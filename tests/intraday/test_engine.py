"""Engine cycle wiring: halt semantics, per-symbol error strikes, state
persistence, restart recovery. DB helpers and notifier are recorded fakes —
the cycle's observable behavior is what's pinned."""

from __future__ import annotations

import time
import types

import numpy as np
import pytest

from app.intraday import engine
from app.intraday.paper import PaperBook
from app.intraday.risk import ErrorTracker, KillSwitch

BAR_MS = 900_000


def _klines(n=120, close=100.0, low=99.0, last_closed=True):
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    out = []
    for i in range(n):
        t = now_open - (n - i) * BAR_MS
        out.append([t, "100", "101", str(low), str(close), "10",
                    t + BAR_MS - 1, "1000", 5, "5", "500", "0"])
    return out


class FakeClient:
    def __init__(self, symbols, fail=()):
        self.symbols = symbols
        self.fail = set(fail)

    def futures_klines(self, symbol, interval, limit):
        if symbol in self.fail:
            raise RuntimeError("boom")
        return _klines()

    def futures_funding_rate(self, symbol, startTime, limit):
        return []


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _f(*a, **k):
            self.calls.append((name, a, k))
        return _f


@pytest.fixture
def ctx(monkeypatch):
    state = {}
    notify = Recorder()
    db = Recorder()
    monkeypatch.setattr(engine, "models", db)
    db.log_intraday_trade = lambda **k: len(db.calls)   # returns fake id
    c = engine.Context(
        client=FakeClient(["AAAUSDT", "BBBUSDT"]),
        book=PaperBook(equity=100.0, max_k=10, horizon_bars=32),
        killswitch=KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.20),
        tracker=ErrorTracker(strikes=3),
        universe=["AAAUSDT", "BBBUSDT"],
        universe_refreshed_ms=int(time.time() * 1000),
        last_funding_ms=0,
        notify=notify,
        state_get=state.get,
        state_set=lambda k, v: state.__setitem__(k, v),
    )
    c._state = state
    return c


def test_cycle_runs_and_persists_state(ctx):
    summary = engine.run_cycle(ctx)
    assert summary["symbols_ok"] == 2
    assert "paper_book" in ctx._state and "killswitch" in ctx._state


def test_error_strikes_alert_once(ctx):
    ctx.client.fail = {"BBBUSDT"}
    engine.run_cycle(ctx)
    engine.run_cycle(ctx)
    engine.run_cycle(ctx)
    strikes = [c for c in ctx.notify.calls if c[0] == "notify_error_strikes"]
    assert len(strikes) == 1
    assert strikes[0][1][0] == "BBBUSDT"


def test_halted_killswitch_blocks_new_placements(ctx, monkeypatch):
    ctx.killswitch.halted = True
    # force a deep-oversold z so a placement WOULD happen if not halted
    monkeypatch.setattr(engine.strategy, "zscore",
                        lambda c, v, q: c * 0.0 - 5.0)
    engine.run_cycle(ctx)
    assert not ctx.book.pending


def test_restart_recovers_book_from_state(ctx):
    ctx.book.pending["AAAUSDT"] = {"limit": 99.0, "z": -4.0, "placed_ms": 0,
                                   "free_at_placement": 10}
    engine.persist(ctx)
    restored = PaperBook.from_dict(ctx._state["paper_book"])
    assert restored.pending["AAAUSDT"]["free_at_placement"] == 10
