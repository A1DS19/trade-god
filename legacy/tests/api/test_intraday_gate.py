"""GET /intraday/gate — extended go-live gate tracker (window ends 2026-10-15).

Date arithmetic is tested through gate_progress(today=...) so tests never
depend on the wall clock; the endpoint test asserts shape only.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.api import queries
from tests.api.conftest import CLOSED_TRADE

MID_WINDOW = date(2026, 9, 1)


def _seed_trades(seed, pnls, exit_time=CLOSED_TRADE["exit_time"]):
    for p in pnls:
        seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": p, "exit_time": exit_time})


def _seed_limit(seed, outcome, resolved_at="2026-07-17T00:45:22+00:00"):
    seed("IntradayLimit", symbol="A", limit_price=1.0, placed_at=resolved_at,
         resolved_at=resolved_at, outcome=outcome, admitted=outcome == "trade_through")


def test_window_math_mid_window(mem_db):
    g = queries.gate_progress(today=MID_WINDOW)
    assert g["window"] == {"start": "2026-07-16", "end": "2026-10-15", "days_total": 91,
                           "days_elapsed": 47, "days_remaining": 44}


def test_window_clamps_before_and_after(mem_db):
    assert queries.gate_progress(today=date(2026, 7, 10))["window"]["days_elapsed"] == 0
    late = queries.gate_progress(today=date(2026, 11, 1))["window"]
    assert late["days_elapsed"] == 91 and late["days_remaining"] == 0


def test_significance_needs_two_trades(mem_db, seed):
    assert queries.gate_progress(today=MID_WINDOW)["criteria"]["significance"] == {
        "trades": 0, "mean_pnl_usd": None, "sd_pnl_usd": None, "t_stat": None, "pass": False}
    _seed_trades(seed, [0.5])
    s = queries.gate_progress(today=MID_WINDOW)["criteria"]["significance"]
    assert s["trades"] == 1 and s["t_stat"] is None and s["pass"] is False


def test_significance_t_stat_hand_computed(mem_db, seed):
    _seed_trades(seed, [0.5, -0.1, 0.3, 0.1])   # mean 0.2, sample sd 0.2582, t = 0.2 / (0.2582/2)
    s = queries.gate_progress(today=MID_WINDOW)["criteria"]["significance"]
    assert s["trades"] == 4
    assert s["mean_pnl_usd"] == pytest.approx(0.2)
    assert s["sd_pnl_usd"] == pytest.approx(0.2582, abs=1e-4)
    assert s["t_stat"] == pytest.approx(1.549, abs=1e-3)
    assert s["pass"] is False


def test_significance_zero_variance_is_null(mem_db, seed):
    _seed_trades(seed, [0.1, 0.1, 0.1])
    s = queries.gate_progress(today=MID_WINDOW)["criteria"]["significance"]
    assert s["t_stat"] is None and s["pass"] is False


def test_ex_top5_excludes_five_best(mem_db, seed):
    _seed_trades(seed, [1.0, 0.8, 0.6, 0.4, 0.2, -0.5, -0.7])   # net 1.8, top-5 3.0
    c = queries.gate_progress(today=MID_WINDOW)["criteria"]["ex_top5_pnl"]
    assert c["top5_usd"] == pytest.approx(3.0)
    assert c["value_usd"] == pytest.approx(-1.2)
    assert c["pass"] is False


def test_ex_top5_passes_at_exactly_zero(mem_db, seed):
    _seed_trades(seed, [1.0, 1.0, 1.0, 1.0, 1.0, 0.0])
    c = queries.gate_progress(today=MID_WINDOW)["criteria"]["ex_top5_pnl"]
    assert c["value_usd"] == pytest.approx(0.0) and c["pass"] is True


def test_trades_after_window_end_are_excluded(mem_db, seed):
    _seed_trades(seed, [1.0], exit_time="2026-10-15T23:45:22+00:00")
    _seed_trades(seed, [-5.0], exit_time="2026-10-16T00:15:22+00:00")
    c = queries.gate_progress(today=date(2026, 10, 20))["criteria"]
    assert c["significance"]["trades"] == 1
    assert c["ex_top5_pnl"]["value_usd"] == pytest.approx(0.0)


def test_limits_after_window_end_are_excluded(mem_db, seed):
    _seed_limit(seed, "trade_through", resolved_at="2026-10-15T23:45:22+00:00")
    _seed_limit(seed, "miss", resolved_at="2026-10-16T00:15:22+00:00")
    c = queries.gate_progress(today=date(2026, 10, 20))["criteria"]["trade_through_rate"]
    assert c == {"value_pct": 100.0, "pass": True}


def test_halt_latch_fails_kill_switch_criterion(mem_db, seed):
    seed("IntradayState", key="killswitch",
         value={"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": True,
                "day": "2026-09-01", "day_anchor": 100.0, "peak": 100.0},
         updated="2026-09-01T00:00:00+00:00")
    g = queries.gate_progress(today=MID_WINDOW)
    ks = g["criteria"]["kill_switch"]
    assert ks["halted_now"] is True and ks["pass"] is False
    assert ks["daily_halt_at_pct"] == -5.0
    assert ks["drawdown_halt_at_pct"] == -20.0
    assert "Telegram" in ks["note"]
    assert g["all_criteria_pass"] is False


def test_trade_through_rate_threshold(mem_db, seed):
    _seed_limit(seed, "trade_through")
    _seed_limit(seed, "miss")
    c = queries.gate_progress(today=MID_WINDOW)["criteria"]["trade_through_rate"]
    assert c == {"value_pct": 50.0, "pass": False}


def test_no_resolved_limits_rate_is_null(mem_db):
    c = queries.gate_progress(today=MID_WINDOW)["criteria"]["trade_through_rate"]
    assert c == {"value_pct": None, "pass": False}


def test_all_criteria_pass_when_every_criterion_passes(mem_db, seed):
    _seed_trades(seed, [0.1, 0.12, 0.08, 0.1, 0.11, 0.09])   # t ≈ 17, ex-top-5 = +0.08
    _seed_limit(seed, "trade_through")
    g = queries.gate_progress(today=MID_WINDOW)
    assert all(c["pass"] for c in g["criteria"].values())
    assert g["all_criteria_pass"] is True


def test_endpoint_shape(client):
    g = client.get("/intraday/gate").json()
    assert set(g) == {"window", "criteria", "all_criteria_pass"}
    assert set(g["criteria"]) == {"significance", "ex_top5_pnl", "kill_switch",
                                  "trade_through_rate"}
