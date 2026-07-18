"""GET /intraday/trades — columns, pct scaling, filters, ordering."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def test_empty_db_returns_empty_list(client):
    r = client.get("/intraday/trades")
    assert r.status_code == 200
    assert r.json() == []


def test_columns_and_pct_scaling(client, seed):
    seed("IntradayTrade", **CLOSED_TRADE)
    row = client.get("/intraday/trades").json()[0]
    assert row["symbol"] == "DOGEUSDT"
    assert row["pnl_pct"] == 8.92          # 0.0892 fraction -> percent
    assert row["pnl_usd"] == 0.8811
    assert row["hold_bars"] == 32
    assert row["status"] == "closed"
    assert row["fill_type"] == "trade_through"
    assert set(row) == {
        "id", "symbol", "limit_price", "entry_price", "exit_price", "slot_usd",
        "entry_time", "exit_time", "hold_bars", "pnl_pct", "pnl_usd",
        "fill_type", "exit_reason", "status",
    }


def test_open_trade_has_null_exit_fields(client, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "exit_price": None, "exit_time": None,
                             "hold_bars": None, "pnl_pct": None, "pnl_usd": None,
                             "exit_reason": None, "status": "open"})
    row = client.get("/intraday/trades").json()[0]
    assert row["status"] == "open"
    assert row["pnl_pct"] is None and row["exit_time"] is None


def test_filters_and_ordering(client, seed):
    seed("IntradayTrade", **CLOSED_TRADE)  # DOGEUSDT, entry 07-16
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT",
                             "entry_time": "2026-07-18T01:00:00+00:00"})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "XRPUSDT", "status": "open",
                             "entry_time": "2026-07-18T02:00:00+00:00"})

    assert [t["symbol"] for t in client.get("/intraday/trades").json()] == \
        ["XRPUSDT", "XRPUSDT", "DOGEUSDT"]          # newest first (id desc)
    assert len(client.get("/intraday/trades?symbol=xrpusdt").json()) == 2  # upcased
    assert len(client.get("/intraday/trades?status=open").json()) == 1
    assert len(client.get("/intraday/trades?since=2026-07-18T00:00:00").json()) == 2
    assert len(client.get("/intraday/trades?limit=1").json()) == 1


def test_limit_over_500_rejected(client):
    assert client.get("/intraday/trades?limit=501").status_code == 422
