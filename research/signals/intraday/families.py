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


def funding_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    f = data["funding"].pivot(index="funding_time", columns="symbol",
                              values="funding_rate")
    f = f.reindex(columns=close.columns)
    rate = (
        f.reindex(f.index.union(close.index)).sort_index().ffill()
        .loc[close.index]
    )
    rate = rate.where(close.notna())
    return cut_panel(
        rate,
        [-np.inf, -1e-3, -3e-4, -1e-4, 1e-4, 3e-4, 1e-3, np.inf],
        ["f<-.1%", "-.1..-.03%", "-.03..-.01%", "-.01..+.01%",
         "+.01..+.03%", "+.03..+.1%", "f>+.1%"],
    )


def vol_impulse_buckets(data: dict) -> pd.DataFrame:
    v = sdata.to_panel(data["klines_15m"], "volume")
    tb = sdata.to_panel(data["klines_15m"], "taker_buy_volume")
    imb = (tb / v.where(v > 0)) - 0.5
    base = v.rolling(BARS_24H, min_periods=BARS_24H).mean().shift(1)
    surge = (v / base.where(base > 0)).clip(upper=10.0)
    impulse = imb * surge
    return cut_panel(
        impulse,
        [-np.inf, -1.5, -0.75, -0.25, 0.25, 0.75, 1.5, np.inf],
        ["i<-1.5", "-1.5..-.75", "-.75..-.25", "-.25...25",
         ".25..0.75", ".75..1.5", "i>1.5"],
    )


def tod_buckets(data: dict) -> pd.DataFrame:
    close = _close(data)
    hours = (close.index.to_numpy() // 3_600_000) % 24
    labels = pd.Series([f"h{h:02d}" for h in hours], index=close.index)
    panel = pd.DataFrame(
        np.broadcast_to(labels.to_numpy()[:, None], close.shape).copy(),
        index=close.index, columns=close.columns,
    )
    return panel.where(close.notna())


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

FAMILIES.extend([
    FamilySpec(
        name="funding_window", build=funding_buckets,
        extreme={"f<-.1%": 1, "f>+.1%": -1},
        middle=["-.01..+.01%"],
        horizons_bars=(16, 32, 96),
    ),
    FamilySpec(
        name="vol_impulse", build=vol_impulse_buckets,
        extreme={"i>1.5": 1, "i<-1.5": -1},
        middle=["-.25...25"],
        horizons_bars=(1, 4, 16, 32),
    ),
    FamilySpec(
        name="time_of_day", build=tod_buckets,
        extreme={f"h{h:02d}": 0 for h in range(24)},
        middle=None,
        horizons_bars=(4,),
    ),
])
