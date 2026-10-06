"""Resumable backfill of Binance's public archive into the warehouse (spec 2026-10-02 §1.1).

    python -m research.archive_backfill                     # every archive dataset and symbol
    python -m research.archive_backfill --datasets archive_um_klines_1d --symbols BNXUSDT,BNXUSDTSETTLED
    python -m research.archive_backfill --dry-run           # list the work, fetch no data

Run from the DEV machine only. Each run re-lists the archive and downloads only months not yet
stored, so an interrupted run resumes where it stopped. The first full run makes about 137,000
requests, about 22,000 monthly files per UM dataset each with a checksum, and takes roughly a day
at the 0.2 s pacing. The REST warehouse, its datasets and the 05:30 cron are untouched: every
archive dataset has its own folder.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import pandas as pd

from research import archive_source as src
from research import config, store


@dataclass
class Summary:
    new_rows: dict = field(default_factory=dict)  # (dataset, symbol) -> int
    failures: list = field(default_factory=list)  # [(dataset, symbol, month or None)]


def stored_months(dataset: str, symbol: str) -> set[str]:
    """Months ('YYYY-MM') with at least one stored row; those are never downloaded again."""
    time_col, _ = config.DATASETS[dataset]
    df = store.load(dataset, symbol)
    if df.empty:
        return set()
    return set(pd.to_datetime(df[time_col], unit="ms", utc=True).dt.strftime("%Y-%m"))


def work_list(perps: list[str], settled: list[str]) -> dict[str, list[str]]:
    """Symbols per dataset: spot is BTC and ETH only, and settled folders exist for klines only."""
    return {
        "archive_spot_klines_1d": list(src.SPOT_SYMBOLS),
        "archive_spot_klines_1h": list(src.SPOT_SYMBOLS),
        "archive_um_klines_1d": perps + settled,
        "archive_um_funding": perps,
        "archive_um_premium_1d": perps,
    }


def _backfill_one(dataset: str, symbol: str, *, get, delay: float, summary: Summary) -> None:
    try:
        months = src.list_month_keys(dataset, symbol, get=get, delay=delay)
    except Exception as e:
        summary.failures.append((dataset, symbol, None))
        print(f"{symbol:<24} {dataset:<24} listing FAILED: {e}", file=sys.stderr)
        return
    time_col, _ = config.DATASETS[dataset]
    have = stored_months(dataset, symbol)
    added = 0
    for month, key in months.items():
        if month in have:
            continue
        try:
            rows = src.fetch_month(dataset, key, get=get, delay=delay)
            added += store.upsert(dataset, symbol, rows, time_col)
        except Exception as e:
            summary.failures.append((dataset, symbol, month))
            print(f"{symbol:<24} {dataset:<24} {month} FAILED: {e}", file=sys.stderr)
    summary.new_rows[(dataset, symbol)] = added
    print(f"{symbol:<24} {dataset:<24} +{added} rows")


def run(work: dict[str, list[str]], *, get, delay: float) -> Summary:
    summary = Summary()
    for dataset, symbols in work.items():
        for symbol in symbols:
            _backfill_one(dataset, symbol, get=get, delay=delay, summary=summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", default=",".join(src.SOURCES),
                        help=f"subset of: {','.join(src.SOURCES)}")
    parser.add_argument("--symbols", help="comma-separated override, applied to every dataset")
    parser.add_argument("--dry-run", action="store_true", help="list the work, fetch no data")
    args = parser.parse_args()

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    unknown = [d for d in datasets if d not in src.SOURCES]
    if unknown:
        parser.error(f"unknown datasets: {unknown}")

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        work = {d: symbols for d in datasets}
    else:
        perps, settled = src.list_um_symbols(get=src.http_get, delay=config.ARCHIVE_DELAY)
        print(f"Archive listing: {len(perps)} USDT perps, {len(settled)} settled folders")
        everything = work_list(perps, settled)
        work = {d: everything[d] for d in datasets}

    if args.dry_run:
        for dataset, symbols in work.items():
            print(f"{dataset:<24} {len(symbols)} symbols")
        return

    summary = run(work, get=src.http_get, delay=config.ARCHIVE_DELAY)
    total = sum(summary.new_rows.values())
    print(f"\nDone: +{total} rows across {len(summary.new_rows)} tasks; "
          f"{len(summary.failures)} failures")
    if summary.failures:
        for dataset, symbol, month in summary.failures:
            print(f"  FAILED {symbol} {dataset} {month or 'listing'}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
