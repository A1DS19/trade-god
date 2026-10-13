"""Reconcile the archive's perp daily closes with the REST warehouse (spec 2026-10-02 §1.1).

    python -m research.archive_reconcile     # exit 1 on any mismatch or missing day

Where both hold a daily close for a symbol and day, the closes must agree within REL_TOL. Every
REST day inside the archive's span for that symbol must also be in the archive: the listing rule
reads a missing day as the end of a listing, so an archive hole would split a live coin. REST days
outside the span are expected: the UM archive starts in 2020-01, REST's BTC in 2019-09, and REST
runs into the current month. Mismatches the owner has reviewed are reported apart and do not fail.
"""

from __future__ import annotations

import sys

import pandas as pd

from research import store
from research.siglib.data import list_symbols

REL_TOL = 1e-9
REST = "klines_1d"
ARCHIVE = "archive_um_klines_1d"
# Owner's ruling, 2026-10-12 (spec §1.1). On these days the archive's monthly and daily files
# agree with each other, and REST agrees with its own hourly bars. The archive's close is kept.
REVIEWED_MISMATCHES = {("ACEUSDT", "2025-01-28"), ("TUSDT", "2025-01-28"),
                       ("TRUMPUSDT", "2025-01-28")}


def compare(rest: pd.DataFrame, archive: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """(rows whose closes disagree beyond REL_TOL, REST open_times the archive lacks)."""
    both = rest[["open_time", "close"]].merge(
        archive[["open_time", "close"]], on="open_time", suffixes=("_rest", "_archive"))
    rel = (both["close_rest"] - both["close_archive"]).abs() / both["close_archive"].abs()
    disagree = both[rel > REL_TOL].assign(rel_diff=rel[rel > REL_TOL])
    inside = rest["open_time"].between(archive["open_time"].min(), archive["open_time"].max())
    missing = sorted(set(rest.loc[inside, "open_time"]) - set(archive["open_time"]))
    return disagree, missing


def reconcile() -> dict:
    report: dict = {"symbols": 0, "days": 0, "mismatches": [], "reviewed": [], "missing": []}
    for symbol in sorted(set(list_symbols(REST)) & set(list_symbols(ARCHIVE))):
        rest, archive = store.load(REST, symbol), store.load(ARCHIVE, symbol)
        disagree, missing = compare(rest, archive)
        report["symbols"] += 1
        report["days"] += int(rest["open_time"].isin(archive["open_time"]).sum())
        for r in disagree.to_dict("records"):
            reviewed = (symbol, _day(r["open_time"])) in REVIEWED_MISMATCHES
            report["reviewed" if reviewed else "mismatches"].append({"symbol": symbol, **r})
        report["missing"] += [(symbol, t) for t in missing]
    return report


def _day(ms: int) -> str:
    return f"{pd.to_datetime(ms, unit='ms'):%Y-%m-%d}"


def main() -> None:
    report = reconcile()
    print(f"{report['symbols']} symbols, {report['days']} shared days; "
          f"{len(report['mismatches'])} mismatches ({len(report['reviewed'])} reviewed apart), "
          f"{len(report['missing'])} REST days missing from the archive")
    for kind in ("reviewed", "mismatches"):
        for m in report[kind][:40]:
            print(f"  {'REVIEWED' if kind == 'reviewed' else 'MISMATCH'} {m['symbol']:<16} "
                  f"{_day(m['open_time'])} rest={m['close_rest']} archive={m['close_archive']}")
    for symbol, t in report["missing"][:40]:
        print(f"  MISSING  {symbol:<16} {_day(t)}")
    if report["mismatches"] or report["missing"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
