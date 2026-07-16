"""Phase 2b OOS evaluator — RUNNING THIS UNSEALS THE OOS YEAR. Run ONCE per
freeze, from Task 5's gated ops step only. No iteration after unseal.

Judges each viable variant against the pre-registered pass bar (spec §3 /
findings §5): net PF >= 1.15 on bar returns, >= 100 OOS trades, positive
total return in >= 2 of 3 windows, max drawdown <= 20% on the full OOS slice.

Run:  python -m research.signals.intraday.mr_vwap_oos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.signals.intraday import mr_vwap_train as train
from research.signals.intraday.mr_vwap_train import VARIANTS, load_panels, run_combo
from research.siglib.costs import INTRADAY, MAKER_ENTRY, MAKER_ENTRY_STRESS, STRESS

DEFAULT_OUT = Path(__file__).parent / "output" / "2b"
OOS_START = "2025-07-01"
OOS_WINDOWS = [("W1", "2025-07-01", "2025-11-01"),
               ("W2", "2025-11-01", "2026-03-01"),
               ("W3", "2026-03-01", None)]
MIN_PF = 1.15
MIN_TRADES = 100
MAX_DD = 0.20
STRESS_COSTS = {"next_bar": (STRESS, STRESS),
                "maker_limit": (MAKER_ENTRY_STRESS, STRESS)}


def judge(full_oos_summary: dict, window_returns: list[float]) -> dict:
    pf_ok = float(full_oos_summary["profit_factor"]) >= MIN_PF
    trades_ok = int(full_oos_summary["n_trades"]) >= MIN_TRADES
    windows_ok = sum(1 for r in window_returns if r > 0) >= 2
    dd_ok = float(full_oos_summary["max_drawdown"]) <= MAX_DD
    return {"pf_ok": pf_ok, "trades_ok": trades_ok, "windows_ok": windows_ok,
            "dd_ok": dd_ok, "passes": pf_ok and trades_ok and windows_ok and dd_ok}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    frozen = json.loads((out / "frozen_params.json").read_text())

    panels = load_panels(end=None)   # FULL history — the unseal
    rows, verdicts = [], {}
    for vname, params in frozen.items():
        if params is None:
            verdicts[vname] = "NOT_VIABLE_ON_TRAIN"
            continue
        p = {k: v for k, v in params.items() if not k.startswith("_")}
        fill = VARIANTS[vname][0]
        for label, (buy, sell) in (
            ("baseline", VARIANTS[vname][1:]),
            ("stress", STRESS_COSTS[vname]),
        ):
            s, w, res = run_combo(panels, p, fill, buy, sell)
            oos_res = res.window(start=OOS_START)
            full = oos_res.summary()
            full["sharpe"] = train.annualized_sharpe(oos_res.returns)
            win_rets = []
            for wname, ws, we in OOS_WINDOWS:
                wr = res.window(start=ws, end=we)
                win_rets.append(wr.total_return)
                rows.append({"variant": vname, "cost": label, "window": wname,
                             **wr.summary()})
            rows.append({"variant": vname, "cost": label, "window": "OOS_FULL",
                         **full})
            if label == "baseline":
                verdicts[vname] = {"judge": judge(full, win_rets),
                                   "params": p, "window_returns": win_rets}
            print(f"{vname}/{label}: PF={full['profit_factor']:.3f} "
                  f"trades={full['n_trades']} dd={full['max_drawdown']:.3f} "
                  f"windows={['%+.4f' % r for r in win_rets]}")
    pd.DataFrame(rows).to_csv(out / "oos_results.csv", index=False)
    (out / "oos_verdicts.json").write_text(json.dumps(verdicts, indent=2) + "\n")
    print(f"outputs -> {out}")


if __name__ == "__main__":
    main()
