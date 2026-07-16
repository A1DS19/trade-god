"""Phase 2a edge-hunt runner: all six families, 15m train data only.

PRE-REGISTERED (2026-07-15): TRAIN_END = 2025-07-01 — nothing on/after this
date is loaded here. OOS (3 windows over 2025-07-01..2026-07-15) is reserved
for Phase 2b. Survivor rule and family definitions: see harness.py and
families.py; every tested pair lands in checks.csv.

Run:  python -m research.signals.intraday.study
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.siglib import data as sdata
from research.signals.intraday.families import FAMILIES
from research.signals.intraday.harness import evaluate_family

TRAIN_END = "2025-07-01"
DEFAULT_OUT = Path(__file__).parent / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df15 = sdata.load_klines("all", interval="15m", end=TRAIN_END)
    if df15.empty:
        raise SystemExit("no klines_15m data in the warehouse before TRAIN_END")
    funding = sdata.load_funding("all", end=TRAIN_END)
    data = {"klines_15m": df15, "funding": funding}

    close = sdata.to_panel(df15, "close")
    elig = (
        sdata.eligible_mask(df15)
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
    )
    print(f"train: {df15['symbol'].nunique()} symbols, "
          f"{len(close.index)} bars < {TRAIN_END}")

    verdicts, all_checks = {}, []
    for spec in FAMILIES:
        buckets = spec.build(data).where(elig)
        stats, checks, verdict = evaluate_family(spec, close, buckets)
        stats.to_csv(out / f"{spec.name}_event_study.csv", index=False)
        all_checks.append(checks)
        verdicts[spec.name] = verdict
        n_pass = int(checks["passes"].sum())
        print(f"{spec.name:<16} {verdict:<9} "
              f"({n_pass}/{len(checks)} bucket x horizon pairs pass)")

    pd.concat(all_checks, ignore_index=True).to_csv(out / "checks.csv", index=False)
    (out / "verdicts.json").write_text(json.dumps(verdicts, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
