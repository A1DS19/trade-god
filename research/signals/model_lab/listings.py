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


def _tagged(daily: pd.DataFrame) -> pd.DataFrame:
    """The rows with their ticker, their contract number, and whether a settled folder holds them."""
    df = daily.assign(ticker=daily["symbol"].map(lambda s: settled_base(s) or s))
    return df.assign(contract=contract_numbers(df), from_folder=df["symbol"] != df["ticker"])


def split_listings(daily: pd.DataFrame) -> pd.DataFrame:
    """Archive daily klines (live and settled folders, long format) → listings.

    Keeps traded bars only, one row per listing and day. `symbol` becomes the listing's name and
    the raw ticker moves to `ticker`. The latest listing of a ticker keeps the ticker's name;
    earlier ones are TICKER@YYYY-MM-DD, after their first day."""
    df = _tagged(daily)
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


def data_holes(daily: pd.DataFrame) -> pd.DataFrame:
    """Days missing inside a contract's span, after settled folders fill what they can.

    A halt shows up as zero-trade bars, not as missing days, so every hole here is absent data:
    it ends a listing and forces a held position out. Columns: ticker, after (the last day before
    the hole) and missing_days."""
    df = (_tagged(daily).sort_values(["ticker", "contract", "open_time"])
            .drop_duplicates(["ticker", "contract", "open_time"]))
    step = df.groupby(["ticker", "contract"])["open_time"].diff()
    hole = step > DAY_MS
    return pd.DataFrame({
        "ticker": df.loc[hole, "ticker"],
        "after": (df.loc[hole, "open_time"] - step[hole]).astype("int64"),
        "missing_days": (step[hole] // DAY_MS - 1).astype("int64"),
    }).reset_index(drop=True)


def settled_conflicts(daily: pd.DataFrame, rel_tol: float = 1e-9) -> pd.DataFrame:
    """Settled-folder rows that the contract rule could put in the wrong listing.

    - "traded last bar": a folder's last bar has trades on a day its live folder also holds. The
      rule gives that live bar to the next contract, though it may belong to the old one.
    - "close disagrees": both folders hold a day for the same contract with different closes, and
      split_listings keeps the live one.
    None of the 17 folders did either on 2026-10-05. Columns: symbol (the folder), open_time, kind."""
    df = _tagged(daily)
    live, folders = df[~df["from_folder"]], df[df["from_folder"]]
    last = folders.loc[folders.groupby("symbol")["open_time"].idxmax()]
    traded = last[last["trades"] > 0].merge(live[["ticker", "open_time"]], on=["ticker", "open_time"])
    both = folders.merge(live, on=["ticker", "contract", "open_time"], suffixes=("", "_live"))
    disagree = both[(both["close"] - both["close_live"]).abs() > rel_tol * both["close_live"].abs()]
    return pd.concat([traded.assign(kind="traded last bar"), disagree.assign(kind="close disagrees")],
                     ignore_index=True)[["symbol", "open_time", "kind"]]
