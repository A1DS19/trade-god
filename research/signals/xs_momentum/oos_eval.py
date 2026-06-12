"""Blind OOS evaluation of the frozen xs_momentum signal (pre-registered protocol).

Run from repo root: python3 -m research.signals.xs_momentum.oos_eval

- Frozen params from params.json; weights built ONLY via signal.build_weights.
- PnL computed ONLY via research.siglib.run_backtest.
- One full-history backtest per cost model; OOS windows are slices of it
  (weights at T depend only on data <= T, so slicing == per-window runs).
- Parameter combinations evaluated by this script: 1 (the frozen set).
  Leg-decomposition runs (long part / short part of the SAME frozen weights)
  are descriptive, not selection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.siglib import load_funding, load_klines, run_backtest, to_panel
from research.siglib.costs import STRESS, CostModel
from research.siglib.data import eligible_mask
from research.signals.xs_momentum.signal import build_weights

HERE = Path(__file__).parent

WINDOWS = {
    "W1": ("2023-07-01", "2024-07-01"),
    "W2": ("2024-07-01", "2025-07-01"),
    "W3": ("2025-07-01", "2026-06-01"),
}
POOLED = ("2023-07-01", "2026-06-01")


def metrics(res) -> dict:
    s = res.summary()
    return {
        "net_return_pct": round(s["total_return"] * 100, 2),
        "profit_factor": round(s["profit_factor"], 4),
        "max_dd_pct": round(s["max_drawdown"] * 100, 2),
        "n_trades": s["n_trades"],
        "turnover": round(s["turnover"], 1),
        "total_trade_cost_pct": round(s["total_trade_cost"] * 100, 2),
        "total_funding_pct": round(s["total_funding"] * 100, 2),
        "gross_return_arith_pct": round(float(res.gross_returns.sum()) * 100, 2),
        "net_return_arith_pct": round(float(res.returns.sum()) * 100, 2),
        "n_bars": s["n_bars"],
    }


def daily_pf(returns: pd.Series) -> float:
    dt = pd.to_datetime(returns.index, unit="ms", utc=True)
    daily = returns.groupby(dt.floor("D")).sum()
    wins = float(daily[daily > 0].sum())
    losses = float(-daily[daily < 0].sum())
    return round(wins / losses, 4) if losses else float("inf")


def monthly_table(returns: pd.Series) -> pd.Series:
    """Arithmetic (additive) monthly decomposition of hourly net returns."""
    dt = pd.to_datetime(returns.index, unit="ms", utc=True)
    return returns.groupby(dt.to_period("M").astype(str)).sum()


def main() -> None:
    params = json.loads((HERE / "params.json").read_text())
    print("frozen params:", params)

    klines = load_klines("all", interval="1h")  # FULL history (eligibility + warmup)
    funding = load_funding("all")
    close = to_panel(klines, "close")
    elig = eligible_mask(klines)
    print(f"klines rows={len(klines):,} symbols={close.shape[1]} bars={close.shape[0]}")

    w = build_weights(klines, params)

    runs = {
        "baseline": run_backtest(close, w, CostModel(), funding, eligibility=elig),
        "stress": run_backtest(close, w, STRESS, funding, eligibility=elig),
        "long_leg": run_backtest(close, w.clip(lower=0.0), CostModel(), funding, eligibility=elig),
        "short_leg": run_backtest(close, w.clip(upper=0.0), CostModel(), funding, eligibility=elig),
    }

    out: dict = {"params": params, "n_param_combos_evaluated_oos": 1}

    for name, res in runs.items():
        out[name] = {}
        for wname, (s, e) in {**WINDOWS, "pooled": POOLED}.items():
            sl = res.window(s, e)
            m = metrics(sl)
            m["daily_profit_factor_descriptive"] = daily_pf(sl.returns)
            out[name][wname] = m

    # leg decomposition sanity: long + short arithmetic net == LS arithmetic net
    pooled = runs["baseline"].window(*POOLED)
    leg_sum = (
        runs["long_leg"].window(*POOLED).returns + runs["short_leg"].window(*POOLED).returns
    )
    assert (leg_sum - pooled.returns).abs().max() < 1e-12, "leg decomposition broke"

    # monthly breakdown (pooled OOS, baseline)
    mt = monthly_table(pooled.returns)
    out["monthly_net_arith_pct"] = {k: round(v * 100, 3) for k, v in mt.items()}
    total = float(mt.sum())
    out["monthly_dominance"] = {
        "total_net_arith_pct": round(total * 100, 2),
        "best_month": mt.idxmax(),
        "best_month_pct": round(float(mt.max()) * 100, 2),
        "best_month_share_of_total": round(float(mt.max()) / total, 3) if total != 0 else None,
        "worst_month": mt.idxmin(),
        "worst_month_pct": round(float(mt.min()) * 100, 2),
        "n_positive_months": int((mt > 0).sum()),
        "n_months": int(len(mt)),
    }

    # promotion criteria (binding; PF = siglib hourly-bar profit factor)
    per_w = out["baseline"]
    positive = sum(per_w[k]["net_return_pct"] > 0 for k in WINDOWS)
    pooled_pf = per_w["pooled"]["profit_factor"]
    stress_ret = out["stress"]["pooled"]["net_return_pct"]
    out["promotion"] = {
        "criterion_1_positive_windows": positive,
        "criterion_1_pass": positive >= 2,
        "criterion_2_pooled_pf": pooled_pf,
        "criterion_2_pass": pooled_pf >= 1.2,
        "criterion_3_stress_pooled_return_pct": stress_ret,
        "criterion_3_pass": stress_ret > 0,
        "passes_all": positive >= 2 and pooled_pf >= 1.2 and stress_ret > 0,
    }

    (HERE / "oos_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["promotion"], indent=2))
    for k in ["W1", "W2", "W3", "pooled"]:
        print(k, out["baseline"][k])
    print("stress pooled:", out["stress"]["pooled"])
    print("long leg pooled:", out["long_leg"]["pooled"])
    print("short leg pooled:", out["short_leg"]["pooled"])
    print(mt.mul(100).round(2).to_string())


if __name__ == "__main__":
    main()
