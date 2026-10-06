"""siglib.stats against hand-computed values (spec §3.2–3.3, §4.4).

Reference values were computed twice, independently, on 2026-10-05: with explicit Python loops,
and with statsmodels 0.15.0 (OLS, cov_type="HAC", maxlags=4, use_correction=False) and scipy
1.18.1 (biased skewness and kurtosis, norm.ppf and norm.cdf). Neither library is a dependency.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from research.config import DAY_MS
from research.siglib import stats

MONDAY = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _daily(first_day: int, returns: list[float]) -> pd.Series:
    return pd.Series(returns, index=[MONDAY + (first_day + i) * DAY_MS for i in range(len(returns))])


def _weekly(returns: list[float]) -> pd.Series:
    return pd.Series(returns, index=[MONDAY + 7 * i * DAY_MS for i in range(len(returns))])


def test_weekly_returns_compound_complete_monday_weeks_only():
    # Saturday 2024-01-06 through Tuesday 2024-01-23: two complete weeks between partial ends.
    returns = [0.01] * 18
    returns[12] = -0.02  # Thursday 2024-01-18, inside the second week
    weekly = stats.weekly_returns(_daily(5, returns))
    assert list(weekly.index) == [MONDAY + 7 * DAY_MS, MONDAY + 14 * DAY_MS]
    assert weekly.iloc[0] == pytest.approx(1.01**7 - 1, rel=1e-12)
    assert weekly.iloc[1] == pytest.approx(1.01**6 * 0.98 - 1, rel=1e-12)


def test_sharpe_is_mean_over_sample_std_times_root_52():
    assert stats.sharpe(pd.Series([0.01, 0.02, -0.01, 0.03])) == pytest.approx(
        5.277986629117474, rel=1e-12)


def test_sharpe_per_period():
    assert stats.sharpe(pd.Series([0.01, 0.02, -0.01, 0.03]), periods_per_year=1) == pytest.approx(
        5.277986629117474 / math.sqrt(52), rel=1e-12)


def test_returns_that_do_not_vary_have_no_sharpe():  # an arm that never trades in a window
    assert math.isnan(stats.sharpe(pd.Series([0.0, 0.0, 0.0])))
    assert math.isnan(stats.sharpe(pd.Series([0.01])))
    assert not stats.sharpe(pd.Series([0.0, 0.0])) > -1.0  # NaN fails every gate comparison


def test_max_drawdown_counts_a_loss_on_the_first_day():
    # equity 1.0 → 0.9 → 0.945 → 0.756 → 0.9828: the trough sits 24.4% under the starting 1.0
    assert stats.max_drawdown(pd.Series([-0.10, 0.05, -0.20, 0.30])) == pytest.approx(0.244, rel=1e-12)


def test_max_drawdown_edges():
    assert stats.max_drawdown(pd.Series([], dtype=float)) == 0.0
    assert stats.max_drawdown(pd.Series([0.01, 0.02])) == 0.0


BENCH = [0.021, -0.034, 0.015, 0.042, -0.011, 0.008, -0.027, 0.033, 0.012, -0.019, 0.026, -0.004]
ARM = [0.015, -0.012, 0.010, 0.030, -0.002, 0.009, -0.010, 0.020, 0.011, -0.006, 0.018, 0.001]


def test_nw_alpha_matches_the_reference():
    fit = stats.nw_alpha(_weekly(ARM), _weekly(BENCH))
    assert fit.alpha == pytest.approx(0.004256714955921019, rel=1e-9)
    assert fit.beta == pytest.approx(0.5309583956281898, rel=1e-9)
    assert fit.se_alpha == pytest.approx(0.00022645201261195535, rel=1e-9)
    assert fit.t_alpha == pytest.approx(18.797426027805987, rel=1e-9)
    assert fit.n == 12


def test_zero_lags_gives_the_white_standard_error():
    fit = stats.nw_alpha(_weekly(ARM), _weekly(BENCH), lags=0)
    assert fit.se_alpha == pytest.approx(0.0003640714004282908, rel=1e-9)


def test_an_exact_multiple_of_btc_has_zero_alpha():  # constant exposure and no trades
    fit = stats.nw_alpha(_weekly([0.5 * b for b in BENCH]), _weekly(BENCH))
    assert fit.alpha == 0.0 and fit.t_alpha == 0.0
    assert fit.beta == pytest.approx(0.5, rel=1e-12)


def test_weeks_align_on_the_index():
    assert stats.nw_alpha(_weekly(ARM), _weekly(BENCH + [0.05])).n == 12


DSR_WEEKLY = [0.012, -0.020, 0.031, 0.004, -0.008, 0.017, 0.025, -0.013, 0.009, 0.002,
              0.019, -0.027, 0.014, 0.006, -0.003, 0.022, 0.011, -0.016, 0.028, 0.001]
TRIAL_SHARPES = [0.05, 0.12, 0.08, 0.15, 0.02, 0.10]  # sample variance 0.0022266666666666667


def test_expected_max_sharpe_of_six_unskilled_trials():
    assert stats.expected_max_sharpe(6, 0.0022266666666666667) == pytest.approx(
        0.061350483116021814, rel=1e-9)


def test_deflated_sharpe_matches_the_reference():
    # sr = 0.34858705162657744, skew = -0.35176553477902145, kurt = 2.236838711880152, T = 20
    # z = (sr - sr0) * sqrt(T - 1) / sqrt(1 - skew*sr + (kurt - 1)/4 * sr^2) = 1.1623883379537419
    assert stats.deflated_sharpe(_weekly(DSR_WEEKLY), TRIAL_SHARPES) == pytest.approx(
        0.8774611208839094, rel=1e-9)


def test_sixty_trials_deflate_further():  # spec §3.3: the N = 60 value is reported, not gated
    assert stats.deflated_sharpe(_weekly(DSR_WEEKLY), TRIAL_SHARPES, n_trials=60) == pytest.approx(
        0.8321758103627532, rel=1e-9)


def test_returns_that_do_not_vary_have_no_deflated_sharpe():
    assert math.isnan(stats.deflated_sharpe(_weekly([0.0] * 20), TRIAL_SHARPES))
