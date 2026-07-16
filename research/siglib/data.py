"""Warehouse loading + panel helpers.

All timestamps are epoch milliseconds (UTC), matching the warehouse parquets.
`start` is inclusive, `end` exclusive, and either may be an epoch-ms int, a
parseable datetime string, or a pandas Timestamp (naive = UTC).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research import config, store

# A symbol is tradable at time T only if it has >= this many days of 1h history before T.
ELIGIBILITY_DAYS = 60

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "quote_volume", "taker_buy_volume", "trades"]
FUNDING_COLS = ["funding_time", "funding_rate", "mark_price"]
PREMIUM_COLS = ["open_time", "open", "high", "low", "close"]


def to_ms(t) -> int | None:
    """Coerce None / epoch-ms number / datetime-like to epoch milliseconds (naive = UTC).

    Floats (which arise from numpy arithmetic on ms indices) are epoch ms too —
    they must NOT fall through to pd.Timestamp, which would read them as
    nanoseconds and silently produce 1970 timestamps.
    """
    if t is None:
        return None
    if isinstance(t, (int, np.integer)) and not isinstance(t, bool):
        return int(t)
    if isinstance(t, (float, np.floating)):
        if not np.isfinite(t):
            raise ValueError(f"non-finite timestamp: {t!r}")
        return int(round(float(t)))
    ts = pd.Timestamp(t)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return int(ts.value // 1_000_000)


def list_symbols(dataset: str = "klines_1h") -> list[str]:
    """Symbols present in the warehouse for a dataset (sorted)."""
    d = config.WAREHOUSE_DIR / dataset
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


def _load_dataset(dataset, symbols, time_col, cols, start, end) -> pd.DataFrame:
    if isinstance(symbols, str):
        symbols = list_symbols(dataset) if symbols == "all" else [symbols]
    start_ms, end_ms = to_ms(start), to_ms(end)
    frames = []
    for sym in symbols:
        df = store.load(dataset, sym)
        if df.empty:
            continue
        df = df[[c for c in cols if c in df.columns]]
        if start_ms is not None:
            df = df[df[time_col] >= start_ms]
        if end_ms is not None:
            df = df[df[time_col] < end_ms]
        if df.empty:
            continue
        df = df.copy()
        df.insert(0, "symbol", sym)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", *cols])
    return pd.concat(frames, ignore_index=True).sort_values(
        ["symbol", time_col], ignore_index=True
    )


def load_klines(symbols="all", interval: str = "1h", start=None, end=None) -> pd.DataFrame:
    """Long klines frame: [symbol, open_time, open, high, low, close, volume, quote_volume]."""
    dataset = f"klines_{interval}"
    if dataset not in config.DATASETS:
        raise ValueError(f"unknown interval {interval!r}")
    return _load_dataset(dataset, symbols, "open_time", KLINE_COLS, start, end)


def load_funding(symbols="all", start=None, end=None) -> pd.DataFrame:
    """Long funding frame: [symbol, funding_time, funding_rate, mark_price].

    funding_time carries ms jitter (events land slightly past the 8h boundary).
    """
    return _load_dataset("funding", symbols, "funding_time", FUNDING_COLS, start, end)


def load_premium(symbols="all", start=None, end=None) -> pd.DataFrame:
    """Long premium-index frame: [symbol, open_time, open, high, low, close]."""
    return _load_dataset("premium_index_1h", symbols, "open_time", PREMIUM_COLS, start, end)


def eligible_mask(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Boolean panel (index=open_time, columns=symbol) of the 60-day eligibility rule.

    True at time T iff the symbol's first 1h bar in `df_1h` is at least
    ELIGIBILITY_DAYS before T. Purely time-based: it does not check for gaps or
    bar presence at T itself — NaN prices in the backtest engine handle that.
    NOTE: pass the symbol's FULL history (not a window starting mid-life), else
    the first observed bar overstates the listing date and delays eligibility.
    """
    first = df_1h.groupby("symbol")["open_time"].min().sort_index()
    idx = np.sort(df_1h["open_time"].unique())
    threshold = first.to_numpy() + ELIGIBILITY_DAYS * config.DAY_MS
    return pd.DataFrame(
        idx[:, None] >= threshold[None, :],
        index=pd.Index(idx, name="open_time"),
        columns=first.index,
    )


def to_panel(df: pd.DataFrame, col: str, time_col: str = "open_time") -> pd.DataFrame:
    """Pivot a long frame to wide: index=time_col, columns=symbol, values=col."""
    return df.pivot(index=time_col, columns="symbol", values=col).sort_index()
