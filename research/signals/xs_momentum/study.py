"""Cross-sectional momentum — pre-registered study (event study + train-only grid).

Protocol (binding)
------------------
- SELECTION uses ONLY data with open_time < 2023-07-01 (the earliest OOS
  start). One parameter set is frozen for all three walk-forward windows, so
  touching anything later would contaminate W1's OOS evaluation. This script
  never loads data past 2025-07-01 (the latest train end); OOS evaluation is
  done elsewhere by the evaluator, running signal.build_weights with
  params.json.
- Every parameter combination evaluated is appended to combo_log.csv.
- Selection rule (pre-registered, applied mechanically):
    candidates = combos with net total_return > 0 and n_trades >= 100 on the
    selection window; pick the candidate with the highest PLATEAU score =
    nan-mean profit factor over {combo + all combos differing in exactly one
    grid coordinate by one step (vol toggle = one step)}. Tie-break: own PF,
    then lower turnover. Plateau scoring is the anti-cliff device: a combo
    that only works at one isolated grid point loses to a stable region.
- Costs: baseline 5+5 bps/side; stress 5+10 bps/side. Funding accrued via the
  siglib engine (longs pay positive funding).

Run:  python -m research.signals.xs_momentum.study
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib.backtest import run_backtest
from research.siglib.costs import STRESS, CostModel
from research.siglib.data import load_funding, load_klines
from research.siglib.events import event_study
from research.signals.xs_momentum.signal import (
    compute_score,
    prepare_panels,
    weights_from_panels,
)

OUT_DIR = Path(__file__).parent
COST_BASE = CostModel()  # 5 + 5 bps/side

SELECT_END = "2023-07-01"  # earliest OOS start — selection never sees beyond this
TRAIN_WINDOWS = {  # cumulative train windows for the frozen-params report
    "W1_train": "2023-07-01",
    "W2_train": "2024-07-01",
    "W3_train": "2025-07-01",
}
REPORT_END = "2025-07-01"  # latest train end; nothing beyond is ever loaded here

R_LIST = [7, 14, 30]      # lookback days
K_LIST = [3, 5, 10]       # positions per leg
B_LIST = [24, 72, 168]    # rebalance hours
VOL_LIST = [False, True]  # vol-normalized ranking

# within-selection sub-periods for sensitivity (NOT used by the selection rule)
SUBPERIODS = [("2021-07-01", "2022-07-01"), ("2022-07-01", "2023-07-01")]

EVENT_HORIZONS = (1, 4, 8, 24, 72, 168)


def metrics(res) -> dict:
    return {
        "total_return_pct": round(res.total_return * 100, 2),
        "profit_factor": round(res.profit_factor, 4),
        "max_dd_pct": round(res.max_drawdown * 100, 2),
        "n_trades": res.n_trades,
        "turnover": round(res.turnover, 1),
        "total_funding_pct": round(float(res.funding_costs.sum()) * 100, 2),
        "total_trade_cost_pct": round(float(res.trade_costs.sum()) * 100, 2),
    }


def decile_panel(close, elig, lookback_days, vol_norm) -> pd.DataFrame:
    """Cross-sectional decile (0=worst momentum .. 9=best) among eligible symbols."""
    score = compute_score(close, lookback_days, vol_norm).where(elig)
    pct = score.rank(axis=1, pct=True)
    return np.ceil(pct * 10).clip(1, 10) - 1


def run_event_studies(close, elig) -> pd.DataFrame:
    rows = []
    for r, vol in [(7, False), (14, False), (30, False), (14, True)]:
        dec = decile_panel(close, elig, r, vol)
        es = event_study(close, dec, horizons_hours=EVENT_HORIZONS)
        es.insert(0, "vol_norm", vol)
        es.insert(0, "lookback_days", r)
        rows.append(es)
        print(f"  event study done: R={r} vol_norm={vol}")
    return pd.concat(rows, ignore_index=True)


def grid_search(close, elig, funding) -> pd.DataFrame:
    rows = []
    for r, k, b, vol in itertools.product(R_LIST, K_LIST, B_LIST, VOL_LIST):
        params = {"lookback_days": r, "k": k, "rebalance_hours": b,
                  "vol_norm": vol, "leg": "ls"}
        w = weights_from_panels(close, elig, params)
        res = run_backtest(close, w, COST_BASE, funding_long=funding, eligibility=elig)
        row = {"R": r, "K": k, "B": b, "vol_norm": vol, **metrics(res)}
        for i, (a, z) in enumerate(SUBPERIODS, 1):
            row[f"sub{i}_ret_pct"] = round(res.window(a, z).total_return * 100, 2)
        rows.append(row)
        print(f"  combo R={r:>2} K={k:>2} B={b:>3} vol={int(vol)} -> "
              f"ret={row['total_return_pct']:>8.2f}% PF={row['profit_factor']:.3f} "
              f"trades={row['n_trades']}")
    return pd.DataFrame(rows)


def plateau_select(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Pre-registered selection rule. Returns (frozen params, scored table)."""
    pf = {}
    for _, row in df.iterrows():
        v = row["profit_factor"]
        pf[(row["R"], row["K"], row["B"], bool(row["vol_norm"]))] = (
            np.nan if not np.isfinite(v) else v
        )

    def neighbors(r, k, b, vol):
        out = [(r, k, b, vol)]
        ri, ki, bi = R_LIST.index(r), K_LIST.index(k), B_LIST.index(b)
        for i in (ri - 1, ri + 1):
            if 0 <= i < len(R_LIST):
                out.append((R_LIST[i], k, b, vol))
        for i in (ki - 1, ki + 1):
            if 0 <= i < len(K_LIST):
                out.append((r, K_LIST[i], b, vol))
        for i in (bi - 1, bi + 1):
            if 0 <= i < len(B_LIST):
                out.append((r, k, B_LIST[i], vol))
        out.append((r, k, b, not vol))
        return out

    df = df.copy()
    df["plateau_pf"] = [
        round(float(np.nanmean([pf[n] for n in neighbors(row["R"], row["K"], row["B"], bool(row["vol_norm"]))])), 4)
        for _, row in df.iterrows()
    ]
    cand = df[(df["total_return_pct"] > 0) & (df["n_trades"] >= 100)]
    if cand.empty:
        return {}, df
    best = cand.sort_values(
        ["plateau_pf", "profit_factor", "turnover"], ascending=[False, False, True]
    ).iloc[0]
    frozen = {
        "lookback_days": int(best["R"]), "k": int(best["K"]),
        "rebalance_hours": int(best["B"]), "vol_norm": bool(best["vol_norm"]),
        "leg": "ls",
    }
    return frozen, df


