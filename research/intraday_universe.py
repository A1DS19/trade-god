"""Select the intraday research universe: top-N warehouse symbols by 30-day
median daily quote volume (spec 2026-07-15 §2 — thin coins have untradeable
spreads at intraday frequency).

    python -m research.intraday_universe                 # print CSV symbol list
    python -m research.intraday_universe --top 30 --save # also snapshot to warehouse

Reads klines_1d already in the warehouse; refresh it first
(python -m research.backfill --top 100 --datasets klines_1d) so medians are current.
Output feeds straight into: python -m research.backfill --symbols "$(...)".
"""

from __future__ import annotations

import argparse
import time

from research import config, store

MIN_DAYS = 30
STALENESS_MS = 7 * config.DAY_MS  # last daily bar older than this = likely delisted


def select_top(n: int, now_ms: int | None = None) -> list[dict]:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    ds_dir = config.WAREHOUSE_DIR / "klines_1d"
    rows = []
    for path in sorted(ds_dir.glob("*.parquet")):
        symbol = path.stem
        df = store.load("klines_1d", symbol)
        if len(df) < MIN_DAYS:
            continue
        window = df.sort_values("open_time").tail(MIN_DAYS)
        if int(window["open_time"].max()) < now_ms - STALENESS_MS:
            continue
        rows.append({
            "symbol": symbol,
            "median_quote_volume_30d": float(window["quote_volume"].median()),
        })
    rows.sort(key=lambda r: r["median_quote_volume_30d"], reverse=True)
    top = rows[:n]
    for rank, r in enumerate(top, start=1):
        r["rank"] = rank
    return top


def save_snapshot(rows: list[dict], snapshot_ms: int) -> int:
    keyed = [
        {**r, "snapshot_ms": snapshot_ms, "snapshot_key": f"{snapshot_ms}:{r['symbol']}"}
        for r in rows
    ]
    return store.upsert("intraday_universe", "ALL", keyed, "snapshot_key")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--save", action="store_true", help="snapshot selection to the warehouse")
    args = parser.parse_args()

    top = select_top(args.top)
    if args.save:
        save_snapshot(top, snapshot_ms=int(time.time() * 1000))
    print(",".join(r["symbol"] for r in top))


if __name__ == "__main__":
    main()
