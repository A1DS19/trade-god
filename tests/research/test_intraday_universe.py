"""Top-N intraday universe: rank warehouse symbols by 30-day median daily quote volume."""

from __future__ import annotations

import pytest

from research import intraday_universe, store

DAY_MS = 86_400_000


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _write_1d(symbol, quote_volumes):
    rows = [
        {"open_time": i * DAY_MS, "close": 1.0, "quote_volume": qv}
        for i, qv in enumerate(quote_volumes)
    ]
    store.upsert("klines_1d", symbol, rows, "open_time")


NOW_40D = 40 * DAY_MS  # "now" for fixtures whose last bar is day 39 — 1 day fresh


def test_ranks_by_median_quote_volume(warehouse):
    _write_1d("AAAUSDT", [100.0] * 40)
    _write_1d("BBBUSDT", [300.0] * 40)
    _write_1d("CCCUSDT", [200.0] * 40)

    top = intraday_universe.select_top(2, now_ms=NOW_40D)

    assert [r["symbol"] for r in top] == ["BBBUSDT", "CCCUSDT"]
    assert top[0]["rank"] == 1
    assert top[0]["median_quote_volume_30d"] == 300.0


def test_median_uses_last_30_days_only(warehouse):
    _write_1d("OLDUSDT", [9_000.0] * 40 + [10.0] * 30)
    _write_1d("NEWUSDT", [100.0] * 70)

    top = intraday_universe.select_top(2, now_ms=70 * DAY_MS)

    assert [r["symbol"] for r in top] == ["NEWUSDT", "OLDUSDT"]


def test_skips_symbols_with_short_history(warehouse):
    _write_1d("FRESHUSDT", [1_000_000.0] * 10)
    _write_1d("OKUSDT", [50.0] * 35)

    top = intraday_universe.select_top(30, now_ms=35 * DAY_MS)

    assert [r["symbol"] for r in top] == ["OKUSDT"]


def test_skips_stale_symbols(warehouse):
    # DEADUSDT's last bar is day 39; LIVEUSDT's is day 47. At now=day 48,
    # DEAD is 9 days stale (delisted-coin parquet) and must not rank despite volume.
    _write_1d("DEADUSDT", [9_000.0] * 40)
    _write_1d("LIVEUSDT", [50.0] * 48)

    top = intraday_universe.select_top(30, now_ms=48 * DAY_MS)

    assert [r["symbol"] for r in top] == ["LIVEUSDT"]


def test_save_snapshot_writes_keyed_rows(warehouse):
    _write_1d("AAAUSDT", [100.0] * 40)
    rows = intraday_universe.select_top(1, now_ms=NOW_40D)

    n = intraday_universe.save_snapshot(rows, snapshot_ms=1234)

    assert n == 1
    snap = store.load("intraday_universe", "ALL")
    assert snap.iloc[0]["snapshot_key"] == "1234:AAAUSDT"
    assert snap.iloc[0]["symbol"] == "AAAUSDT"
