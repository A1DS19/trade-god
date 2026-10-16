"""The BTC and ETH timing arms (spec 2026-10-02 §2.1–2.2, §2.4, as amended).

timing_decisions walks the quarterly refits and turns each day's model outputs into the weight
the arm holds; run_book prices those weights through siglib.run_backtest, the only place P&L is
computed."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS
from research.siglib.backtest import BacktestResult, run_backtest
from research.siglib.costs import CostModel
from research.siglib.data import to_ms
from research.signals.model_lab import features as feat
from research.signals.model_lab import models
from research.signals.model_lab.labels import up_label
from research.signals.model_lab.walkforward import model_in_force, quarter_starts, trains_refit

BAND = 0.2
# HAR refits every quarter from here on, so that σ̂ exists point-in-time for the 365 days σ*
# needs before a decision.
HAR_START = "2018-01-01"
TIMING_ARMS = {"btc": ("BTCUSDT", "ETHUSDT"), "eth": ("ETHUSDT", "BTCUSDT")}  # asset, other


def rebalance(s: pd.Series, e: pd.Series, band: float = BAND) -> pd.Series:
    """The weight held after each decision: e_t when s_t differs from the previous s, otherwise
    e_t only if it is more than `band` from the weight held. The book starts flat."""
    held, last_s, out = 0.0, 0.0, []
    for s_t, e_t in zip(s.to_numpy(), e.to_numpy()):
        if s_t != last_s or abs(e_t - held) > band:
            held = e_t
        last_s = s_t
        out.append(held)
    return pd.Series(out, index=e.index)


def _direction(X, y, t, decide, refits, setting) -> np.ndarray:
    """p_t for the decided rows, each from the classifier refit in force at its decision."""
    p = np.full(len(t), np.nan)
    trainable = X.notna().all(axis=1).to_numpy() & y.notna().to_numpy()
    in_force = model_in_force(t, refits)
    for i, refit in enumerate(refits):
        use = decide & (in_force == i)
        if use.any():
            train = trainable & trains_refit(t, refit)
            p[use] = models.fit_direction(X[train], y[train], setting).predict(X[use])
    return p


def _sigma_hat(rv, t, refits) -> pd.Series:
    """σ̂_t at every row from HAR_START on, each from the HAR refit in force at its decision."""
    terms, target = models.har_terms(rv), models.har_target(rv)
    forecast = np.full(len(t), np.nan)
    in_force = model_in_force(t, refits)
    for i, refit in enumerate(refits):
        use = in_force == i
        train = trains_refit(t, refit)
        forecast[use] = models.har_forecast(models.fit_har(terms[train], target[train]), terms[use])
    return feat.annualised_vol(pd.Series(forecast, index=rv.index))


def timing_decisions(daily: dict[str, pd.DataFrame], hourly: pd.DataFrame, arm: str,
                     setting: str, start, end) -> pd.DataFrame:
    """The arm's decisions in [start, end): one row per daily bar t, decided at t + 1 day, with
    columns p, s, sigma_hat, v, e and w (the weight held from that decision on).

    `daily` holds both assets' daily klines, `hourly` the arm's own hourly klines."""
    asset, other = TIMING_ARMS[arm]
    bars = feat.daily_grid(daily[asset])
    rv = feat.daily_rv(hourly).reindex(bars.index)
    X = feat.timing_features(bars, rv, feat.daily_grid(daily[other])["close"])
    t = bars.index.to_numpy()
    decide = (t + DAY_MS >= to_ms(start)) & (t + DAY_MS < to_ms(end))
    incomplete = ~X[decide].notna().all(axis=1)
    if incomplete.any():
        day = pd.Timestamp(incomplete.idxmax(), unit="ms")
        raise ValueError(f"{arm}: the decision on bar {day:%Y-%m-%d} lacks a feature")
    sigma_hat = _sigma_hat(rv, t, quarter_starts(HAR_START, end))
    out = pd.DataFrame({
        "p": _direction(X, up_label(bars["close"]), t, decide, quarter_starts(start, end), setting),
        "sigma_hat": sigma_hat,
        "v": models.size_scale(sigma_hat),
    }, index=bars.index)[decide]
    if out["v"].isna().any():
        raise ValueError(f"{arm}: σ* needs {models.SIGMA_STAR_DAYS} days of σ̂ before {start}")
    out["s"] = (out["p"] > models.THRESHOLD).astype(float)
    out["e"] = out["s"] * out["v"]
    out["w"] = rebalance(out["s"], out["e"])
    return out


def run_book(close: pd.Series, weights: pd.Series, start, end,
             cost_model: CostModel = CostModel()) -> BacktestResult:
    """The book over [start, end) through siglib.run_backtest: the weight decided at bar t earns
    bar t + 1 (§2.1). `close` and `weights` are indexed by bar open_time.

    A day without a close stops the run, like a decision without its features: at the window's
    end, where no decision row exists to fail, it would otherwise silently shorten the book."""
    first, end_ms = to_ms(start) - DAY_MS, to_ms(end)
    prices = close.reindex(np.arange(first, end_ms, DAY_MS)).to_frame("asset")
    missing = prices.index[prices["asset"].isna().to_numpy()]
    if len(missing):
        day = pd.Timestamp(missing[0], unit="ms")
        raise ValueError(f"the book over [{start}, {end}) has no close on {day:%Y-%m-%d}")
    held = weights.reindex(prices.index).fillna(0.0).to_frame("asset")
    return run_backtest(prices, held, cost_model).window(start, end)
