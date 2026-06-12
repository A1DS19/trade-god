"""Universe resolution: top-N TRADING USDT perps by 24h quote volume, with
exchangeInfo metadata (onboardDate), snapshot-appended to universe.parquet."""

from __future__ import annotations

import pytest

from research import store, universe


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class FakeClient:
    def futures_exchange_info(self):
        def sym(s, status="TRADING", ct="PERPETUAL", quote="USDT", onboard=1567965300000):
            return {"symbol": s, "status": status, "contractType": ct,
                    "quoteAsset": quote, "onboardDate": onboard}
        return {"symbols": [
            sym("DOGEUSDT"),
            sym("BSVUSDT"),
            sym("OLDUSDT", status="SETTLING"),          # not trading -> excluded
            sym("BTCUSDT_240628", ct="CURRENT_QUARTER"),  # not perp -> excluded
            sym("ETHBTC", quote="BTC"),                  # not USDT -> excluded
            sym("PEPEUSDT"),
        ]}

    def futures_ticker(self):
        return [
            {"symbol": "DOGEUSDT", "quoteVolume": "3000"},
            {"symbol": "BSVUSDT", "quoteVolume": "1000"},
            {"symbol": "PEPEUSDT", "quoteVolume": "2000"},
            {"symbol": "OLDUSDT", "quoteVolume": "9999"},   # excluded by exchangeInfo
            {"symbol": "UNLISTEDUSDT", "quoteVolume": "8888"},  # no exchangeInfo entry
        ]


def test_resolve_top_orders_by_quote_volume_and_filters():
    rows = universe.resolve_top(FakeClient(), 2)
    assert [r["symbol"] for r in rows] == ["DOGEUSDT", "PEPEUSDT"]
    assert rows[0]["rank"] == 1 and rows[1]["rank"] == 2
    assert rows[0]["coin"] == "DOGE"
    assert rows[0]["onboard_date_ms"] == 1567965300000


def test_snapshot_appends_to_universe_parquet(warehouse):
    rows = universe.resolve_top(FakeClient(), 2)
    universe.save_snapshot(rows, snapshot_ms=1000)
    universe.save_snapshot(rows, snapshot_ms=2000)  # second day
    df = store.load("universe", "ALL")
    assert len(df) == 4
    assert sorted(set(df["snapshot_ms"])) == [1000, 2000]


def test_snapshot_same_time_idempotent(warehouse):
    rows = universe.resolve_top(FakeClient(), 2)
    universe.save_snapshot(rows, snapshot_ms=1000)
    universe.save_snapshot(rows, snapshot_ms=1000)
    assert len(store.load("universe", "ALL")) == 2
