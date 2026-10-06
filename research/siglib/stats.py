"""Performance statistics for the model lab's verdicts (spec 2026-10-02 §3.2–3.3).

Conventions, pinned by tests/research/test_siglib_stats.py against hand-computed values:
- returns are simple returns indexed by bar open_time in epoch ms, like BacktestResult.returns;
- a week runs from Monday 00:00 to Monday 00:00 UTC, and only complete weeks count;
- standard deviations are sample (ddof=1); skewness and kurtosis are population moments, with
  kurtosis not in excess form (a normal distribution has 3), as in Bailey & López de Prado (2014).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.siglib.data import week_start

WEEKS_PER_YEAR = 52


def weekly_returns(daily: pd.Series) -> pd.Series:
    """Compound daily returns into Monday-to-Monday weeks, indexed by each week's Monday (ms).

    A week missing any of its seven days is dropped, so a window's leftover days at either end
    never form a partial week."""
    weeks = week_start(daily.index.to_numpy(dtype="int64"))
    grouped = (1.0 + daily).groupby(weeks)
    complete = grouped.size() == 7
    return (grouped.prod() - 1.0)[complete]


def sharpe(returns: pd.Series, periods_per_year: int = WEEKS_PER_YEAR) -> float:
    """Mean over sample standard deviation, × √periods_per_year. NaN when the standard deviation
    is zero or undefined: a NaN Sharpe fails every comparison a gate makes."""
    sd = float(returns.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(returns.mean()) / sd * math.sqrt(periods_per_year)


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall of the compounded equity curve, as a positive fraction.

    The starting equity of 1.0 counts as a peak, so a loss on the first bar is a drawdown."""
    equity = np.concatenate([[1.0], np.cumprod(1.0 + returns.to_numpy(dtype=float))])
    return float((1.0 - equity / np.maximum.accumulate(equity)).max())
