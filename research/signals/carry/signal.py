"""Funding-rate carry signal.

Hypothesis: extreme funding marks crowded positioning. When the (trailing-mean)
funding rate exceeds +X bps/8h (or a rolling percentile), go SHORT — collect
funding and fade crowded longs; below -X, go LONG. Hold until funding
normalizes (hysteresis exit). Max K concurrent positions ranked by |funding|.

All PnL flows through research.siglib (this module only builds target weights).

Interface (consumed by the OOS evaluator):
    build_weights(data, params) -> hourly target-weights panel
        index = open_time ms, columns = symbol, values = signed weights with
        gross exposure 1.0 split equally across open positions.
    `data` is a dict with long frames:
        'klines_1h': [symbol, open_time, ..., close, ...]
        'funding':   [symbol, funding_time, funding_rate]
    If `data` is None (or a key is missing) the full warehouse is loaded via
    siglib. Weights at bar t use only information available at bar t close
    (funding events are floored to the hour they settle in; the engine applies
    w[t] to bar t+1 — next-bar execution per protocol).

`params` keys:
    form:      'abs' (threshold in bps/8h) or 'pct' (rolling 30d percentile)
    x:         threshold — bps/8h for 'abs'; entry percentile (e.g. 0.95) for 'pct'
    m_events:  trailing mean over M funding events (M=1 -> current rate)
    k_max:     max concurrent positions (ranked by |smoothed funding|)
    exit_frac: ('abs' only) exit when |smoothed| <= exit_frac * x (hysteresis;
               1.0 = no hysteresis)
    filter:    'none' or 'trend72' (shorts require trailing 72h return <= 0,
               longs >= 0 — don't fade a market still running against you)

Fixed implementation constants (pre-registered, NOT tuned):
    PCT_WINDOW_H / PCT_MIN_PERIODS: 30d rolling percentile window (720h / 360h)
    PCT_EXIT_BUFFER: percentile hysteresis 0.10
    PCT_ABS_FLOOR_BPS: 'pct' entries also need |rate| >= 2 bps/8h (a symbol
        pinned at the 1 bp default can hit a high percentile on noise)
    FFILL_LIMIT_H: funding state goes stale (-> flat) after 48h without events
    TREND_HOURS: 72h lookback for the optional trend filter
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.siglib import data as sdata

HOUR_MS = 3_600_000
BPS = 1e-4

PCT_WINDOW_H = 720
PCT_MIN_PERIODS = 360
PCT_EXIT_BUFFER = 0.10
PCT_ABS_FLOOR_BPS = 2.0
FFILL_LIMIT_H = 48
TREND_HOURS = 72

# Defaults == the frozen params (params.json) so build_weights(data) alone
# reproduces the frozen signal.
DEFAULT_PARAMS = {
    "form": "abs",
    "x": 20.0,
    "m_events": 1,
    "k_max": 3,
    "exit_frac": 1.0,
    "filter": "trend72",
}


def funding_state_panel(funding: pd.DataFrame, index: pd.Index, m_events: int) -> pd.DataFrame:
    """Hourly panel of trailing-M-event mean funding, normalized to bps-per-8h
    equivalents as fractions (i.e. a 4h-interval 0.01% event counts as 0.02%/8h).

    A funding event settling at F (8h-boundary + ms jitter) is assigned to the
    hourly bar open_time = floor(F): that bar closes at floor(F)+1h >= F, so the
    value is known by the time the bar-close decision is made. Forward-filled
    between events, stale after FFILL_LIMIT_H.
    """
    f = funding.sort_values(["symbol", "funding_time"]).copy()
    # Per-event funding interval in hours (diff to previous event), snapped to
    # the regimes Binance actually uses; gaps/firsts inherit the neighbor regime.
    d = (f.groupby("symbol")["funding_time"].diff() / HOUR_MS).round()
    d = d.where(d.isin([1.0, 2.0, 4.0, 8.0]))
    d = d.groupby(f["symbol"]).ffill()
    d = d.groupby(f["symbol"]).bfill()
    d = d.fillna(8.0)
    f["rate_8h"] = f["funding_rate"] * (8.0 / d)
    f["smoothed"] = (
        f.groupby("symbol")["rate_8h"]
        .rolling(m_events, min_periods=m_events)
        .mean()
        .droplevel(0)
    )
    f["hour"] = (f["funding_time"] // HOUR_MS) * HOUR_MS
    f = f.drop_duplicates(["symbol", "hour"], keep="last")
    panel = f.pivot(index="hour", columns="symbol", values="smoothed")
    full = panel.reindex(index.union(panel.index)).sort_index()
    return full.ffill(limit=FFILL_LIMIT_H).reindex(index)


def rolling_percentile_panel(state: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol rolling 30d percentile rank of the smoothed funding state."""
    return state.rolling(PCT_WINDOW_H, min_periods=PCT_MIN_PERIODS).rank(pct=True)


