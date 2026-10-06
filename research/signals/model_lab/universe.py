"""Point-in-time top-50 universe for the ranker (spec 2026-10-02 §1.2, as amended).

Decision dates are Mondays 00:00 UTC, and a decision on date d sees only bars that closed by d
(open_time < d). A listing (see listings.py) is eligible on d when all of these hold:
- it has at least ELIGIBILITY_DAYS (60) daily bars before d;
- it has a bar on d - 1 day;
- its ticker is not in exclusions.EXCLUDED.

Eligible listings rank by quote volume summed over [d - 30 days, d - 1 day], with ties broken by
name, and the top TOP_N form the week's universe. A week with fewer than MIN_BREADTH eligible
listings has no universe, so the book holds nothing that week.

    python -m research.signals.model_lab.universe     # summary over the archive, for review
"""

from __future__ import annotations

import pandas as pd

from research.config import DAY_MS
from research.siglib.data import ELIGIBILITY_DAYS, load_klines, to_ms, week_start
from research.signals.model_lab.exclusions import EXCLUDED
from research.signals.model_lab.listings import settlement_mismatches, split_listings

TOP_N = 50
MIN_BREADTH = 20
VOLUME_WINDOW_DAYS = 30
WEEK_MS = 7 * DAY_MS


def mondays(start, end) -> list[int]:
    """Decision dates: every Monday 00:00 UTC in [start, end), as epoch ms."""
    start_ms, end_ms = to_ms(start), to_ms(end)
    first = int(week_start(start_ms))
    if first < start_ms:
        first += WEEK_MS
    return list(range(first, end_ms, WEEK_MS))


def build_universe(listings: pd.DataFrame, dates: list[int],
                   excluded: frozenset[str] = EXCLUDED) -> pd.DataFrame:
    """Long frame [decision_time, rank, symbol, ticker, quote_volume_30d], one row per member."""
    tickers = listings.groupby("symbol")["ticker"].first()
    volume = listings.pivot(index="open_time", columns="symbol", values="quote_volume").sort_index()
    volume = volume.reindex(range(int(volume.index[0]), int(volume.index[-1]) + DAY_MS, DAY_MS))
    bars = volume.notna().cumsum()  # bars with open_time <= each row
    window = volume.rolling(VOLUME_WINDOW_DAYS, min_periods=1).sum()
    allowed = ~tickers.reindex(volume.columns).isin(excluded)
    members = []
    for d in dates:
        prev = d - DAY_MS
        if prev not in volume.index:
            continue
        eligible = (bars.loc[prev] >= ELIGIBILITY_DAYS) & volume.loc[prev].notna() & allowed
        if eligible.sum() < MIN_BREADTH:
            continue
        ranked = (window.loc[prev][eligible].rename("quote_volume_30d").rename_axis("symbol")
                  .reset_index()
                  .sort_values(["quote_volume_30d", "symbol"], ascending=[False, True])
                  .head(TOP_N))
        members.append(ranked.assign(decision_time=d, rank=range(1, len(ranked) + 1)))
    columns = ["decision_time", "rank", "symbol", "ticker", "quote_volume_30d"]
    if not members:
        return pd.DataFrame(columns=columns)
    out = pd.concat(members, ignore_index=True)
    return out.assign(ticker=out["symbol"].map(tickers))[columns]


def main() -> None:
    daily = load_klines("all", "1d", source="archive_um_klines")
    listed = split_listings(daily)
    per_ticker = listed.groupby("ticker")["symbol"].nunique()
    print(f"{daily['symbol'].nunique()} archive folders -> {listed['symbol'].nunique()} listings "
          f"over {len(per_ticker)} tickers; {int((per_ticker > 1).sum())} tickers have more than one")
    mismatched = settlement_mismatches(daily)
    print(f"settlement check: {len(mismatched)} halts where the last traded close is not the halt price")
    for row in mismatched.head(20).itertuples():
        print(f"  {row.symbol:<24} last close {row.close} vs halt price {row.halt_close}")

    end = int(listed["open_time"].max()) + DAY_MS
    members = build_universe(listed, mondays(int(listed["open_time"].min()), end))
    last_bar = listed.groupby("symbol")["open_time"].max()
    members = members.assign(
        year=pd.to_datetime(members["decision_time"], unit="ms", utc=True).dt.year,
        ended_early=members["symbol"].map(last_bar) < end - WEEK_MS,
    )
    per_listing = members.drop_duplicates(["year", "symbol"])
    summary = pd.DataFrame({
        "weeks": members.groupby("year")["decision_time"].nunique(),
        "listings": per_listing.groupby("year").size(),
        "of_which_ended_before_the_data": per_listing.groupby("year")["ended_early"].sum(),
    })
    print(f"\n{members['decision_time'].nunique()} weeks with a universe; per year, the listings "
          f"that were members and how many of them later delisted, settled or were relisted:")
    print(summary.to_string())


if __name__ == "__main__":
    main()
