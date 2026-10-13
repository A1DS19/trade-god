"""Resumable backfill of Binance's public archive into the warehouse (spec 2026-10-02 §1.1).

    python -m research.archive_backfill                     # every archive dataset and symbol
    python -m research.archive_backfill --datasets archive_um_klines_1d --symbols BNXUSDT,BNXUSDTSETTLED
    python -m research.archive_backfill --dry-run           # list the work, fetch no data

Run from the DEV machine only. Each run re-lists the archive and downloads only months not yet
stored, so an interrupted run resumes where it stopped. The first full run makes about 137,000
requests, about 22,000 monthly files per UM dataset each with a checksum. With 8 workers, each
pacing its own requests at 0.2 s, that takes about 3½ hours; one at a time it took about 29. The
REST warehouse, its datasets and the 05:30 cron are untouched: every archive dataset has its own
folder.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial

import pandas as pd

from research import archive_source as src
from research import config, store


@dataclass
class Summary:
    new_rows: dict = field(default_factory=dict)  # (dataset, symbol) -> int
    failures: list = field(default_factory=list)  # [(dataset, symbol, month/day/None=listing)]


def stored_months(dataset: str, symbol: str) -> set[str]:
    """Months ('YYYY-MM') with at least one stored row; those are never downloaded again."""
    time_col, _ = config.DATASETS[dataset]
    df = store.load(dataset, symbol)
    if df.empty:
        return set()
    return set(pd.to_datetime(df[time_col], unit="ms", utc=True).dt.strftime("%Y-%m"))


def missing_days(dataset: str, symbol: str) -> list[str]:
    """Days ('YYYY-MM-DD') between the first and last stored bar that have no row."""
    time_col, _ = config.DATASETS[dataset]
    df = store.load(dataset, symbol)
    if df.empty:
        return []
    days = pd.DatetimeIndex(pd.to_datetime(df[time_col], unit="ms", utc=True).dt.normalize())
    expected = pd.date_range(days.min(), days.max(), freq="D")
    return list(expected.difference(days).strftime("%Y-%m-%d"))


def work_list(perps: list[str], settled: list[str]) -> dict[str, list[str]]:
    """Symbols per dataset: spot is BTC and ETH only, and settled folders exist for klines only."""
    return {
        "archive_spot_klines_1d": list(src.SPOT_SYMBOLS),
        "archive_spot_klines_1h": list(src.SPOT_SYMBOLS),
        "archive_um_klines_1d": perps + settled,
        "archive_um_funding": perps,
        "archive_um_premium_1d": perps,
    }


def _backfill_one(dataset: str, symbol: str, *, get, delay: float) -> tuple[int | None, list]:
    """(new rows, or None if the listing failed; [(month/day/None, error)]) for one symbol.

    It touches only this symbol's file and reports nothing itself, so symbols can run side by
    side."""
    try:
        months = src.list_month_keys(dataset, symbol, get=get, delay=delay)
    except Exception as e:
        return None, [(None, e)]
    time_col, _ = config.DATASETS[dataset]
    have = stored_months(dataset, symbol)
    added, errors = 0, []
    for month, key in months.items():
        if month in have:
            continue
        try:
            rows = src.fetch_month(dataset, key, get=get, delay=delay)
            added += store.upsert(dataset, symbol, rows, time_col)
        except Exception as e:
            errors.append((month, e))
    filled, fill_errors = _fill_days(dataset, symbol, get=get, delay=delay)
    return added + filled, errors + fill_errors


def _fill_days(dataset: str, symbol: str, *, get, delay: float) -> tuple[int, list]:
    """Fetch the days a monthly file skipped from Binance's daily files (spec §1.1).

    A day with no daily file is a real hole and stays one; any other error is reported."""
    template = src.SOURCES[dataset].daily
    if template is None:
        return 0, []
    time_col, _ = config.DATASETS[dataset]
    added, errors = 0, []
    for day in missing_days(dataset, symbol):
        try:
            rows = src.fetch_month(dataset, template.format(symbol=symbol, day=day), get=get,
                                   delay=delay)
            added += store.upsert(dataset, symbol, rows, time_col)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                errors.append((day, e))
        except Exception as e:
            errors.append((day, e))
    return added, errors


def run(work: dict[str, list[str]], *, get, delay: float, workers: int = 1) -> Summary:
    """Datasets in order; within one, up to `workers` symbols download side by side, each paced.

    Results are reported in symbol order, and a dataset finishes before the next one starts."""
    summary = Summary()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for dataset, symbols in work.items():
            one = partial(_backfill_one, dataset, get=get, delay=delay)
            for symbol, (added, errors) in zip(symbols, pool.map(one, symbols)):
                for month, e in errors:
                    summary.failures.append((dataset, symbol, month))
                    print(f"{symbol:<24} {dataset:<24} {month or 'listing'} FAILED: {e}",
                          file=sys.stderr)
                if added is not None:
                    summary.new_rows[(dataset, symbol)] = added
                    print(f"{symbol:<24} {dataset:<24} +{added} rows")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", default=",".join(src.SOURCES),
                        help=f"subset of: {','.join(src.SOURCES)}")
    parser.add_argument("--symbols", help="comma-separated override, applied to every dataset")
    parser.add_argument("--dry-run", action="store_true", help="list the work, fetch no data")
    parser.add_argument("--workers", type=int, default=config.ARCHIVE_WORKERS,
                        help="symbols downloaded side by side (default %(default)s)")
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

    summary = run(work, get=src.http_get, delay=config.ARCHIVE_DELAY, workers=args.workers)
    total = sum(summary.new_rows.values())
    print(f"\nDone: +{total} rows across {len(summary.new_rows)} tasks; "
          f"{len(summary.failures)} failures")
    if summary.failures:
        for dataset, symbol, month in summary.failures:
            print(f"  FAILED {symbol} {dataset} {month or 'listing'}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
