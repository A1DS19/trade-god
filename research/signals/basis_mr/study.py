"""basis_mr study — event study + train-only parameter exploration.

PRE-REGISTERED PROTOCOL (do not deviate):
- Parameter selection uses ONLY data strictly before 2023-07-01 (the earliest
  OOS start, W1). Nothing on/after that date is loaded during Phase A/B.
- Every parameter combination evaluated is logged to output/combo_log.csv.
- Selection rule (mechanical, committed before looking at results):
    eligible combos: n_trades >= 100 and total_return > 0 on W1 train;
    primary ranking: annualized Sharpe of hourly net returns;
    plateau guard: prefer the highest-Sharpe combo whose one-step grid
    neighbors ALL have Sharpe > 0; if none qualifies, take the global best
    and flag it as a cliff.
- Phase C runs the FROZEN params on each train window (W1/W2/W3) for the
  report, at baseline and stress costs. No OOS data is ever touched here
  (W3 train ends 2025-07-01 < first OOS evaluation by the external runner...
  to be precise: phase C touches data < 2025-07-01, which is allowed because
  selection was already frozen in Phase B on < 2023-07-01 data).

Run:  python -m research.signals.basis_mr.study
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.siglib.backtest import run_backtest
from research.siglib.costs import STRESS, CostModel
from research.siglib.events import event_study
from research.signals.basis_mr.signal import build_weights

OUT = Path(__file__).parent / "output"
PARAMS_JSON = Path(__file__).parent / "params.json"

W1_TRAIN_END = "2023-07-01"
TRAIN_ENDS = {"W1_train": "2023-07-01", "W2_train": "2024-07-01", "W3_train": "2025-07-01"}

# ---- grid v3 (270 combos; see output/combo_log_v1_evicting_construction.csv
# for the original 81-combo run whose portfolio construction churned itself
# to death — kept for the multiple-testing ledger) ---------------------------
GRID_M = [168, 336, 720]
GRID_P = [0.95, 0.98, 0.99, 0.995, 0.998]
GRID_H = [24, 72, 168]
GRID_K = [3, 5, 10]
GRID_EXIT = ["median", "horizon"]

EVENT_BUCKET_EDGES = [
    0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.25, 0.75,
    0.95, 0.98, 0.99, 0.995, 0.998, 1.0001,
]
EVENT_BUCKET_LABELS = [
    "[0,.2%]", "(.2,.5%]", "(.5,1%]", "(1,2%]", "(2,5%]", "(5,25%]",
    "(25,75%]", "(75,95%]", "(95,98%]", "(98,99%]", "(99,99.5%]",
    "(99.5,99.8%]", "(99.8,100%]",
]
HORIZONS = (1, 4, 8, 24, 72, 168)
HOURS_PER_YEAR = 24 * 365


def load_train_data(end: str) -> dict:
    """Full-history load (start=None keeps listing dates correct for the
    60-day eligibility rule), truncated strictly before `end`."""
    return {
        "klines_1h": sdata.load_klines("all", end=end),
        "premium": sdata.load_premium("all", end=end),
        "funding": sdata.load_funding("all", end=end),
        "cache": {},
    }


def annualized_sharpe(returns: pd.Series) -> float:
    sd = float(returns.std())
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(returns.mean()) / sd * np.sqrt(HOURS_PER_YEAR)


# ---------------------------------------------------------------------------
# Phase A — event study (train < 2023-07-01)
# ---------------------------------------------------------------------------
def phase_a(data: dict) -> pd.DataFrame:
    from research.signals.basis_mr.signal import _signal_state

    close = sdata.to_panel(data["klines_1h"], "close")
    elig = (
        sdata.eligible_mask(data["klines_1h"])
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
    )
    all_stats = []
    for M in GRID_M:
        _, pct, _ = _signal_state(data, M)
        pct = pct.where(elig)
        stacked = pct.stack()
        buckets = pd.cut(
            stacked, bins=EVENT_BUCKET_EDGES, labels=EVENT_BUCKET_LABELS,
            include_lowest=True,
        ).astype(object)
        bucket_panel = buckets.unstack()
        bucket_panel = bucket_panel.reindex(index=close.index, columns=close.columns)
        stats = event_study(close, bucket_panel, horizons_hours=HORIZONS)
        stats.insert(0, "M", M)
        all_stats.append(stats)
        print(f"[phase A] event study done for M={M}")
    out = pd.concat(all_stats, ignore_index=True)
    out.to_csv(OUT / "event_study_train.csv", index=False)
    return out


# ---------------------------------------------------------------------------
# Phase B — grid search on W1 train ONLY
# ---------------------------------------------------------------------------
def run_combo(data: dict, prices: pd.DataFrame, elig: pd.DataFrame,
              params: dict, cost: CostModel) -> dict:
    w = build_weights(data, params)
    res = run_backtest(prices, w, cost, funding_long=data["funding"], eligibility=elig)
    s = res.summary()
    s["sharpe"] = annualized_sharpe(res.returns)
    return s


def phase_b(data: dict) -> tuple[dict, pd.DataFrame]:
    prices = sdata.to_panel(data["klines_1h"], "close")
    elig = sdata.eligible_mask(data["klines_1h"])
    cost = CostModel()  # baseline 5+5 bps/side
    rows = []
    combos = list(itertools.product(GRID_M, GRID_P, GRID_EXIT, GRID_H, GRID_K))
    t0 = time.time()
    for i, (M, P, E, H, K) in enumerate(combos, 1):
        params = {"M": M, "P": P, "exit_mode": E, "horizon_hours": H, "max_k": K}
        s = run_combo(data, prices, elig, params, cost)
        rows.append({**params, **s})
        print(f"[phase B] {i}/{len(combos)} {params} -> "
              f"ret={s['total_return']:+.4f} pf={s['profit_factor']:.3f} "
              f"sharpe={s['sharpe']:+.2f} trades={s['n_trades']} "
              f"({time.time()-t0:.0f}s)")
    log = pd.DataFrame(rows)
    log.to_csv(OUT / "combo_log.csv", index=False)

    # --- mechanical selection (rule fixed above, before results were seen) ---
    ok = log[(log.n_trades >= 100) & (log.total_return > 0)].copy()
    if ok.empty:
        print("[phase B] NO combo passes the eligibility filter -> not viable")
        return {}, log

    def neighbors_all_positive(row) -> bool:
        """One-step numeric-grid neighbors, within the same exit_mode."""
        for col, grid in (("M", GRID_M), ("P", GRID_P),
                          ("horizon_hours", GRID_H), ("max_k", GRID_K)):
            gi = grid.index(row[col])
            for j in (gi - 1, gi + 1):
                if 0 <= j < len(grid):
                    q = {c: row[c] for c in ("M", "P", "horizon_hours", "max_k")}
                    q[col] = grid[j]
                    nb = log[(log.M == q["M"]) & (log.P == q["P"])
                             & (log.exit_mode == row["exit_mode"])
                             & (log.horizon_hours == q["horizon_hours"])
                             & (log.max_k == q["max_k"])]
                    if len(nb) and float(nb.iloc[0].sharpe) <= 0:
                        return False
        return True

    ok = ok.sort_values("sharpe", ascending=False)
    chosen, cliff = None, False
    for _, row in ok.iterrows():
        if neighbors_all_positive(row):
            chosen = row
            break
    if chosen is None:
        chosen, cliff = ok.iloc[0], True
    params = {"M": int(chosen.M), "P": float(chosen.P),
              "exit_mode": str(chosen.exit_mode),
              "horizon_hours": int(chosen.horizon_hours), "max_k": int(chosen.max_k)}
    print(f"[phase B] FROZEN params: {params} (cliff={cliff}) "
          f"sharpe={chosen.sharpe:+.2f} ret={chosen.total_return:+.4f}")
    PARAMS_JSON.write_text(json.dumps({**params, "_cliff": cliff}, indent=2) + "\n")
    return params, log


# ---------------------------------------------------------------------------
# Phase C — frozen params on each train window, baseline + stress
# ---------------------------------------------------------------------------
def phase_c(params: dict) -> pd.DataFrame:
    rows = []
    for name, end in TRAIN_ENDS.items():
        data = load_train_data(end)
        prices = sdata.to_panel(data["klines_1h"], "close")
        elig = sdata.eligible_mask(data["klines_1h"])
        w = build_weights(data, params)
        for label, cost in (("baseline", CostModel()), ("stress", STRESS)):
            res = run_backtest(prices, w, cost, funding_long=data["funding"],
                               eligibility=elig)
            s = res.summary()
            s["sharpe"] = annualized_sharpe(res.returns)
            rows.append({"window": name, "cost": label, **s})
            print(f"[phase C] {name}/{label}: ret={s['total_return']:+.4f} "
                  f"pf={s['profit_factor']:.3f} dd={s['max_drawdown']:.4f} "
                  f"trades={s['n_trades']} sharpe={s['sharpe']:+.2f}")
        # long/short leg decomposition (diagnostic for survivorship discussion)
        for leg, wl in (("long_leg", w.where(w > 0, 0.0)), ("short_leg", w.where(w < 0, 0.0))):
            res = run_backtest(prices, wl, CostModel(), funding_long=data["funding"],
                               eligibility=elig)
            s = res.summary()
            s["sharpe"] = annualized_sharpe(res.returns)
            rows.append({"window": name, "cost": leg, **s})
            print(f"[phase C] {name}/{leg}: ret={s['total_return']:+.4f} "
                  f"pf={s['profit_factor']:.3f} funding={s['total_funding']:+.4f}")
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "frozen_train_results.csv", index=False)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    print(f"=== Phase A+B: loading train data (< {W1_TRAIN_END}) ===")
    data = load_train_data(W1_TRAIN_END)
    n_sym = data["klines_1h"]["symbol"].nunique()
    print(f"train symbols with any data: {n_sym}")
    phase_a(data)
    params, log = phase_b(data)
    if not params:
        return
    print("=== Phase C: frozen params on train windows ===")
    phase_c(params)


if __name__ == "__main__":
    main()
