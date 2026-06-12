"""Cross-sectional momentum signal — build_weights(data, params).

Hypothesis: relative strength persists. Every `rebalance_hours` (B), rank
eligible symbols by trailing `lookback_days` (R) return (optionally divided by
realized vol); go long the top-K and short the bottom-K, dollar-neutral,
gross exposure 1.0, forward-filled between rebalances.

Semantics
---------
- Returned weights are DECIDED weights on the full hourly grid (index =
  open_time epoch-ms, columns = symbol). The siglib engine applies its own
  one-bar shift, so no shifting happens here.
- Rebalance bars are wall-clock anchored: bars whose open_time satisfies
  (open_time // 1h) % B == 0 (B=24 -> the 00:00 UTC bar; B=168 -> Thursday
  00:00 UTC). Deterministic, no tuning.
- Eligibility: siglib's 60-day rule masks scores BEFORE ranking, so an
  ineligible symbol can never be selected. `data` must therefore contain each
  symbol's FULL history from listing (plus at least R days + 60 days of warmup
  before the first bar you intend to evaluate).
- Breadth guard (fixed, not tuned): a rebalance with fewer than
  max(2*K, MIN_BREADTH) valid scores produces a flat book until the next
  rebalance (early-history protection; legs never overlap).

`data`: either the long klines frame from siglib.data.load_klines(...,
interval='1h') or a dict containing it under 'klines_1h' (or 'klines').

params (params.json schema):
    lookback_days   R: trailing-return window in days
    k               K: positions per leg
    rebalance_hours B: decision spacing in hours
    vol_norm        bool: rank on ret/vol instead of raw ret
    leg             'ls' (dollar-neutral, default) | 'long' | 'short'
                    (single legs are for the survivorship-bias report; each
                    leg alone is normalized to gross 1.0)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import HOUR_MS
from research.siglib.data import eligible_mask, to_panel

MIN_BREADTH = 10  # fixed constant, not part of the search grid


def prepare_panels(klines_1h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Long 1h klines -> (close panel, eligibility panel) on a complete hourly grid.

    The complete grid makes positional shifts time-exact (a missing bar for
    every symbol at once would otherwise corrupt lookback alignment).
    """
    close = to_panel(klines_1h, "close")
    grid = pd.Index(
        np.arange(int(close.index[0]), int(close.index[-1]) + HOUR_MS, HOUR_MS),
        name="open_time",
    )
    close = close.reindex(grid)
    # eligibility is monotone in time per symbol, so ffill across grid holes is exact
    elig = (
        eligible_mask(klines_1h)
        .astype(float)
        .reindex(grid)
        .ffill()
        .fillna(0.0)
        .astype(bool)
        .reindex(columns=close.columns)
        .fillna(False)
    )
    return close, elig


def compute_score(close: pd.DataFrame, lookback_days: int, vol_norm: bool) -> pd.DataFrame:
    """Trailing R-day return, optionally divided by realized hourly vol over the
    same window (scale is irrelevant — only the cross-sectional rank is used)."""
    n = lookback_days * 24
    score = close / close.shift(n) - 1.0
    if vol_norm:
        hourly = close.pct_change(fill_method=None)
        vol = hourly.rolling(n, min_periods=max(24, int(n * 0.8))).std()
        score = score / vol.where(vol > 0)
    return score


def weights_from_panels(
    close: pd.DataFrame, elig: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """Decided-weights panel from prepared panels (see module docstring)."""
    r = int(params["lookback_days"])
    k = int(params["k"])
    b = int(params["rebalance_hours"])
    vol_norm = bool(params.get("vol_norm", False))
    leg = params.get("leg", "ls")
    if leg not in ("ls", "long", "short"):
        raise ValueError(f"unknown leg {leg!r}")

    score = compute_score(close, r, vol_norm).where(elig)

    rb_mask = (close.index.to_numpy() // HOUR_MS) % b == 0
    s = score.loc[rb_mask]
    n_valid = s.notna().sum(axis=1)
    rank = s.rank(axis=1, method="first")  # 1..n_valid; NaN stays NaN

    long_m = rank.gt(n_valid - k, axis=0)  # top-K by score
    short_m = rank.le(k)                   # bottom-K
    w_long = {"ls": 0.5 / k, "long": 1.0 / k, "short": 0.0}[leg]
    w_short = {"ls": -0.5 / k, "long": 0.0, "short": -1.0 / k}[leg]

    w_rb = long_m.astype(float) * w_long + short_m.astype(float) * w_short
    tradable = (n_valid >= max(2 * k, MIN_BREADTH)).astype(float)
    w_rb = w_rb.mul(tradable, axis=0)

    return w_rb.reindex(close.index).ffill().fillna(0.0)


def build_weights(data, params: dict) -> pd.DataFrame:
    """Entry point for the OOS evaluator. See module docstring for `data`/`params`."""
    if isinstance(data, dict):
        klines = data.get("klines_1h", data.get("klines"))
        if klines is None:
            raise ValueError("data dict needs 'klines_1h' (long 1h klines frame)")
    else:
        klines = data
    close, elig = prepare_panels(klines)
    return weights_from_panels(close, elig, params)
