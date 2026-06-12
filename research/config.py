"""Warehouse layout and dataset definitions."""

import os
from pathlib import Path

# Override in tests / alternate machines via env.
WAREHOUSE_DIR = Path(os.environ.get("RESEARCH_WAREHOUSE_DIR", str(Path(__file__).parent / "warehouse")))

RATE_LIMIT_DELAY = 0.5  # seconds between REST requests; never run from the prod IP

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS

# dataset name -> (time column, expected bar spacing in ms; None = irregular)
DATASETS: dict[str, tuple[str, int | None]] = {
    "klines_1h": ("open_time", HOUR_MS),
    "klines_4h": ("open_time", 4 * HOUR_MS),
    "klines_1d": ("open_time", DAY_MS),
    "funding": ("funding_time", 8 * HOUR_MS),
    "premium_index_1h": ("open_time", HOUR_MS),
    "oi_1h": ("timestamp", HOUR_MS),
    "long_short_1h": ("timestamp", HOUR_MS),
    "universe": ("snapshot_key", None),
}

# OI / long-short endpoints only serve the trailing ~30 days; clamp with margin.
ROLLING_WINDOW_MS = 29 * DAY_MS
