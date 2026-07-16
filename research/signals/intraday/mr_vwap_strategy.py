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

import pandas as pd

from research import config
from app.intraday.strategy import Z_ENTRY, Z_RECOVER, build_weights  # noqa: F401

PIT_TOP_N = 30
PIT_WINDOW_DAYS = 30


def pit_top30_mask(df_1d_long: pd.DataFrame, index_15m: pd.Index,
                   columns: pd.Index) -> pd.DataFrame:
    qv = df_1d_long.pivot(index="open_time", columns="symbol",
                          values="quote_volume").sort_index()
    med = qv.rolling(PIT_WINDOW_DAYS, min_periods=PIT_WINDOW_DAYS).median()
    rank = med.rank(axis=1, ascending=False)
    mask_1d = rank <= PIT_TOP_N
    # a day's bar covers [open, open+1d); its ranking is known at close and
    # applies from the NEXT ms onward — shift the effective index by one day
    mask_1d.index = mask_1d.index + config.DAY_MS
    out = (
        mask_1d.reindex(mask_1d.index.union(index_15m)).sort_index().ffill()
        .loc[index_15m]
        .reindex(columns=columns)
        .fillna(False)
        .astype(bool)
    )
    return out
