"""Premium-index mean reversion (basis_mr) — target-weight builder.

Hypothesis: perp premium/discount extremes mean-revert. The premium-index
close is ranked as a rolling percentile over the last M hours (per symbol).
  - percentile >= P      -> SHORT candidate (rich premium)
  - percentile <= 1 - P  -> LONG candidate (deep discount)
Exit (param `exit_mode`, both pre-registered in the hypothesis family):
  - "median":  percentile crosses back to the median (>= 0.5 for longs,
    <= 0.5 for shorts) OR `horizon_hours` after the LAST bar inside the
    entry zone, whichever comes first.
  - "horizon": pure time-based hold — exit `horizon_hours` after the LAST
    bar inside the entry zone (no median exit). Premium percentiles revert
    to the median within hours, so "median" exits cut holds far shorter
    than the forward-return edge persists; "horizon" lets the position
    breathe.
While the percentile stays in the entry zone the holding clock keeps
refreshing — "be positioned while extreme, then give it up to H hours to
revert".

Portfolio construction (slot-based, NO eviction):
  - max_k slots. An open position keeps its slot until its own exit rule
    fires; it is never displaced by a newer, more extreme candidate (the
    v1 implementation re-ranked every bar and the resulting eviction churn
    traded ~35% of gross per HOUR — pure cost bleed, see study notes).
  - When more new candidates than free slots exist on a bar, admission
    priority is |premium z-score| (over the same M window) on that bar,
    ties broken by column order (deterministic).
  - Gross exposure 1.0 split equally across open positions: w_i = ±1/n_open.
  - A symbol must be eligible (60-day rule) and have a close price to hold
    a slot; losing either closes the position.

All weights are DECIDED at bar t close; the siglib engine applies them to
bar t+1 (next-bar execution). This module never computes PnL.

`data` contract (everything loadable via research.siglib.data):
  data["klines_1h"] : long frame from siglib.data.load_klines("all", ...) —
                      must contain each symbol's FULL history from listing
                      (the 60-day eligibility rule reads the first bar).
  data["premium"]   : long frame from siglib.data.load_premium("all", ...).
  data["cache"]     : OPTIONAL dict; reused across calls to memoize the
                      rolling percentile/z panels per M (study-time speedup;
                      results are identical with or without it).

Gap tolerance (e.g. ICPUSDT's 77-day premium hole in 2022): missing premium
bars produce NaN percentiles -> no entry, no median-exit and no zone refresh
there; an open position simply times out via the horizon. min_periods = 90%
of M so a handful of missing bars inside the window does not silence the
signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.siglib import data as sdata

HOUR_MS = 3_600_000

DEFAULT_PARAMS = {
    "M": 336,           # percentile lookback, hours
    "P": 0.98,          # entry percentile (short >= P, long <= 1-P)
    "horizon_hours": 72,  # max hold after last bar in the entry zone
    "max_k": 5,         # max concurrent positions (slots)
    "exit_mode": "median",  # "median" (median-cross or timeout) | "horizon" (timeout only)
}


def _signal_state(data: dict, M: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(close_panel, premium_percentile_panel, premium_z_panel) for lookback M.

    Memoized in data["cache"] when provided (keyed by M).
    """
    cache = data.get("cache")
    key = f"state_{M}"
    if cache is not None and key in cache:
        return cache[key]

    close = sdata.to_panel(data["klines_1h"], "close")
    prem = (
        sdata.to_panel(data["premium"], "close")
        .reindex(index=close.index, columns=close.columns)
    )
    minp = max(2, int(M * 0.9))
    roll = prem.rolling(M, min_periods=minp)
    pct = roll.rank(pct=True)
    sd = roll.std()
    z = (prem - roll.mean()) / sd.where(sd > 0)

    out = (close, pct, z)
    if cache is not None:
        cache[key] = out
    return out


def build_weights(data: dict, params: dict) -> pd.DataFrame:
    """Hourly target-weights panel (index=open_time ms, columns=symbol).

    See module docstring for the data contract and the exact state machine.
    The per-bar loop is over ~50k bars with O(n_symbols) numpy work — bounded
    and deterministic.
    """
    M = int(params["M"])
    P = float(params["P"])
    H = int(params["horizon_hours"])
    K = int(params["max_k"])
    exit_mode = params.get("exit_mode", "median")
    if exit_mode not in ("median", "horizon"):
        raise ValueError(f"unknown exit_mode {exit_mode!r}")
    median_exit = exit_mode == "median"

    close, pct, z = _signal_state(data, M)
    elig = (
        sdata.eligible_mask(data["klines_1h"])
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
    )

    times = close.index.to_numpy(dtype=np.int64)
    pct_np = pct.to_numpy()
    absz_np = np.abs(z.to_numpy())
    tradable_np = (elig & close.notna()).to_numpy()
    n_t, n_s = pct_np.shape
    h_ms = H * HOUR_MS

    direction = np.zeros(n_s, dtype=np.int8)       # -1 short, 0 flat, +1 long
    last_zone = np.full(n_s, np.iinfo(np.int64).min, dtype=np.int64)
    out = np.zeros((n_t, n_s))

    for t in range(n_t):
        now = times[t]
        p = pct_np[t]
        tradable = tradable_np[t]
        valid = ~np.isnan(p)
        in_long = valid & (p <= 1.0 - P)
        in_short = valid & (p >= P)

        # 1) zone refresh keeps the timeout clock alive while still extreme
        refresh = ((direction == 1) & in_long) | ((direction == -1) & in_short)
        last_zone[refresh] = now

        # 2) exits: (median cross,) timeout, or symbol no longer tradable
        active = direction != 0
        close_mask = active & ~tradable
        if median_exit:
            close_mask |= (direction == 1) & valid & (p >= 0.5)
            close_mask |= (direction == -1) & valid & (p <= 0.5)
        close_mask |= active & (now - last_zone >= h_ms)
        direction[close_mask] = 0

        # 3) entries into free slots, best |z| first (no eviction of holders)
        free = K - int(np.count_nonzero(direction))
        if free > 0:
            cand = tradable & (direction == 0) & (in_long | in_short)
            idxs = np.flatnonzero(cand)
            if idxs.size:
                score = absz_np[t, idxs]
                score = np.where(np.isnan(score), 0.0, score)
                take = idxs[np.argsort(-score, kind="stable")[:free]]
                direction[take] = np.where(in_long[take], 1, -1)
                last_zone[take] = now

        # 4) equal split of gross 1.0 across open positions
        n_open = int(np.count_nonzero(direction))
        if n_open:
            out[t] = direction / n_open

    return pd.DataFrame(out, index=close.index, columns=close.columns)
