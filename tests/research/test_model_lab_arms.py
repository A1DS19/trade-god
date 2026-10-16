"""The timing arms (spec §2.1–2.2, as amended): the 0.2 rebalancing band, next-bar execution
through siglib, and the whole walk-forward pipeline: no look-ahead, a planted signal found, and
nothing found in random walks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.siglib.stats import sharpe, weekly_returns
from research.signals.model_lab import arms
from research.signals.model_lab.features import daily_grid
from research.signals.model_lab.labels import up_label

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC
START, END = "2021-07-01", "2023-07-01"  # the validation decisions


def _rebalanced(s, e, band=arms.BAND):
    idx = BASE + np.arange(len(s)) * DAY
    return arms.rebalance(pd.Series(s, index=idx, dtype=float),
                          pd.Series(e, index=idx, dtype=float), band).tolist()


def test_a_new_signal_moves_at_once_and_a_small_change_waits():
    assert _rebalanced([1, 1, 1, 0, 1], [0.9, 0.75, 0.6, 0.0, 0.5]) == [0.9, 0.9, 0.6, 0.0, 0.5]


def test_a_change_inside_the_band_waits_and_one_beyond_it_moves():
    assert _rebalanced([1, 1, 1], [0.5, 0.69, 0.71]) == [0.5, 0.5, 0.71]


def test_the_band_is_strict():  # a band of 0.25 makes the boundary exact in binary
    assert _rebalanced([1, 1, 1], [0.5, 0.75, 0.875], band=0.25) == [0.5, 0.5, 0.875]


def test_the_book_starts_flat():
    assert _rebalanced([0, 1], [0.0, 0.1]) == [0.0, 0.1]  # the first long is a change of signal


def test_volatility_sizing_alone_moves_only_past_the_band():  # the s ≡ 1 baseline (§3.5)
    assert _rebalanced([1, 1, 1, 1], [1.0, 0.85, 0.79, 1.0]) == [1.0, 1.0, 0.79, 1.0]


def test_a_weight_earns_the_next_day_net_of_costs():
    idx = BASE + np.arange(4) * DAY
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    weights = pd.Series([1.0, 0.0, 0.0, 0.0], index=idx)
    book = arms.run_book(close, weights, BASE + DAY, BASE + 4 * DAY)
    # decided at bar 0, so it earns bar 1 (+10%) less the 10 bp entry; sold on bar 2 at 10 bp
    assert book.returns.tolist() == pytest.approx([0.10 - 0.001, -0.001, 0.0])


def test_buy_and_hold_pays_one_entry():
    idx = BASE + np.arange(4) * DAY
    close = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    book = arms.run_book(close, pd.Series(1.0, index=idx), BASE + DAY, BASE + 4 * DAY)
    assert book.n_trades == 1 and book.trade_costs.sum() == pytest.approx(0.001)


def test_a_book_without_every_close_stops():  # at the window's end it would silently shorten
    idx = BASE + np.arange(3) * DAY
    close = pd.Series([100.0, 110.0, 99.0], index=idx)  # no bar on the window's last day
    with pytest.raises(ValueError, match="no close on 2024-01-04"):
        arms.run_book(close, pd.Series(1.0, index=idx), BASE + DAY, BASE + 4 * DAY)


@pytest.fixture
def fast_trees(monkeypatch):
    """Ten rounds instead of hundreds: the pipeline's plumbing, not the model, is under test."""
    small = {name: {**s, "n_estimators": 10} for name, s in arms.models.SETTINGS.items()}
    monkeypatch.setattr(arms.models, "SETTINGS", small)


def _decide(daily, hourly, arm="btc", setting="S1"):
    asset, _ = arms.TIMING_ARMS[arm]
    return arms.timing_decisions(daily, hourly[asset], arm, setting, START, END)


