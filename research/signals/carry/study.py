"""Funding-rate carry — event study + train-only parameter exploration.

PRE-REGISTERED PROTOCOL (do not deviate)
========================================
Phase A — SELECTION. Uses ONLY data strictly before 2023-07-01 (the earliest
OOS start, W1). Because one frozen parameter set serves all three walk-forward
windows, selecting on anything later would contaminate W1/W2 OOS. Phase A
loads the warehouse with end=2023-07-01 so later data is never even computed on.

Phase B — REPORT. Runs the already-frozen params on the three train windows
(W1 < 2023-07-01, W2 < 2024-07-01, W3 < 2025-07-01). Loads end=2025-07-01;
nothing on/after 2025-07-01 is touched. No parameter is revisited in Phase B.

Parameter grid (every combo evaluated and logged to combo_log.csv):
    form='abs':  x in {3, 5, 8, 12, 20} bps/8h
                 exit_frac in {0.25, 0.5, 1.0}
                 m_events in {1, 3, 6}; k_max in {3, 5, 10}
                 filter in {none, trend72}              -> 270 combos
    form='pct':  x in {0.90, 0.95, 0.98} (exit buffer fixed at 0.10)
                 m_events in {1, 3, 6}; k_max in {3, 5, 10}
                 filter in {none, trend72}              ->  54 combos
                                                   total   324 combos

Selection rule (fixed before looking at results):
    eligible if, on W1 train: n_trades >= 100 AND total_return > 0 AND
    profit_factor >= 1.1 AND total_return under STRESS costs (slippage 10bps) > 0;
    among eligible, pick max annualized Sharpe of hourly net returns
    (mean/std * sqrt(8760)). Plateau check: report the x-neighbors of the
    winner (same other params) — a winner on a cliff is reported as such.

Execution: all PnL via research.siglib.run_backtest (next-bar, costs 10bps/side
baseline, funding accrued; longs pay positive funding). Eligibility: 60-day rule.
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib import CostModel, event_study, run_backtest
from research.siglib import data as sdata
from research.siglib.costs import STRESS
from research.signals.carry import signal as sig

OUT = Path(__file__).parent
W1_OOS_START = "2023-07-01"
W2_OOS_START = "2024-07-01"
W3_OOS_START = "2025-07-01"

BASE = CostModel()  # taker 5 + slippage 5
HOURS_PER_YEAR = 24 * 365

EVENT_EDGES_BPS = [-np.inf, -20, -10, -5, -2, 2, 5, 10, 20, np.inf]
EVENT_LABELS = ["<-20", "-20..-10", "-10..-5", "-5..-2", "-2..2",
                "2..5", "5..10", "10..20", ">20"]

GRID_ABS = {
    "x": [3.0, 5.0, 8.0, 12.0, 20.0],
    "exit_frac": [0.25, 0.5, 1.0],
    "m_events": [1, 3, 6],
    "k_max": [3, 5, 10],
    "filter": ["none", "trend72"],
}
GRID_PCT = {
    "x": [0.90, 0.95, 0.98],
    "m_events": [1, 3, 6],
    "k_max": [3, 5, 10],
    "filter": ["none", "trend72"],
}


def load_phase(end: str) -> dict:
    klines = sdata.load_klines("all", "1h", end=end)
    funding = sdata.load_funding("all", end=end)
    close = sdata.to_panel(klines, "close")
    elig = (
        sdata.eligible_mask(klines)
        .reindex(index=close.index, columns=close.columns)
        .fillna(False)
    )
    return {
        "klines": klines,
        "funding": funding,
        "close": close,
        "elig": elig,
        "tradable": elig & close.notna(),
    }


def sharpe(returns: pd.Series) -> float:
    sd = float(returns.std())
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(returns.mean()) / sd * np.sqrt(HOURS_PER_YEAR)


def run_event_study(ph: dict, m_events: int) -> pd.DataFrame:
    """Conditional forward PRICE returns by funding band (train data only)."""
    sm = sig.funding_state_panel(ph["funding"], ph["close"].index, m_events)
    sm = sm.reindex(columns=ph["close"].columns)
    sm_bps = (sm / sig.BPS).where(ph["tradable"])
    stacked = sm_bps.stack().dropna()
    buckets = pd.cut(stacked, bins=EVENT_EDGES_BPS, labels=EVENT_LABELS)
    bucket_panel = buckets.astype(object).unstack()
    bucket_panel = bucket_panel.reindex(index=ph["close"].index, columns=ph["close"].columns)
    return event_study(ph["close"], bucket_panel)


def combo_weights(ph: dict, sm: pd.DataFrame, pct: pd.DataFrame | None, p: dict) -> pd.DataFrame:
    state = sig._state_panel(sm, pct, p)
    state = sig._apply_trend_filter(state, ph["close"], p)
    return sig.weights_from_state(state, sm, ph["tradable"], p["k_max"])


def evaluate(ph: dict, w: pd.DataFrame, cost: CostModel) -> dict:
    res = run_backtest(ph["close"], w, cost, funding_long=ph["funding"])
    return {
        "total_return": res.total_return,
        "profit_factor": res.profit_factor,
        "max_drawdown": res.max_drawdown,
        "n_trades": res.n_trades,
        "turnover": res.turnover,
        "total_funding": float(res.funding_costs.sum()),
        "sharpe": sharpe(res.returns),
    }


def grid_search(ph: dict) -> pd.DataFrame:
    rows = []
    combos = [
        {"form": "abs", **dict(zip(GRID_ABS, vals))}
        for vals in itertools.product(*GRID_ABS.values())
    ] + [
        {"form": "pct", "exit_frac": np.nan, **dict(zip(GRID_PCT, vals))}
        for vals in itertools.product(*GRID_PCT.values())
    ]
    print(f"grid: {len(combos)} combos")

    sm_cache = {
        m: sig.funding_state_panel(ph["funding"], ph["close"].index, m).reindex(
            columns=ph["close"].columns
        )
        for m in (1, 3, 6)
    }
    pct_cache = {m: sig.rolling_percentile_panel(sm_cache[m]) for m in (1, 3, 6)}

    t0 = time.time()
    for i, p in enumerate(combos):
        sm = sm_cache[p["m_events"]]
        pct = pct_cache[p["m_events"]] if p["form"] == "pct" else None
        w = combo_weights(ph, sm, pct, p)
        row = {**p, **evaluate(ph, w, BASE)}
        passes_base = (
            row["n_trades"] >= 100
            and row["total_return"] > 0
            and row["profit_factor"] >= 1.1
        )
        if passes_base:  # stress run only needed for selection-eligible combos
            row["stress_total_return"] = evaluate(ph, w, STRESS)["total_return"]
        else:
            row["stress_total_return"] = np.nan
        row["eligible"] = passes_base and row["stress_total_return"] > 0
        rows.append(row)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(combos)}  ({time.time() - t0:.0f}s)")
    return pd.DataFrame(rows)


GRID_EXT = {  # post-selection sensitivity extension — see sensitivity_extension()
    "x": [30.0, 40.0, 60.0],
    "exit_frac": [0.5, 1.0],
    "m_events": [1, 3],
    "k_max": [3, 5],
    "filter": ["none", "trend72"],
}


def sensitivity_extension() -> None:
    """TRAIN-ONLY (< 2023-07-01) extension above x=20, run AFTER freezing.

    The pre-registered winner landed on the grid edge (x=20). To report
    plateau-vs-cliff honestly we map x in {30,40,60} on train data only.
    These combos are logged (combo_log.csv, phase='ext') and counted, but by
    pre-registration they DO NOT alter the frozen params — they are
    sensitivity evidence only.
    """
    ph = load_phase(W1_OOS_START)
    sm_cache = {
        m: sig.funding_state_panel(ph["funding"], ph["close"].index, m).reindex(
            columns=ph["close"].columns
        )
        for m in (1, 3)
    }
    rows = []
    for vals in itertools.product(*GRID_EXT.values()):
        p = {"form": "abs", **dict(zip(GRID_EXT, vals))}
        w = combo_weights(ph, sm_cache[p["m_events"]], None, p)
        row = {**p, **evaluate(ph, w, BASE)}
        row["stress_total_return"] = evaluate(ph, w, STRESS)["total_return"]
        row["eligible"] = False  # post-hoc: never selectable
        row["phase"] = "ext"
        rows.append(row)
    ext = pd.DataFrame(rows)
    log = pd.read_csv(OUT / "combo_log.csv")
    if "phase" not in log.columns:
        log["phase"] = "preregistered"
    log = pd.concat([log[log["phase"] != "ext"], ext], ignore_index=True)
    log.to_csv(OUT / "combo_log.csv", index=False)
    cols = ["x", "exit_frac", "m_events", "k_max", "filter",
            "total_return", "sharpe", "profit_factor", "n_trades", "total_funding"]
    print(ext[cols].sort_values(["filter", "x"]).to_string(index=False))


def main() -> None:
    # ---------------- Phase A: selection, data < W1 OOS start ONLY ----------
    print("Phase A: loading data end =", W1_OOS_START)
    ph = load_phase(W1_OOS_START)
    print("close panel:", ph["close"].shape)

    for m in (1, 6):
        es = run_event_study(ph, m)
        es.to_csv(OUT / f"event_study_m{m}.csv", index=False)
        print(f"event study (M={m}) written")

    log = grid_search(ph)
    log.to_csv(OUT / "combo_log.csv", index=False)
    print(f"combo log written: {len(log)} combos, {int(log['eligible'].sum())} eligible")

    elig = log[log["eligible"]]
    if elig.empty:
        print("NO ELIGIBLE COMBO — signal not viable on train.")
        (OUT / "params.json").write_text(json.dumps({"viable": False}, indent=2))
        return
    win = elig.loc[elig["sharpe"].idxmax()]
    frozen = {
        "form": str(win["form"]),
        "x": float(win["x"]),
        "m_events": int(win["m_events"]),
        "k_max": int(win["k_max"]),
        "filter": str(win["filter"]),
    }
    if frozen["form"] == "abs":
        frozen["exit_frac"] = float(win["exit_frac"])
    (OUT / "params.json").write_text(json.dumps(frozen, indent=2))
    print("FROZEN:", frozen)

    same = log[
        (log["form"] == win["form"])
        & (log["m_events"] == win["m_events"])
        & (log["k_max"] == win["k_max"])
        & (log["filter"] == win["filter"])
        & ((log["form"] == "pct") | (log["exit_frac"] == win["exit_frac"]))
    ].sort_values("x")
    print("\nplateau (x-neighbors of winner):")
    print(same[["x", "total_return", "sharpe", "profit_factor", "n_trades"]].to_string(index=False))

    # ---------------- Phase B: frozen params on train windows ---------------
    print("\nPhase B: frozen params on train windows (data end =", W3_OOS_START, ")")
    phb = load_phase(W3_OOS_START)
    w = sig.build_weights(
        {"klines_1h": phb["klines"], "funding": phb["funding"]}, frozen
    )
    res = run_backtest(phb["close"], w, BASE, funding_long=phb["funding"])
    res_stress = run_backtest(phb["close"], w, STRESS, funding_long=phb["funding"])
    # Long/short attribution (approximate decomposition: costs of a sign flip
    # within one bar would double-count, but flips are rare with the latch).
    res_short = run_backtest(phb["close"], w.clip(upper=0.0), BASE, funding_long=phb["funding"])
    res_long = run_backtest(phb["close"], w.clip(lower=0.0), BASE, funding_long=phb["funding"])

    def window_stats(r, end):
        s = r.window(None, end)
        return {
            "total_return_pct": round(100 * s.total_return, 2),
            "profit_factor": round(s.profit_factor, 3),
            "max_dd_pct": round(100 * s.max_drawdown, 2),
            "n_trades": s.n_trades,
            "sharpe": round(sharpe(s.returns), 2),
            "total_funding_pnl_pct": round(-100 * float(s.funding_costs.sum()), 2),
            "total_trade_cost_pct": round(100 * float(s.trade_costs.sum()), 2),
        }

    report = {
        "frozen_params": frozen,
        "n_combos": int(len(log)),
        "train_windows": {
            "W1_train": window_stats(res, W1_OOS_START),
            "W2_train": window_stats(res, W2_OOS_START),
            "W3_train": window_stats(res, W3_OOS_START),
        },
        "train_windows_stress": {
            "W1_train": window_stats(res_stress, W1_OOS_START),
            "W2_train": window_stats(res_stress, W2_OOS_START),
            "W3_train": window_stats(res_stress, W3_OOS_START),
        },
        "attribution_full_train": {
            "short_side": window_stats(res_short, W3_OOS_START),
            "long_side": window_stats(res_long, W3_OOS_START),
        },
    }
    (OUT / "frozen_train_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import sys

    if "--ext" in sys.argv:
        sensitivity_extension()
    else:
        main()
