"""GET /intraday/gate — 4-week go-live gate tracker.

Date arithmetic is tested through gate_progress(today=...) so tests never
depend on the wall clock; the endpoint test asserts shape only.
"""

from __future__ import annotations

from datetime import date

from app.api import queries
from tests.api.conftest import CLOSED_TRADE


def test_window_math_mid_window(mem_db):
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["window"] == {"start": "2026-07-16", "end": "2026-08-13",
                           "days_elapsed": 2, "days_remaining": 26}


def test_window_clamps_before_and_after(mem_db):
    assert queries.gate_progress(today=date(2026, 7, 10))["window"]["days_elapsed"] == 0
    late = queries.gate_progress(today=date(2026, 9, 1))["window"]
    assert late["days_elapsed"] == 28 and late["days_remaining"] == 0


def test_pnl_criterion_edges(mem_db, seed):
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["cumulative_pnl"] == {"value_usd": 0.0, "pass": True}  # no trades: 0 >= 0

    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": -0.01})
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["cumulative_pnl"]["pass"] is False
    assert g["on_track"] is False


def test_halt_latch_blocks_on_track(mem_db, seed):
    seed("IntradayState", key="killswitch",
         value={"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": True,
                "day": "2026-07-18", "day_anchor": 100.0, "peak": 100.0},
         updated="2026-07-18T00:00:00+00:00")
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["kill_switch"]["halted_now"] is True
    assert g["criteria"]["kill_switch"]["daily_halt_at_pct"] == -5.0
    assert g["criteria"]["kill_switch"]["drawdown_halt_at_pct"] == -20.0
    assert "Telegram" in g["criteria"]["kill_switch"]["note"]
    assert g["on_track"] is False


def test_trade_through_rate_from_fills(mem_db, seed):
    seed("IntradayLimit", symbol="A", limit_price=1.0, placed_at="t",
         resolved_at="t", outcome="trade_through", admitted=True)
    seed("IntradayLimit", symbol="A", limit_price=1.0, placed_at="t",
         resolved_at="t", outcome="miss", admitted=False)
    g = queries.gate_progress(today=date(2026, 7, 18))
    assert g["criteria"]["trade_through_rate_pct"] == 50.0


def test_no_resolved_limits_rate_is_null(mem_db):
    assert queries.gate_progress(today=date(2026, 7, 18))["criteria"]["trade_through_rate_pct"] is None


def test_endpoint_shape(client):
    g = client.get("/intraday/gate").json()
    assert set(g) == {"window", "criteria", "on_track"}
    assert set(g["criteria"]) == {"cumulative_pnl", "kill_switch", "trade_through_rate_pct"}
