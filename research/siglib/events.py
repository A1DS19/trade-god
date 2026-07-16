"""Event studies: conditional forward returns by signal bucket.

Honest-stats caveat: forward returns at horizons > 1h overlap across adjacent
hourly observations, so the per-bucket t-stats reported here are NOT
Newey-West corrected and overstate significance for long horizons. They are
descriptive only; treat them as ranking devices, not hypothesis tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_HORIZONS = (1, 4, 8, 24, 72, 168)


def event_study(
    panel_close: pd.DataFrame,
    signal_panel: pd.DataFrame,
    horizons_hours=DEFAULT_HORIZONS,
    absolute: bool = False,
) -> pd.DataFrame:
    """Conditional forward-return stats per signal bucket and horizon.

    panel_close: wide close prices (index=open_time, columns=symbol).
    signal_panel: same shape, values are bucket labels (caller buckets the raw
        signal, e.g. deciles); NaN cells are excluded.
    Forward return at horizon h: close[t+h]/close[t] - 1, aligned so the
    signal observed at t predicts the NEXT h hours (the backtest engine adds
    its own one-bar shift; here the convention is forward-from-t).
    absolute=True studies |forward return| (movement magnitude, direction-free).

    Returns long DataFrame: [bucket, horizon_hours, count, mean, median, std, t_stat].
    t_stat = mean / (std / sqrt(count)) — see module caveat re overlap.
    """
    sig = signal_panel.stack().dropna()
    sig.name = "bucket"
    out = []
    for h in horizons_hours:
        fwd = (panel_close.shift(-h) / panel_close - 1.0).stack().dropna()
        if absolute:
            fwd = fwd.abs()
        fwd.name = "fwd"
        joined = pd.concat([sig, fwd], axis=1, join="inner").dropna()
        stats = joined.groupby("bucket")["fwd"].agg(
            count="count", mean="mean", median="median", std="std"
        )
        stats["t_stat"] = stats["mean"] / (stats["std"] / np.sqrt(stats["count"]))
        stats["horizon_hours"] = h
        out.append(stats.reset_index())
    cols = ["bucket", "horizon_hours", "count", "mean", "median", "std", "t_stat"]
    return pd.concat(out, ignore_index=True)[cols]
