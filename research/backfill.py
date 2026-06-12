"""Resumable warehouse backfill CLI.

    python -m research.backfill --top 100
    python -m research.backfill --symbols DOGEUSDT,BSVUSDT --datasets klines_1h,funding
    python -m research.backfill --top 100 --dry-run

Run from the DEV machine only — never the production IP (2026-06-05 -1003 ban).
All endpoints are unsigned: no API keys required. Re-running resumes from each
symbol x dataset high-water mark, so interrupting is always safe.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

from research import binance_source as src
from research import config, store, universe


@dataclass
class _FetchSpec:
    fn: object
    needs_interval: str | None = None


FETCHERS: dict[str, _FetchSpec] = {
    "klines_1h": _FetchSpec(src.fetch_klines, "1h"),
    "klines_4h": _FetchSpec(src.fetch_klines, "4h"),
    "klines_1d": _FetchSpec(src.fetch_klines, "1d"),
    "funding": _FetchSpec(src.fetch_funding),
    "premium_index_1h": _FetchSpec(src.fetch_premium_index),
    "oi_1h": _FetchSpec(src.fetch_open_interest),
    "long_short_1h": _FetchSpec(src.fetch_long_short),
}


@dataclass
class Summary:
    new_rows: dict = field(default_factory=dict)   # (dataset, symbol) -> int
    failures: list = field(default_factory=list)   # [(dataset, symbol)]


def run(client, targets: list[dict], datasets: list[str], delay: float) -> Summary:
    summary = Summary()
    for t in targets:
        symbol = t["symbol"]
        for dataset in datasets:
            spec = FETCHERS[dataset]
            time_col, _ = config.DATASETS[dataset]
            hwm = store.high_water_mark(dataset, symbol, time_col)
            start_ms = (hwm + 1) if hwm is not None else int(t.get("onboard_date_ms") or 0)
            try:
                if spec.needs_interval:
                    rows = spec.fn(client, symbol, spec.needs_interval, start_ms, delay=delay)
                else:
                    rows = spec.fn(client, symbol, start_ms, delay=delay)
                n = store.upsert(dataset, symbol, rows, time_col)
                summary.new_rows[(dataset, symbol)] = n
                print(f"{symbol:<16} {dataset:<18} +{n} rows")
            except Exception as e:
                summary.failures.append((dataset, symbol))
                print(f"{symbol:<16} {dataset:<18} FAILED: {e}", file=sys.stderr)
    return summary


def _resolve_onboard(client, symbols: list[str]) -> list[dict]:
    """Resolve real onboard dates for explicit symbols via futures_exchange_info().

    Binance returns onboardDate (epoch ms) per symbol; fall back to 0 when the key
    is absent or zero so the high-water-mark logic in run() handles it gracefully.
    """
    info = client.futures_exchange_info()
    date_by_symbol = {
        s["symbol"]: int(s.get("onboardDate") or 0)
        for s in info.get("symbols", [])
    }
    return [{"symbol": sym, "onboard_date_ms": date_by_symbol.get(sym, 0)} for sym in symbols]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--symbols", help="comma-separated symbol override (skips top-N resolution)")
    parser.add_argument("--datasets", default=",".join(FETCHERS), help=f"subset of: {','.join(FETCHERS)}")
    parser.add_argument("--delay", type=float, default=config.RATE_LIMIT_DELAY)
    parser.add_argument("--dry-run", action="store_true", help="list the work, fetch nothing")
    args = parser.parse_args()

    from binance.client import Client
    client = Client("", "")  # unsigned market-data endpoints only

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    unknown = [d for d in datasets if d not in FETCHERS]
    if unknown:
        parser.error(f"unknown datasets: {unknown}")

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
        targets = _resolve_onboard(client, symbols)
    else:
        rows = universe.resolve_top(client, args.top)
        universe.save_snapshot(rows, snapshot_ms=int(time.time() * 1000))
        targets = rows
        print(f"Universe: top {len(rows)} USDT perps by 24h quote volume (snapshot saved)")

    if args.dry_run:
        for t in targets:
            print(f"{t['symbol']:<16} onboard={t.get('onboard_date_ms')}")
        print(f"{len(targets)} symbols x {len(datasets)} datasets, delay={args.delay}s")
        return

    summary = run(client, targets, datasets, args.delay)
    total = sum(summary.new_rows.values())
    print(f"\nDone: +{total} rows across {len(summary.new_rows)} tasks; {len(summary.failures)} failures")
    if summary.failures:
        for dataset, symbol in summary.failures:
            print(f"  FAILED {symbol} {dataset}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
