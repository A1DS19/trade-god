"""store.py owns all parquet I/O: idempotent upsert keyed on the dataset's time
column, high-water marks for resumable backfills, atomic writes."""

from __future__ import annotations

import pandas as pd
import pytest

from research import store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _rows(*times):
    return [{"open_time": t, "close": float(t) / 1000} for t in times]


def test_upsert_creates_and_loads(warehouse):
    n = store.upsert("klines_1h", "DOGEUSDT", _rows(1000, 2000), "open_time")
    assert n == 2
    df = store.load("klines_1h", "DOGEUSDT")
    assert list(df["open_time"]) == [1000, 2000]


def test_upsert_dedups_and_sorts(warehouse):
    store.upsert("klines_1h", "DOGEUSDT", _rows(2000, 1000), "open_time")
    n = store.upsert("klines_1h", "DOGEUSDT", _rows(2000, 3000), "open_time")
    assert n == 1  # 2000 already present; only 3000 is new
    df = store.load("klines_1h", "DOGEUSDT")
    assert list(df["open_time"]) == [1000, 2000, 3000]


def test_upsert_newer_row_wins_on_same_time(warehouse):
    store.upsert("oi_1h", "DOGEUSDT", [{"timestamp": 1000, "sum_open_interest": 1.0}], "timestamp")
    store.upsert("oi_1h", "DOGEUSDT", [{"timestamp": 1000, "sum_open_interest": 2.0}], "timestamp")
    df = store.load("oi_1h", "DOGEUSDT")
    assert len(df) == 1 and df.iloc[0]["sum_open_interest"] == 2.0


def test_upsert_empty_rows_noop(warehouse):
    assert store.upsert("klines_1h", "DOGEUSDT", [], "open_time") == 0
    assert store.load("klines_1h", "DOGEUSDT").empty


def test_high_water_mark(warehouse):
    assert store.high_water_mark("klines_1h", "DOGEUSDT", "open_time") is None
    store.upsert("klines_1h", "DOGEUSDT", _rows(1000, 5000, 3000), "open_time")
    assert store.high_water_mark("klines_1h", "DOGEUSDT", "open_time") == 5000


def test_unknown_dataset_rejected(warehouse):
    with pytest.raises(KeyError):
        store.upsert("nope", "DOGEUSDT", _rows(1), "open_time")
