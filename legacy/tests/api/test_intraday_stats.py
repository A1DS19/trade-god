"""GET /intraday/stats — hand-computed aggregates over closed trades."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def _seed_three(seed):
    # +1.00 (DOGE), -0.50 (XRP), +0.50 (DOGE) -> net +1.00
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0, "pnl_pct": 0.10,
                             "exit_time": "2026-07-17T00:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT", "pnl_usd": -0.5,
                             "pnl_pct": -0.05, "entry_time": "2026-07-17T05:00:00+00:00",
                             "exit_time": "2026-07-17T12:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 0.5, "pnl_pct": 0.05,
                             "entry_time": "2026-07-18T01:00:00+00:00",
                             "exit_time": "2026-07-18T08:00:00+00:00"})


def test_hand_computed_aggregates(client, seed):
    _seed_three(seed)
    s = client.get("/intraday/stats").json()
    assert s["trades"] == 3
    assert s["win_rate_pct"] == 66.67
    assert s["net_pnl_usd"] == 1.0
    assert s["gross_win_usd"] == 1.5
    assert s["gross_loss_usd"] == 0.5
    assert s["profit_factor"] == 3.0
    assert s["avg_pnl_pct"] == round((10 - 5 + 5) / 3, 4)
    assert s["median_pnl_pct"] == 5.0
    assert s["best_trade"] == {"symbol": "DOGEUSDT", "pnl_usd": 1.0,
                               "exit_time": "2026-07-17T00:00:00+00:00"}
    assert s["worst_trade"]["symbol"] == "XRPUSDT"
    assert s["period"] == {"first_entry": "2026-07-16T17:00:22+00:00",
                           "last_exit": "2026-07-18T08:00:00+00:00"}
    assert s["by_symbol"]["DOGEUSDT"] == {"trades": 2, "wins": 2,
                                          "win_rate_pct": 100.0, "net_pnl": 1.5}
    assert s["by_symbol"]["XRPUSDT"]["win_rate_pct"] == 0.0


def test_open_trades_excluded(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "status": "open", "pnl_usd": None,
                             "pnl_pct": None, "exit_time": None})
    assert client.get("/intraday/stats").json()["trades"] == 0


def test_since_filters_on_entry_time(client, seed):
    _seed_three(seed)
    s = client.get("/intraday/stats?since=2026-07-18T00:00:00").json()
    assert s["trades"] == 1 and s["net_pnl_usd"] == 0.5


def test_empty_shape(client):
    s = client.get("/intraday/stats").json()
    assert s == {"trades": 0, "message": "No closed intraday trades in window."}


def test_all_wins_profit_factor_capped(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    assert client.get("/intraday/stats").json()["profit_factor"] == 999.0
