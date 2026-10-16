"""The timing arms' models (spec 2026-10-02 §2.2, §2.4, as amended): a LightGBM classifier for
direction, and the HAR forecast of volatility that sizes the position."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from research.signals.model_lab.labels import HORIZON_DAYS

# The only search (§2.4). The names are LightGBM's scikit-learn aliases, which lightgbm.train
# accepts as they are; n_estimators is the number of boosting rounds.
SETTINGS = {
    "S1": {"num_leaves": 7, "max_depth": 3, "learning_rate": 0.03, "n_estimators": 300,
           "min_child_samples": 100, "subsample": 0.8, "subsample_freq": 1,
           "colsample_bytree": 0.8, "reg_lambda": 1.0},
    "S2": {"num_leaves": 15, "max_depth": 4, "learning_rate": 0.03, "n_estimators": 600,
           "min_child_samples": 50, "subsample": 0.8, "subsample_freq": 1,
           "colsample_bytree": 0.8, "reg_lambda": 1.0},
}
# Fixed for both settings. LightGBM's documentation asks for force_row_wise (or col-wise)
# whenever deterministic is on, and one thread makes the fixed thread count trivially the same
# on every machine.
FIXED_PARAMS = {"random_state": 20261002, "deterministic": True, "force_row_wise": True,
                "num_threads": 1, "verbose": -1}
THRESHOLD = 0.5
HAR_TERMS = ["rv_d", "rv_w", "rv_m"]
SIGMA_STAR_DAYS = 365


def lightgbm_params(setting: str) -> dict:
    """Everything lightgbm.train is given for a setting, as frozen_params.json records it."""
    return {"objective": "binary", **SETTINGS[setting], **FIXED_PARAMS}


def fit_direction(X: pd.DataFrame, y: pd.Series, setting: str) -> lgb.Booster:
    """A binary classifier of the 7-day label under one of the two settings."""
    params = lightgbm_params(setting)
    rounds = params.pop("n_estimators")
    return lgb.train(params, lgb.Dataset(X, label=y), num_boost_round=rounds)


def har_terms(rv: pd.Series) -> pd.DataFrame:
    """The HAR regressors at each day: RV_t, mean(RV[t−6..t]) and mean(RV[t−29..t])."""
    return pd.DataFrame({"rv_d": rv, "rv_w": rv.rolling(7).mean(), "rv_m": rv.rolling(30).mean()})


def har_target(rv: pd.Series) -> pd.Series:
    """What HAR forecasts: mean(RV[t+1..t+7]), the next 7 days' mean daily variance."""
    return rv.rolling(HORIZON_DAYS).mean().shift(-HORIZON_DAYS)


def fit_har(terms: pd.DataFrame, target: pd.Series) -> np.ndarray:
    """OLS coefficients (b0, b_d, b_w, b_m), fitted on the rows where all four values exist."""
    rows = terms.assign(target=target).dropna()
    x = np.column_stack([np.ones(len(rows)), rows[HAR_TERMS].to_numpy()])
    coef, *_ = np.linalg.lstsq(x, rows["target"].to_numpy(), rcond=None)
    return coef


def har_forecast(coef: np.ndarray, terms: pd.DataFrame) -> pd.Series:
    """b0 + b_d·RV_t + b_w·RV_week + b_m·RV_month at each row of `terms`."""
    return coef[0] + terms[HAR_TERMS] @ coef[1:]


def size_scale(sigma_hat: pd.Series) -> pd.Series:
    """v_t = min(1, σ*_t / σ̂_t), where σ* is the median σ̂ over the trailing 365 days.

    A σ̂ of 0 gives v = 1, the limit as the forecast falls. NaN until 365 days of σ̂ exist."""
    sigma_star = sigma_hat.rolling(SIGMA_STAR_DAYS).median()
    return (sigma_star / sigma_hat).clip(upper=1.0)
