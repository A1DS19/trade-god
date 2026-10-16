"""The timing arms' models (spec §2.2, §2.4, as amended): the two pre-registered LightGBM settings,
deterministic; HAR by OLS; σ̂ annualised by √365; v = min(1, σ*/σ̂) with σ* a 365-day median."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import models
from research.signals.model_lab.features import annualised_vol


def test_the_settings_are_the_spec_table():  # §2.4: the only search, fixed before any run
    common = {"learning_rate": 0.03, "subsample": 0.8, "subsample_freq": 1,
              "colsample_bytree": 0.8, "reg_lambda": 1.0}
    assert models.SETTINGS == {
        "S1": {"num_leaves": 7, "max_depth": 3, "n_estimators": 300, "min_child_samples": 100,
               **common},
        "S2": {"num_leaves": 15, "max_depth": 4, "n_estimators": 600, "min_child_samples": 50,
               **common},
    }
    assert models.FIXED_PARAMS["random_state"] == 20261002
    assert models.FIXED_PARAMS["deterministic"] is True


def _learnable(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 3)), columns=["a", "b", "c"])
    y = (X["a"] + rng.normal(scale=0.5, size=n) > 0).astype(float)
    return X, y


def test_the_classifier_is_deterministic_and_runs_every_round():
    X, y = _learnable()
    first, second = (models.fit_direction(X, y, "S1") for _ in range(2))
    assert np.array_equal(first.predict(X), second.predict(X))
    assert first.num_trees() == 300


def test_the_classifier_learns_a_real_pattern():
    X, y = _learnable()
    p = models.fit_direction(X, y, "S2").predict(X)
    assert ((p > models.THRESHOLD) == y).mean() > 0.8


def test_har_target_is_the_next_seven_days_mean():
    rv = pd.Series(np.arange(20, dtype=float))
    assert models.har_target(rv).iloc[0] == pytest.approx(np.mean(np.arange(1, 8)))
    assert models.har_target(rv).iloc[13:].isna().all()  # day 19 is the last known


def test_har_recovers_known_coefficients():
    rng = np.random.default_rng(1)
    rv = pd.Series(rng.uniform(1e-4, 4e-4, 400))
    terms = models.har_terms(rv)
    target = 1e-5 + 0.3 * terms["rv_d"] + 0.4 * terms["rv_w"] + 0.2 * terms["rv_m"]
    coef = models.fit_har(terms, target)
    assert coef == pytest.approx([1e-5, 0.3, 0.4, 0.2])
    assert models.har_forecast(coef, terms).iloc[-1] == pytest.approx(target.iloc[-1])


def test_sigma_hat_is_annualised_and_never_negative():
    assert annualised_vol(pd.Series([1e-4, -1e-5])).tolist() == pytest.approx(
        [math.sqrt(365e-4), 0.0])


def test_size_scale_cuts_exposure_only_above_the_median():
    sigma = pd.Series(np.r_[np.full(365, 0.5), 1.0, 0.25, 0.0])
    v = models.size_scale(sigma)
    assert v.iloc[:364].isna().all()  # σ* needs 365 days of σ̂
    assert v.iloc[364] == 1.0
    assert v.iloc[365] == pytest.approx(0.5)  # σ̂ twice the median
    assert v.iloc[366:].tolist() == [1.0, 1.0]  # below the median, or 0: never above 1
