"""check.py reports per-file row counts, time coverage, internal gaps
(spacing > expected step) and staleness, so backtests can't silently span holes."""

from __future__ import annotations

import pytest

from research import check, store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def test_finds_gaps(warehouse):
    h = 3_600_000
    rows = [{"open_time": i * h, "close": 1.0} for i in (0, 1, 2, 5, 6)]  # gap: 2->5
    store.upsert("klines_1h", "DOGEUSDT", rows, "open_time")

    report = check.scan()

    [entry] = [e for e in report if e["dataset"] == "klines_1h" and e["symbol"] == "DOGEUSDT"]
    assert entry["rows"] == 5
    assert entry["gaps"] == 1
    assert entry["largest_gap_ms"] == 3 * h


def test_no_gaps_clean(warehouse):
    h = 3_600_000
    store.upsert("klines_1h", "DOGEUSDT", [{"open_time": i * h, "close": 1.0} for i in range(4)], "open_time")
    [entry] = check.scan()
    assert entry["gaps"] == 0


def test_irregular_datasets_skip_gap_check(warehouse):
    store.upsert("universe", "ALL", [{"snapshot_key": "1:A", "symbol": "A"}], "snapshot_key")
    [entry] = check.scan()
    assert entry["gaps"] is None
