"""Labels for the timing arms (spec 2026-10-02 §2.2).

Rows are daily bars indexed by open_time on a complete daily grid (features.daily_grid). A row's
decision is made when its bar closes, at 00:00 UTC the next day."""

from __future__ import annotations

import pandas as pd

HORIZON_DAYS = 7


def up_label(close: pd.Series) -> pd.Series:
    """1.0 when close[t+7] / close[t] - 1 > 0, else 0.0, and NaN while close[t+7] is unknown.

    `close` must sit on a complete daily grid, so that 7 rows on is 7 days on."""
    ahead = close.shift(-HORIZON_DAYS) / close - 1.0
    return (ahead > 0).astype(float).where(ahead.notna())