def test_decisions_cover_the_window_from_the_bar_before_it(spot_market, fast_trees):
    daily, hourly = spot_market(1)
    out = _decide(daily, hourly)
    assert out.index[0] == pd.Timestamp("2021-06-30", tz="UTC").value // 1_000_000
    assert out.index[-1] == pd.Timestamp("2023-06-29", tz="UTC").value // 1_000_000
    assert list(out.columns) == ["p", "sigma_hat", "v", "s", "e", "w"]


def _scrambled_from(frames, cut, rng):
    """Copies of the frames with every price and volume from `cut` on multiplied at random."""
    out = {}
    for symbol, bars in frames.items():
        bars = bars.copy()
        future = bars["open_time"] >= cut
        for col in ("close", "quote_volume", "taker_buy_quote_volume"):
            bars.loc[future, col] *= rng.uniform(0.5, 2.0, int(future.sum()))
        out[symbol] = bars
    return out


def test_future_data_never_changes_a_past_feature_or_decision(spot_market, fast_trees,
                                                              monkeypatch):  # spec §4.4
    # Every feature frame timing_decisions builds, so that the RV (hourly) and cross-asset inputs
    # are checked as wired; ten-round trees can miss a leak in a single feature.
    features = []
    build = arms.feat.timing_features

    def record(*args):
        features.append(build(*args))
        return features[-1]

    monkeypatch.setattr(arms.feat, "timing_features", record)
    daily, hourly = spot_market(2)
    before = _decide(daily, hourly)
    # 3 days after the 2022-07-01 refit: a leaked label would reach past it
    cut = pd.Timestamp("2022-07-04", tz="UTC").value // 1_000_000
    rng = np.random.default_rng(3)
    after = _decide(_scrambled_from(daily, cut, rng), _scrambled_from(hourly, cut, rng))
    pd.testing.assert_frame_equal(before[before.index < cut], after[after.index < cut])
    assert not before[before.index >= cut].equals(after[after.index >= cut])
    X_before, X_after = features
    pd.testing.assert_frame_equal(X_before[X_before.index < cut], X_after[X_after.index < cut])


def test_a_decision_without_every_feature_stops_the_run(spot_market, fast_trees):
    daily, hourly = spot_market(1)
    missing = pd.Timestamp("2022-01-10", tz="UTC").value // 1_000_000
    daily["BTCUSDT"] = daily["BTCUSDT"][daily["BTCUSDT"]["open_time"] != missing]
    with pytest.raises(ValueError, match="2022-01-10 lacks a feature"):
        _decide(daily, hourly)


def test_a_probability_of_exactly_one_half_stays_out(spot_market, monkeypatch):
    # A tree model with no split on a balanced training set predicts exactly 0.5 (§2.2: s = 1
    # only when p > 0.5).
    class CoinFlip:
        def predict(self, X):
            return np.full(len(X), 0.5)

    monkeypatch.setattr(arms.models, "fit_direction", lambda X, y, setting: CoinFlip())
    out = _decide(*spot_market(1))
    assert (out["s"] == 0.0).all() and (out["w"] == 0.0).all()


def _hit_rate_and_sharpes(daily, hourly):
    out = _decide(daily, hourly)
    close = daily_grid(daily["BTCUSDT"])["close"]
    label = up_label(close).reindex(out.index)
    hit = float((out["s"] == label)[label.notna()].mean())
    book = arms.run_book(close, out["w"], START, END)
    hold = arms.run_book(close, pd.Series(1.0, index=close.index), START, END)
    return hit, sharpe(weekly_returns(book.returns)), sharpe(weekly_returns(hold.returns))


def test_a_planted_signal_is_found(spot_market):  # spec §4.4 power, with the real settings
    hit, book, hold = _hit_rate_and_sharpes(*spot_market(3, signal=0.01))
    assert hit > 0.55 and book > hold + 1.0


def test_a_random_walk_yields_nothing(spot_market):  # spec §4.4 null
    hit, book, hold = _hit_rate_and_sharpes(*spot_market(1))
    assert 0.43 < hit < 0.57 and book < hold + 0.5
