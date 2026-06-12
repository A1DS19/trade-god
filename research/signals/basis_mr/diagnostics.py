"""Post-freeze diagnostics for the train report (W1 train data only).

1. Survivorship bound: rerun the frozen params on a fixed "incumbent majors"
   subset — symbols listed 2019-20 whose presence in TODAY'S top-100-by-volume
   universe was never in doubt, so their inclusion is (nearly) independent of
   their 2020-23 performance. If the edge collapses on this subset, the
   full-universe number is survivorship-inflated.
2. Per-symbol net PnL concentration of the frozen strategy on W1 train.
3. Exit-type and holding-period stats.

Run AFTER study.py froze params:  python -m research.signals.basis_mr.diagnostics
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.siglib import data as sdata
from research.siglib.backtest import run_backtest
from research.siglib.costs import CostModel
from research.signals.basis_mr import study
from research.signals.basis_mr.signal import build_weights

# Listed 2019-2020 on Binance USDT-M; top-of-book incumbents whose survival to
# 2026's top-100 was effectively unconditional.
MAJORS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "LTCUSDT", "LINKUSDT", "BCHUSDT", "ETCUSDT", "TRXUSDT", "XLMUSDT",
]


def main():
    params = json.loads((Path(__file__).parent / "params.json").read_text())
    params = {k: v for k, v in params.items() if not k.startswith("_")}
    print("frozen params:", params)

    data = study.load_train_data(study.W1_TRAIN_END)
    prices = sdata.to_panel(data["klines_1h"], "close")
    elig = sdata.eligible_mask(data["klines_1h"])
    w = build_weights(data, params)

    # --- full-universe baseline + per-symbol concentration ------------------
    res = run_backtest(prices, w, CostModel(), funding_long=data["funding"],
                       eligibility=elig)
    print("\nfull universe:", {k: round(v, 4) for k, v in res.summary().items()},
          "sharpe", round(study.annualized_sharpe(res.returns), 2))

    ret = prices / prices.shift(1) - 1.0
    per_sym_gross = (w.shift(1).fillna(0.0) * ret).sum()
    print("\nper-symbol GROSS pnl contribution (top/bottom 8):")
    contrib = per_sym_gross[per_sym_gross != 0].sort_values()
    print(pd.concat([contrib.head(8), contrib.tail(8)]).round(3).to_string())
    print(f"share of positive gross from top 3 symbols: "
          f"{contrib.nlargest(3).sum() / contrib[contrib > 0].sum():.2f}")

    # --- majors-only survivorship bound -------------------------------------
    maj = [s for s in MAJORS if s in prices.columns]
    data_m = {
        "klines_1h": data["klines_1h"][data["klines_1h"].symbol.isin(maj)],
        "premium": data["premium"][data["premium"].symbol.isin(maj)],
        "funding": data["funding"][data["funding"].symbol.isin(maj)],
        "cache": {},
    }
    prices_m = sdata.to_panel(data_m["klines_1h"], "close")
    elig_m = sdata.eligible_mask(data_m["klines_1h"])
    w_m = build_weights(data_m, params)
    res_m = run_backtest(prices_m, w_m, CostModel(), funding_long=data_m["funding"],
                         eligibility=elig_m)
    print(f"\nmajors-only ({len(maj)} incumbents):",
          {k: round(v, 4) for k, v in res_m.summary().items()},
          "sharpe", round(study.annualized_sharpe(res_m.returns), 2))

    # --- holding-period stats ------------------------------------------------
    nz = w != 0
    pos_chg = nz & ~nz.shift(1, fill_value=False)
    episodes = int(pos_chg.sum().sum())
    held_bars = int(nz.sum().sum())
    print(f"\nepisodes: {episodes}, avg hold: {held_bars / max(episodes,1):.1f}h, "
          f"avg open positions: {nz.sum(axis=1).mean():.2f}, "
          f"long share of held bars: {float((w > 0).sum().sum()) / held_bars:.2f}")


if __name__ == "__main__":
    main()
