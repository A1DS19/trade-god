"""Phase 2b strategy: long-only mean reversion on deep oversold vs 24h VWAP.

PRE-REGISTERED (2026-07-16 — docs/superpowers/plans/2026-07-16-mr-vwap-2b-backtest.md):
Z_ENTRY = -3.0 and Z_RECOVER = -1.0 are fixed from Phase 2a, never searched.
Two fill models per findings caveat #6:
- next_bar: signal at t -> exposure starts at close[t+1] (taker base case).
- maker_limit: limit bid at close[t]; fills in bar t+1 only on STRICT
  trade-through (low[t+1] < close[t]); exposure starts at close[t] = the
  limit price, matching the engine's w[t] convention. Missed fills skipped.
Slots: 1/K gross each; exits free slots before entries; lowest z first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_ENTRY = -3.0
Z_RECOVER = -1.0
Z_WINDOW = 96   # 24h of 15m bars — the pre-registered mr_vwap window


def zscore(close: pd.DataFrame, volume: pd.DataFrame, quote_volume: pd.DataFrame,
           window: int = Z_WINDOW) -> pd.DataFrame:
    vsum = volume.rolling(window, min_periods=window).sum()
    vwap = quote_volume.rolling(window, min_periods=window).sum() / vsum.where(vsum > 0)
    sd = close.rolling(window, min_periods=window).std()
    return (close - vwap) / sd.where(sd > 0)


def build_weights(z: pd.DataFrame, close: pd.DataFrame, low: pd.DataFrame,
                  elig: pd.DataFrame, params: dict, fill: str) -> pd.DataFrame:
    if fill not in ("next_bar", "maker_limit"):
        raise ValueError(f"unknown fill model {fill!r}")
    horizon = int(params["horizon_bars"])
    exit_mode = params["exit"]
    k = int(params["max_k"])
    slot = 1.0 / k

    idx, cols = z.index, z.columns
    n, m = len(idx), len(cols)
    zv = z.to_numpy()
    cv = close.to_numpy()
    lv = low.to_numpy()
    ev = elig.reindex(index=idx, columns=cols).fillna(False).to_numpy()
    signal = (zv < Z_ENTRY) & ev & np.isfinite(cv)

    w = np.zeros((n, m))
    remaining = np.zeros(m, dtype=int)   # earning bars left per symbol (0 = flat)

    for t in range(n):
        # exits first (horizon exhaustion is the age-down at the end of each
        # bar; z is checked from the first held close onward)
        for s in range(m):
            if remaining[s] > 0 and (
                (exit_mode == "z_recover" and zv[t, s] > Z_RECOVER)
                or not ev[t, s]
            ):
                remaining[s] = 0
        # candidate entries effective THIS bar, most-oversold first
        cands = []
        for s in range(m):
            if remaining[s] > 0:
                continue
            if fill == "next_bar":
                if t >= 1 and signal[t - 1, s]:
                    cands.append((zv[t - 1, s], s))
            else:  # maker_limit: signal at t, strict trade-through in t+1
                if t + 1 < n and signal[t, s] and lv[t + 1, s] < cv[t, s]:
                    cands.append((zv[t, s], s))
        cands.sort()
        free = k - int((remaining > 0).sum())
        for _, s in cands[:free]:
            remaining[s] = horizon
        # write weights and age positions
        for s in range(m):
            if remaining[s] > 0:
                w[t, s] = slot
                remaining[s] -= 1

    return pd.DataFrame(w, index=idx, columns=cols)