def _latch(enter: pd.DataFrame, exit_: pd.DataFrame) -> pd.DataFrame:
    """Two-threshold latch: 1 from an `enter` bar until an `exit_` bar (entry
    wins when both fire). Returns float panel in {0, 1}."""
    raw = pd.DataFrame(np.nan, index=enter.index, columns=enter.columns)
    raw = raw.mask(exit_, 0.0)
    raw = raw.mask(enter, 1.0)
    return raw.ffill().fillna(0.0)


def _state_panel(sm: pd.DataFrame, pct: pd.DataFrame | None, params: dict) -> pd.DataFrame:
    """Signed desired-position panel in {-1, 0, +1} (before trend filter / K-cap)."""
    if params["form"] == "abs":
        thr = params["x"] * BPS
        exit_thr = params["exit_frac"] * thr
        short = _latch(sm >= thr, sm <= exit_thr)
        long_ = _latch(sm <= -thr, sm >= -exit_thr)
    elif params["form"] == "pct":
        x = params["x"]
        floor = PCT_ABS_FLOOR_BPS * BPS
        short = _latch((pct >= x) & (sm >= floor), pct <= x - PCT_EXIT_BUFFER)
        long_ = _latch((pct <= 1.0 - x) & (sm <= -floor), pct >= 1.0 - x + PCT_EXIT_BUFFER)
    else:
        raise ValueError(f"unknown form {params['form']!r}")
    return long_ - short


def _apply_trend_filter(state: pd.DataFrame, close: pd.DataFrame, params: dict) -> pd.DataFrame:
    if params.get("filter", "none") == "none":
        return state
    if params["filter"] != "trend72":
        raise ValueError(f"unknown filter {params['filter']!r}")
    trend = close / close.shift(TREND_HOURS) - 1.0
    ok_short = (trend <= 0).fillna(False)
    ok_long = (trend >= 0).fillna(False)
    out = state.where(~((state < 0) & ~ok_short), 0.0)
    return out.where(~((out > 0) & ~ok_long), 0.0)


def weights_from_state(
    state: pd.DataFrame,
    sm: pd.DataFrame,
    tradable: pd.DataFrame,
    k_max: int,
) -> pd.DataFrame:
    """K-cap by |smoothed funding| and split gross 1.0 equally across positions."""
    active = (state != 0) & tradable
    score = sm.abs().where(active)
    if int(active.sum(axis=1).max() or 0) > k_max:
        rank = score.rank(axis=1, ascending=False, method="first")
        active = active & (rank <= k_max)
    chosen = state.where(active, 0.0)
    n_open = (chosen != 0).sum(axis=1)
    return chosen.div(n_open.where(n_open > 0), axis=0).fillna(0.0)


def build_weights(data: dict | None = None, params: dict | None = None) -> pd.DataFrame:
    """Build the hourly target-weights panel (see module docstring)."""
    params = {**DEFAULT_PARAMS, **(params or {})}
    data = data or {}
    klines = data.get("klines_1h")
    if klines is None:
        klines = sdata.load_klines("all", "1h")
    funding = data.get("funding")
    if funding is None:
        funding = sdata.load_funding("all")

    close = sdata.to_panel(klines, "close")
    elig = sdata.eligible_mask(klines).reindex(
        index=close.index, columns=close.columns
    ).fillna(False)
    tradable = elig & close.notna()

    sm = funding_state_panel(funding, close.index, params["m_events"])
    sm = sm.reindex(columns=close.columns)
    pct = rolling_percentile_panel(sm) if params["form"] == "pct" else None

    state = _state_panel(sm, pct, params)
    state = _apply_trend_filter(state, close, params)
    return weights_from_state(state, sm, tradable, params["k_max"])
