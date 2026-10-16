"""The 21 timing features of the BTC and ETH arms (spec 2026-10-02 §2.2, as amended).

Each is computed at daily bar t from bars closed by t's close. Bars sit on a complete daily grid,
so a missing day leaves NaN in every window that spans it, and the arms never train on or decide
from such a row."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS

RETURN_DAYS = (1, 3, 7, 14, 30, 60, 90, 180, 365)
SMA_DAYS = (7, 20, 50, 100, 200)
ANNUAL_DAYS = 365
TIMING_FEATURES = [
    *(f"ret_{n}" for n in RETURN_DAYS),
    *(f"trend_{n}" for n in SMA_DAYS),
    "rv_1", "rv_7", "rv_30",
    "drawdown_365",
    "volume_7_30",
    "taker_buy_7",
    "other_ret_30",
]


def daily_grid(daily: pd.DataFrame) -> pd.DataFrame:
    """One asset's daily klines indexed by open_time, one row per day from its first bar to its
    last; a day without a bar is a row of NaN."""
    bars = daily.set_index("open_time").sort_index()
    return bars.reindex(np.arange(bars.index[0], bars.index[-1] + DAY_MS, DAY_MS))


def daily_rv(hourly: pd.DataFrame) -> pd.Series:
    """Realised variance per day: squared log returns between consecutive hourly closes, summed
    over the day that holds the later bar.

    A return across missing hours stays in, so its square carries their variance and the day's
    sum stays unbiased. A day with no hourly bar has no value."""
    bars = hourly.sort_values("open_time")
    squared = np.log(bars["close"]).diff() ** 2
    day = (bars["open_time"] // DAY_MS) * DAY_MS
    return squared.groupby(day.to_numpy()).sum(min_count=1)


def annualised_vol(mean_daily_rv: pd.Series) -> pd.Series:
    """√(365 · RV): a mean daily variance as annual volatility. A negative value, which only an
    extrapolating forecast can produce, counts as 0."""
    return np.sqrt(ANNUAL_DAYS * mean_daily_rv.clip(lower=0.0))


def timing_features(bars: pd.DataFrame, rv: pd.Series, other_close: pd.Series) -> pd.DataFrame:
    """The 21 features at every row of `bars` (a daily_grid frame). `rv` is daily_rv of the same
    asset and `other_close` the other asset's daily closes, both indexed by day."""
    close = bars["close"]
    log_close = np.log(close)
    rv = rv.reindex(bars.index)
    quote = bars["quote_volume"]
    other = np.log(other_close.reindex(bars.index))
    cols = {f"ret_{n}": log_close - log_close.shift(n) for n in RETURN_DAYS}
    cols |= {f"trend_{n}": close / close.rolling(n).mean() - 1.0 for n in SMA_DAYS}
    cols["rv_1"] = annualised_vol(rv)
    cols["rv_7"] = annualised_vol(rv.rolling(7).mean())
    cols["rv_30"] = annualised_vol(rv.rolling(30).mean())
    cols["drawdown_365"] = close / close.rolling(365).max() - 1.0
    cols["volume_7_30"] = quote.rolling(7).mean() / quote.rolling(30).mean()
    cols["taker_buy_7"] = bars["taker_buy_quote_volume"].rolling(7).sum() / quote.rolling(7).sum()
    cols["other_ret_30"] = other - other.shift(30)
    return pd.DataFrame(cols, index=bars.index)[TIMING_FEATURES]
