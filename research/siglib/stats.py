"""Performance statistics for the model lab's verdicts (spec 2026-10-02 §3.2–3.3).

Conventions, pinned by tests/research/test_siglib_stats.py against hand-computed values:
- returns are simple returns indexed by bar open_time in epoch ms, like BacktestResult.returns;
- a week runs from Monday 00:00 to Monday 00:00 UTC, and only complete weeks count;
- standard deviations are sample (ddof=1); skewness and kurtosis are population moments, with
  kurtosis not in excess form (a normal distribution has 3), as in Bailey & López de Prado (2014).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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


# An exact multiple of BTC (constant exposure, no trades) leaves OLS an alpha of about 1e-19
# with a standard error just as small, so its t-statistic is noise that could pass a gate.
ALPHA_NOISE = 1e-12


@dataclass(frozen=True)
class AlphaFit:
    alpha: float
    beta: float
    se_alpha: float
    t_alpha: float
    n: int


def nw_alpha(arm: pd.Series, bench: pd.Series, lags: int = 4) -> AlphaFit:
    """OLS arm = α + β·bench + ε on index-aligned rows, with Newey-West standard errors.

    Bartlett weights 1 - lag/(lags + 1), no small-sample correction: statsmodels' HAC with
    use_correction=False. An |α| under ALPHA_NOISE is reported as α = 0, t = 0."""
    both = pd.concat([arm, bench], axis=1, join="inner").dropna()
    y = both.iloc[:, 0].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(both)), both.iloc[:, 1].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    scores = x * (y - x @ coef)[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        gamma = scores[lag:].T @ scores[:-lag]
        meat += (1.0 - lag / (lags + 1)) * (gamma + gamma.T)
    bread = np.linalg.inv(x.T @ x)
    se = math.sqrt((bread @ meat @ bread)[0, 0])
    alpha = float(coef[0])
    if abs(alpha) < ALPHA_NOISE:
        return AlphaFit(alpha=0.0, beta=float(coef[1]), se_alpha=se, t_alpha=0.0, n=len(both))
    return AlphaFit(alpha=alpha, beta=float(coef[1]), se_alpha=se, t_alpha=alpha / se, n=len(both))
