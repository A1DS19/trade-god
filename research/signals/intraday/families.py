"""The six pre-registered intraday signal families (Phase 2a).

Each builder: data dict (long warehouse frames) -> bucket-label panel
(index=open_time, columns=symbol). Bucket edges, horizons, and hypotheses
are pre-registered in docs/superpowers/plans/2026-07-15-intraday-edge-hunt.md
and MUST NOT change after the real-data run.

Family 5 note: the spec's "volume/OI impulse" runs as volume/taker-flow only —
Binance serves ~30 trailing days of OI, so no OI history exists in the train
window. Recorded as a known limitation in the Phase 2a report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.signals.intraday.harness import FamilySpec, cut_panel

BARS_1H = 4
BARS_24H = 96
BARS_7D = 672


def _close(data):
    return sdata.to_panel(data["klines_15m"], "close")


def breakout_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    hi = close.rolling(BARS_24H, min_periods=BARS_24H).max().shift(1)
    lo = close.rolling(BARS_24H, min_periods=BARS_24H).min().shift(1)
    rng = hi - lo
    pos = (close - lo) / rng.where(rng > 0)
    return cut_panel(
        pos,
        [-np.inf, 0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0, np.inf],
        ["break_down", "0-.1", ".1-.25", ".25-.5", ".5-.75", ".75-.9",
         ".9-1", "break_up"],
    )


def mr_vwap_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    v = sdata.to_panel(data["klines_15m"], "volume")
    qv = sdata.to_panel(data["klines_15m"], "quote_volume")
    vsum = v.rolling(BARS_24H, min_periods=BARS_24H).sum()
    vwap = qv.rolling(BARS_24H, min_periods=BARS_24H).sum() / vsum.where(vsum > 0)
    sd = close.rolling(BARS_24H, min_periods=BARS_24H).std()
    z = (close - vwap) / sd.where(sd > 0)
    return cut_panel(
        z,
        [-np.inf, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, np.inf],
        ["z<-3", "z-3..-2", "z-2..-1", "z-1..1", "z1..2", "z2..3", "z>3"],
    )


def squeeze_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    ret = close.pct_change()
    short_vol = ret.rolling(BARS_24H, min_periods=BARS_24H).std()
    long_vol = ret.rolling(BARS_7D, min_periods=BARS_7D).std()
    ratio = short_vol / long_vol.where(long_vol > 0)
    return cut_panel(
        ratio,
        [0.0, 0.4, 0.6, 0.8, 1.0, 1.25, np.inf],
        ["r<.4", ".4-.6", ".6-.8", ".8-1", "1-1.25", ">1.25"],
    )


FAMILIES: list[FamilySpec] = [
    FamilySpec(
        name="breakout", build=breakout_buckets,
        extreme={"break_up": 1, "break_down": -1},
        middle=[".25-.5", ".5-.75"],
        horizons_bars=(4, 16, 32, 96),
    ),
    FamilySpec(
        name="mr_vwap", build=mr_vwap_buckets,
        extreme={"z<-3": 1, "z>3": -1},
        middle=["z-1..1"],
        horizons_bars=(1, 4, 16, 32),
    ),
    FamilySpec(
        name="squeeze", build=squeeze_buckets,
        extreme={"r<.4": 1, ".4-.6": 1},
        middle=[".8-1", "1-1.25"],
        horizons_bars=(16, 32, 96),
        abs_mode=True,
    ),
]
