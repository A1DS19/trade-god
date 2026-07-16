"""PaperBook money-path goldens + replay parity against the batch builder."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.intraday import strategy
from app.intraday.paper import Bar, PaperBook

BAR_MS = 900_000


def _bar(t, close, low=None):
    return Bar(open_time=t * BAR_MS, close=close, low=close if low is None else low)


def _book(k=2, horizon=4):
    return PaperBook(equity=100.0, max_k=k, horizon_bars=horizon)


def test_signal_places_limit_then_trade_through_fills():
    book = _book()
    r1 = book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    assert [p["symbol"] for p in r1.placements] == ["A"]
    r2 = book.on_bar({"A": _bar(1, 101.0, low=99.9)}, {"A": 0.0}, {"A"})
    assert r2.resolutions[0]["outcome"] == "trade_through"
    assert r2.entries[0]["entry_price"] == 100.0


def test_touch_only_does_not_fill():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    r2 = book.on_bar({"A": _bar(1, 101.0, low=100.0)}, {"A": 0.0}, {"A"})
    assert r2.resolutions[0]["outcome"] == "touch_only"
    assert not r2.entries


def test_missing_bar_resolves_no_data():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    r2 = book.on_bar({}, {}, {"A"})
    assert r2.resolutions[0]["outcome"] == "no_data"


def test_horizon_exit_pnl_and_costs():
    book = _book(k=1, horizon=2)
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    book.on_bar({"A": _bar(1, 100.0, low=99.0)}, {"A": 0.0}, {"A"})   # fill @100, held 1
    r3 = book.on_bar({"A": _bar(2, 102.0)}, {"A": 0.0}, {"A"})        # held 2 == H -> exit
    assert len(r3.exits) == 1
    e = r3.exits[0]
    slot = 100.0
    expected = slot * 0.02 - slot * (0.0002 + 0.0008)
    assert e["pnl_usd"] == pytest.approx(expected)
    assert book.equity == pytest.approx(100.0 + expected)


def test_slot_cap_admits_lowest_z_first():
    book = _book(k=1, horizon=4)
    bars0 = {s: _bar(0, 100.0) for s in ("A", "B")}
    book.on_bar(bars0, {"A": -4.0, "B": -6.0}, {"A", "B"})
    bars1 = {s: _bar(1, 100.0, low=99.0) for s in ("A", "B")}
    r = book.on_bar(bars1, {"A": 0.0, "B": 0.0}, {"A", "B"})
    admitted = {x["symbol"]: x["admitted"] for x in r.resolutions}
    assert admitted == {"B": True, "A": False}


def test_funding_applied_to_realized_pnl():
    book = _book(k=1, horizon=2)
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    book.on_bar({"A": _bar(1, 100.0, low=99.0)}, {"A": 0.0}, {"A"})
    book.apply_funding("A", 0.0001)     # long pays positive funding
    r = book.on_bar({"A": _bar(2, 100.0)}, {"A": 0.0}, {"A"})
    assert r.exits[0]["pnl_usd"] == pytest.approx(
        -100.0 * (0.0002 + 0.0008) - 100.0 * 0.0001)


def test_serialization_roundtrip_preserves_behavior():
    book = _book()
    book.on_bar({"A": _bar(0, 100.0)}, {"A": -5.0}, {"A"})
    clone = PaperBook.from_dict(book.to_dict())
    r_orig = book.on_bar({"A": _bar(1, 101.0, low=99.0)}, {"A": 0.0}, {"A"})
    r_clone = clone.on_bar({"A": _bar(1, 101.0, low=99.0)}, {"A": 0.0}, {"A"})
    assert r_orig.entries == r_clone.entries
    assert book.to_dict() == clone.to_dict()


def test_replay_parity_with_batch_builder():
    rng = np.random.default_rng(42)
    n, syms, k, horizon = 400, ["A", "B", "C"], 2, 4
    idx = pd.Index(np.arange(n) * BAR_MS, name="open_time")
    close = pd.DataFrame(
        {s: 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n)) for s in syms}, index=idx)
    low = close * (1 - rng.uniform(0, 0.02, (n, len(syms))))
    z = pd.DataFrame(rng.normal(0, 2.0, (n, len(syms))), index=idx, columns=syms)
    elig = pd.DataFrame(True, index=idx, columns=syms)

    w_batch = strategy.build_weights(
        z, close, low, elig,
        {"horizon_bars": horizon, "exit": "horizon", "max_k": k}, "maker_limit")

    book = PaperBook(equity=100.0, max_k=k, horizon_bars=horizon)
    spans = []   # (symbol, fill_bar_index)
    for t in range(n):
        bars = {s: Bar(open_time=int(idx[t]), close=float(close.iloc[t][s]),
                       low=float(low.iloc[t][s])) for s in syms}
        zrow = {s: float(z.iloc[t][s]) for s in syms}
        res = book.on_bar(bars, zrow, set(syms))
        for e in res.entries:
            spans.append((e["symbol"], t))

    # reconstruct exposure: a fill confirmed at bar t earned from bar t-1
    # (batch w[signal] with signal = t-1) for `horizon` bars
    w_live = pd.DataFrame(0.0, index=idx, columns=syms)
    for sym, fill_bar in spans:
        start = fill_bar - 1
        w_live.iloc[start:start + horizon,
                    w_live.columns.get_loc(sym)] = 1.0 / k
    # the batch builder needs t+1 in range; the live book can't know the last
    # bar's future either — compare on the interior
    pd.testing.assert_frame_equal(
        w_live.iloc[: n - 1], w_batch.iloc[: n - 1], check_dtype=False)
