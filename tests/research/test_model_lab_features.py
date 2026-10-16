"""The 21 timing features (spec §2.2, as amended): computed at bar t from bars closed by t, on a
complete daily grid; daily RV sums squared hourly log returns, keeping returns across gaps."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import features as feat

DAY = 86_400_000
HOUR = 3_600_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _bars(n_days, growth=0.001, quote=None):
    """Daily klines with close = e^(growth · i), and taker buys 60% of quote volume."""
    quote = np.ones(n_days) if quote is None else np.asarray(quote, dtype=float)
    return pd.DataFrame({"open_time": BASE + np.arange(n_days) * DAY,
                         "close": np.exp(growth * np.arange(n_days)),
                         "quote_volume": quote, "taker_buy_quote_volume": 0.6 * quote})


def _features(bars, rv=1e-4, other_growth=0.002):
    grid = feat.daily_grid(bars)
    other = pd.Series(np.exp(other_growth * np.arange(len(grid))), index=grid.index)
    return feat.timing_features(grid, pd.Series(rv, index=grid.index), other)


def test_the_feature_list_is_the_spec_table():
    assert len(feat.TIMING_FEATURES) == 21
    assert feat.TIMING_FEATURES[:9] == [f"ret_{n}" for n in (1, 3, 7, 14, 30, 60, 90, 180, 365)]


def test_daily_rv_keeps_a_return_across_missing_hours():
    hourly = pd.DataFrame({
        "open_time": [BASE, BASE + HOUR, BASE + 3 * HOUR, BASE + DAY, BASE + 3 * DAY],
        "close": np.exp([0.0, 0.01, 0.04, 0.02, 0.02]),
    })
    rv = feat.daily_rv(hourly)
    # day 0: 0.01² + 0.03² (the 2-hour return across the missing hour); day 1: 0.02²; day 3: 0
    assert rv.index.tolist() == [BASE, BASE + DAY, BASE + 3 * DAY]  # day 2 has no bar, so no value
    assert rv.tolist() == pytest.approx([1e-3, 4e-4, 0.0])


def test_feature_values_on_a_steady_climb():
    quote = np.r_[np.ones(393), np.full(7, 4.0)]
    row = _features(_bars(400, quote=quote)).iloc[-1]
    for n in (1, 3, 7, 14, 30, 60, 90, 180, 365):
        assert row[f"ret_{n}"] == pytest.approx(0.001 * n)
    assert row["trend_7"] == pytest.approx(1 / np.mean(np.exp(-0.001 * np.arange(7))) - 1)
    assert row[["rv_1", "rv_7", "rv_30"]].tolist() == pytest.approx([math.sqrt(365e-4)] * 3)
    assert row["drawdown_365"] == 0.0  # a new high
    assert row["volume_7_30"] == pytest.approx(4.0 / ((23 + 7 * 4.0) / 30))
    assert row["taker_buy_7"] == pytest.approx(0.6)
    assert row["other_ret_30"] == pytest.approx(0.06)


def test_drawdown_is_from_the_highest_close_of_the_last_365_days():
    bars = _bars(400)
    bars.loc[399, "close"] = 0.8 * bars.loc[398, "close"]
    assert _features(bars).iloc[-1]["drawdown_365"] == pytest.approx(-0.2)


def test_the_first_complete_row_comes_after_365_days():
    X = _features(_bars(400))
    assert X.notna().all(axis=1).idxmax() == BASE + 365 * DAY


def test_a_missing_day_blanks_every_window_that_spans_it():
    bars = _bars(400).drop(index=390)
    X = _features(bars)
    assert X.loc[BASE + 390 * DAY, ["ret_1", "trend_7", "volume_7_30"]].isna().all()
    assert np.isnan(X.loc[BASE + 396 * DAY, "trend_7"])  # its 7-day window spans day 390
    assert not np.isnan(X.loc[BASE + 397 * DAY, "trend_7"])


def test_future_bars_never_change_a_feature():  # spec §4.4 look-ahead
    rng = np.random.default_rng(20261002)
    bars = _bars(500, quote=rng.uniform(1, 2, 500))
    before = _features(bars)
    cut = 450
    later = bars.copy()
    later.loc[cut:, ["close", "quote_volume", "taker_buy_quote_volume"]] *= rng.uniform(
        0.5, 2.0, (500 - cut, 3))
    after = _features(later)
    pd.testing.assert_frame_equal(before.iloc[:cut], after.iloc[:cut])
    assert not before.iloc[cut:].equals(after.iloc[cut:])
