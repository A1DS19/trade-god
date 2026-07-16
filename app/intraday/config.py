"""Frozen strategy + engine settings. Strategy params are pre-registered
(2b findings) — do not tune them here; a new value requires a new research
phase."""

import os

HORIZON_BARS = 32
MAX_K = 10
PAPER_EQUITY = 100.0
CHECK_INTERVAL = 900
DAILY_LOSS_HALT = 0.05
MAX_DD_HALT = 0.20
UNIVERSE_REFRESH_DAYS = 7
ERROR_ALERT_STRIKES = 3
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "paper")
RESUME = os.environ.get("INTRADAY_RESUME") == "1"