def main():
    print("=== Phase A+B: selection data (end < %s) ===" % SELECT_END)
    klines = load_klines("all", "1h", end=SELECT_END)
    funding = load_funding("all", end=SELECT_END)
    close, elig = prepare_panels(klines)
    print(f"selection panel: {close.shape[0]} hours x {close.shape[1]} symbols")

    print("--- event studies ---")
    es = run_event_studies(close, elig)
    es.to_csv(OUT_DIR / "event_study.csv", index=False)

    print("--- grid search (%d combos) ---"
          % (len(R_LIST) * len(K_LIST) * len(B_LIST) * len(VOL_LIST)))
    grid = grid_search(close, elig, funding)
    frozen, grid = plateau_select(grid)
    grid.to_csv(OUT_DIR / "combo_log.csv", index=False)
    print("frozen params:", frozen)
    if not frozen:
        print("NO viable combo on train — signal fails before OOS.")
        return

    with open(OUT_DIR / "params.json", "w") as f:
        json.dump(frozen, f, indent=2)

    print("=== Phase C: frozen params on cumulative train windows (end < %s) ===" % REPORT_END)
    rk = load_klines("all", "1h", end=REPORT_END)
    rf = load_funding("all", end=REPORT_END)
    rclose, relig = prepare_panels(rk)

    report = {}
    for leg in ("ls", "long", "short"):
        w = weights_from_panels(rclose, relig, {**frozen, "leg": leg})
        for cost_name, cm in (("base", COST_BASE), ("stress", STRESS)):
            if leg != "ls" and cost_name == "stress":
                continue  # stress test pre-registered on the headline (dollar-neutral) book
            res = run_backtest(rclose, w, cm, funding_long=rf, eligibility=relig)
            for wname, wend in TRAIN_WINDOWS.items():
                report[f"{leg}/{cost_name}/{wname}"] = metrics(res.window(None, wend))

    with open(OUT_DIR / "train_metrics.json", "w") as f:
        json.dump(report, f, indent=2)
    for key, m in report.items():
        print(f"{key:28s} {m}")


if __name__ == "__main__":
    main()
