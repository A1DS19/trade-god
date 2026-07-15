"""Warehouse layout and dataset definitions."""

import os
from pathlib import Path

# Override in tests / alternate machines via env.
WAREHOUSE_DIR = Path(os.environ.get("RESEARCH_WAREHOUSE_DIR", str(Path(__file__).parent / "warehouse")))

RATE_LIMIT_DELAY = 0.5  # seconds between REST requests; never run from the prod IP

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
MINUTE_MS = 60_000

# dataset name -> (time column, expected bar spacing in ms; None = irregular)
DATASETS: dict[str, tuple[str, int | None]] = {
    "klines_5m": ("open_time", 5 * MINUTE_MS),
    "klines_15m": ("open_time", 15 * MINUTE_MS),
    "klines_1h": ("open_time", HOUR_MS),
    "klines_4h": ("open_time", 4 * HOUR_MS),
    "klines_1d": ("open_time", DAY_MS),
    "funding": ("funding_time", 8 * HOUR_MS),
    "premium_index_1h": ("open_time", HOUR_MS),
    "oi_1h": ("timestamp", HOUR_MS),
    "long_short_1h": ("timestamp", HOUR_MS),
    "universe": ("snapshot_key", None),
    "intraday_universe": ("snapshot_key", None),
}

# OI / long-short endpoints only serve the trailing ~30 days; clamp with margin.
ROLLING_WINDOW_MS = 29 * DAY_MS

# Minute-level klines are capped so they never backfill to listing:
# 15m from 2023-01-01 (or listing, whichever is later), 5m trailing ~18 months.
KLINES_15M_FLOOR_MS = 1_672_531_200_000  # 2023-01-01T00:00:00Z
KLINES_5M_WINDOW_MS = 548 * DAY_MS


def dataset_start_floor(dataset: str, now_ms: int) -> int:
    """Earliest allowed backfill start for a dataset; 0 = no floor."""
    if dataset == "klines_15m":
        return KLINES_15M_FLOOR_MS
    if dataset == "klines_5m":
        return now_ms - KLINES_5M_WINDOW_MS
    return 0
