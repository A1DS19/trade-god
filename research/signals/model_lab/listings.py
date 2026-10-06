"""Listings: one contract's tradable life under a ticker (spec 2026-10-02 §1.2, as amended).

The archive keeps one folder per ticker, and a ticker can outlive its contract. On 2026-10-05:
- a settled contract got a flat, zero-trade bar at its settlement price every day until its
  ticker was relisted, and otherwise indefinitely: all 133 settled perps still did (BLZ had sat
  at 0.06836 since 2024-12-23), so without dropping those bars they would never delist;
- a relisted ticker continued the same file at an unrelated price: PUMPUSDT went from the old
  token's 0.0471 to the new token's 0.0052;
- 17 settled folders held old contracts' last days, some of which the live folder lacks: BNX's
  last 11 trading days before its 2023-02 redenomination exist only in BNXUSDTSETTLED.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.archive_source import settled_base
from research.config import DAY_MS


def contract_numbers(daily: pd.DataFrame) -> np.ndarray:
    """Each row's contract within its ticker, counting from 0.

    A settled folder's last bar ends a contract: the folder's rows belong to it, and the live
    folder's rows from that day on belong to the next one."""
    contract = np.zeros(len(daily), dtype=int)
    symbol = daily["symbol"].to_numpy()
    open_time = daily["open_time"].to_numpy()
    folders = daily[daily["symbol"] != daily["ticker"]]
    ends = folders.groupby("symbol")["open_time"].max()
    for ticker, folder_ends in ends.groupby(ends.index.map(settled_base)):
        bounds = np.sort(folder_ends.to_numpy())
        live = symbol == ticker
        contract[live] = np.searchsorted(bounds, open_time[live], side="right")
        for folder, end in folder_ends.items():
            contract[symbol == folder] = np.searchsorted(bounds, end, side="left")
    return contract


def split_listings(daily: pd.DataFrame) -> pd.DataFrame:
    """Archive daily klines (live and settled folders, long format) → listings.

    Keeps traded bars only, one row per listing and day. `symbol` becomes the listing's name and
    the raw ticker moves to `ticker`. The latest listing of a ticker keeps the ticker's name;
    earlier ones are TICKER@YYYY-MM-DD, after their first day."""
    df = daily.assign(ticker=daily["symbol"].map(lambda s: settled_base(s) or s))
    df = df.assign(contract=contract_numbers(df), from_folder=df["symbol"] != df["ticker"])
    df = df[df["trades"] > 0]
    df = (df.sort_values(["ticker", "contract", "open_time", "from_folder"])
            .drop_duplicates(["ticker", "contract", "open_time"], keep="first"))  # live wins
    step = df.groupby(["ticker", "contract"])["open_time"].diff()
    listing = (step != DAY_MS).cumsum()  # NaN marks each contract's first bar
    first = df.groupby(listing)["open_time"].transform("min")
    newest = first == first.groupby(df["ticker"]).transform("max")
    dated = df["ticker"] + "@" + pd.to_datetime(first, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    return (df.assign(symbol=df["ticker"].where(newest, dated))
              .drop(columns=["contract", "from_folder"])
              .reset_index(drop=True))


def settlement_mismatches(daily: pd.DataFrame, rel_tol: float = 1e-9) -> pd.DataFrame:
    """Folders whose last traded close before a halt differs from the halt price.

    The spec's delisting rule assumes the two are equal: the last traded close is the settlement
    price. An empty result confirms it for every halt in the data."""
    df = daily.sort_values(["symbol", "open_time"])
    following = df.groupby("symbol")[["trades", "close"]].shift(-1)
    halts = (df["trades"] > 0) & (following["trades"] == 0)
    rel = (df["close"] - following["close"]).abs() / following["close"].abs()
    hits = df.loc[halts & (rel > rel_tol), ["symbol", "open_time", "close"]]
    return hits.assign(halt_close=following.loc[hits.index, "close"]).reset_index(drop=True)
