"""Phase 2b train runner: pre-registered grid, mechanical freeze, diagnostics.

PRE-REGISTERED (2026-07-16): TRAIN_END = 2025-07-01 — nothing on/after is
loaded here. Grid 3H x 2exit x 3K per fill variant; selection = eligible
(n_trades >= 100, total_return > 0) -> max annualized Sharpe with the
plateau guard from the basis_mr protocol on H/K neighbors (same exit).
Diagnostics are descriptive and must not alter frozen params. OOS stays
sealed.

Run:  python -m research.signals.intraday.mr_vwap_train
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.siglib.backtest import run_backtest
from research.siglib.costs import INTRADAY, MAKER_ENTRY
from research.signals.intraday import mr_vwap_strategy as strat
from research.signals.intraday.families import mr_vwap_z

TRAIN_END = "2025-07-01"
DEFAULT_OUT = Path(__file__).parent / "output" / "2b"
GRID_H = [8, 16, 32]
GRID_EXIT = ["horizon", "z_recover"]
GRID_K = [3, 5, 10]
MIN_TRAIN_TRADES = 100
BARS_PER_YEAR = 4 * 24 * 365
VARIANTS = {
    "next_bar": ("next_bar", INTRADAY, INTRADAY),
    "maker_limit": ("maker_limit", MAKER_ENTRY, INTRADAY),
}


def annualized_sharpe(returns: pd.Series) -> float:
    sd = float(returns.std())
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(returns.mean()) / sd * np.sqrt(BARS_PER_YEAR)


def load_panels(end):
    df15 = sdata.load_klines("all", interval="15m", end=end)
    if df15.empty:
        raise SystemExit("no klines_15m data before end")
    df1d = sdata.load_klines("all", interval="1d", end=end)
    funding = sdata.load_funding("all", end=end)
    data = {"klines_15m": df15}
    close = sdata.to_panel(df15, "close")
    low = sdata.to_panel(df15, "low")
    z = mr_vwap_z(data)
    elig = (
        sdata.eligible_mask(df15)
        .reindex(index=close.index, columns=close.columns).fillna(False)
    )
    pit = strat.pit_top30_mask(df1d, close.index, close.columns)
    return z, close, low, elig & pit, funding


def run_combo(panels, params, fill, buy, sell):
    z, close, low, elig, funding = panels
    w = strat.build_weights(z, close, low, elig, params, fill)
    res = run_backtest(close, w, buy, funding_long=funding,
                       eligibility=None, sell_cost_model=sell)
    s = res.summary()
    s["sharpe"] = annualized_sharpe(res.returns)
    s["episodes"] = int(((w > 0) & (w.shift(1).fillna(0.0) == 0)).sum().sum())
    return s, w, res


def select_frozen(log: pd.DataFrame):
    ok = log[(log.n_trades >= MIN_TRAIN_TRADES) & (log.total_return > 0)]
    if ok.empty:
        return None, False
    ok = ok.sort_values("sharpe", ascending=False)

    def neighbors_positive(row) -> bool:
        for col, grid in (("horizon_bars", GRID_H), ("max_k", GRID_K)):
            gi = grid.index(row[col])
            for j in (gi - 1, gi + 1):
                if 0 <= j < len(grid):
                    q = {"horizon_bars": row["horizon_bars"], "max_k": row["max_k"]}
                    q[col] = grid[j]
                    nb = log[(log.horizon_bars == q["horizon_bars"])
                             & (log.max_k == q["max_k"])
                             & (log.exit == row["exit"])]
                    # An in-grid neighbor that is absent from the log or has
                    # NaN sharpe (never traded) cannot certify a plateau.
                    if not len(nb):
                        return False
                    s = float(nb.iloc[0].sharpe)
                    if np.isnan(s) or s <= 0:
                        return False
        return True

    for _, row in ok.iterrows():
        if neighbors_positive(row):
            return row, False
    return ok.iloc[0], True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    panels = load_panels(TRAIN_END)
    rows = []
    for vname, (fill, buy, sell) in VARIANTS.items():
        for H, E, K in itertools.product(GRID_H, GRID_EXIT, GRID_K):
            params = {"horizon_bars": H, "exit": E, "max_k": K}
            s, _, _ = run_combo(panels, params, fill, buy, sell)
            rows.append({"fill": vname, **params, **s})
            print(f"{vname:<12} H={H:<3} exit={E:<10} K={K:<3} "
                  f"ret={s['total_return']:+.4f} pf={s['profit_factor']:.3f} "
                  f"sharpe={s['sharpe']:+.2f} trades={s['n_trades']} "
                  f"episodes={s['episodes']}")
    log = pd.DataFrame(rows)
    log.to_csv(out / "combo_log.csv", index=False)

    frozen, diag = {}, {}
    for vname in VARIANTS:
        chosen, cliff = select_frozen(log[log.fill == vname])
        if chosen is None:
            frozen[vname] = None
            print(f"{vname}: NOT VIABLE on train")
            continue
        frozen[vname] = {"horizon_bars": int(chosen.horizon_bars),
                         "exit": str(chosen.exit), "max_k": int(chosen.max_k),
                         "_cliff": bool(cliff)}
        print(f"{vname}: FROZEN {frozen[vname]} sharpe={chosen.sharpe:+.2f}")
    (out / "frozen_params.json").write_text(json.dumps(frozen, indent=2) + "\n")

    # diagnostics on the best viable variant(s), train-only, descriptive
    per_sym_rows, monthly_rows = [], []
    for vname, params in frozen.items():
        if params is None:
            continue
        fill, buy, sell = VARIANTS[vname]
        p = {k: v for k, v in params.items() if not k.startswith("_")}
        s, w, res = run_combo(panels, p, fill, buy, sell)
        z, close, low, elig, funding = panels
        ret = close / close.shift(1) - 1.0
        pnl_sym = (w.shift(1).fillna(0.0) * ret).fillna(0.0)
        for sym in pnl_sym.columns:
            entries = int(((w[sym] > 0) & (w[sym].shift(1).fillna(0.0) == 0)).sum())
            if entries:
                per_sym_rows.append({"variant": vname, "symbol": sym,
                                     "episodes": entries,
                                     "gross_pnl": float(pnl_sym[sym].sum())})
        month = pd.to_datetime(res.returns.index, unit="ms").to_period("M")
        for mth, grp in res.returns.groupby(month):
            monthly_rows.append({"variant": vname, "month": str(mth),
                                 "net_return": float(grp.sum())})
        se = float(res.returns.std()) / np.sqrt(max(len(res.returns), 1))
        diag[vname] = {"edge_t": float(res.returns.mean()) / se if se else float("nan"),
                       "episodes": s["episodes"], **{k: s[k] for k in
                       ("total_return", "profit_factor", "max_drawdown", "n_trades")}}
    pd.DataFrame(per_sym_rows).to_csv(out / "diag_per_symbol.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(out / "diag_monthly.csv", index=False)
    (out / "diag_summary.json").write_text(json.dumps(diag, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
