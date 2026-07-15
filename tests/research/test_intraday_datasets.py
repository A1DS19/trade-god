"""Intraday dataset registration and backfill start floors."""

from research import config

NOW_MS = 1_752_500_000_000


def test_intraday_datasets_registered():
    assert config.DATASETS["klines_15m"] == ("open_time", 15 * config.MINUTE_MS)
    assert config.DATASETS["klines_5m"] == ("open_time", 5 * config.MINUTE_MS)
    assert config.DATASETS["intraday_universe"] == ("snapshot_key", None)


def test_start_floor_15m_is_2023_01_01():
    assert config.dataset_start_floor("klines_15m", NOW_MS) == 1_672_531_200_000


def test_start_floor_5m_is_trailing_window():
    assert config.dataset_start_floor("klines_5m", NOW_MS) == NOW_MS - config.KLINES_5M_WINDOW_MS
    assert config.KLINES_5M_WINDOW_MS == 548 * config.DAY_MS


def test_no_floor_for_classic_datasets():
    for ds in ("klines_1h", "klines_4h", "klines_1d", "funding",
               "premium_index_1h", "oi_1h", "long_short_1h", "universe",
               "intraday_universe"):
        assert config.dataset_start_floor(ds, NOW_MS) == 0
