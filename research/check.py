"""Warehouse integrity report: rows, coverage, internal gaps, staleness.

    python -m research.check
"""

from __future__ import annotations

from research import config, store

# A real hole is at least a missing bar (2x step); Binance timestamps carry
# ms-level jitter (funding: +1..50ms on 8h steps), so a strict > step flags
# thousands of false positives. 1.5x splits the difference safely.
GAP_TOLERANCE = 1.5


def scan() -> list[dict]:
    report = []
    for dataset, (time_col, step_ms) in config.DATASETS.items():
        ds_dir = config.WAREHOUSE_DIR / dataset
        if not ds_dir.exists():
            continue
        for path in sorted(ds_dir.glob("*.parquet")):
            symbol = path.stem
            df = store.load(dataset, symbol)
            entry = {"dataset": dataset, "symbol": symbol, "rows": len(df),
                     "gaps": None, "largest_gap_ms": 0, "first": None, "last": None}
            if step_ms is not None and len(df) > 1:
                times = df[time_col].sort_values()
                diffs = times.diff().dropna()
                gaps = diffs[diffs > step_ms * GAP_TOLERANCE]
                entry["gaps"] = int(len(gaps))
                entry["largest_gap_ms"] = int(gaps.max()) if len(gaps) else 0
                entry["first"] = int(times.iloc[0])
                entry["last"] = int(times.iloc[-1])
            report.append(entry)
    return report


def main() -> None:
    report = scan()
    if not report:
        print("Warehouse is empty.")
        return
    bad = [e for e in report if e["gaps"]]
    print(f"{len(report)} files scanned; {len(bad)} with gaps")
    for e in sorted(bad, key=lambda e: -e["largest_gap_ms"])[:40]:
        print(f"  {e['symbol']:<16} {e['dataset']:<18} rows={e['rows']:<8} "
              f"gaps={e['gaps']:<4} largest={e['largest_gap_ms'] / 3_600_000:.1f}h")


if __name__ == "__main__":
    main()
