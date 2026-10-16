"""Train-only validation study of the BTC and ETH arms, then their freeze (spec 2026-10-02 §2.4).

    python -m research.signals.model_lab.study

Each arm runs both settings over the validation decisions, 2021-07-01 to 2023-06-30, with its
quarterly refits and baseline costs: four of Experiment 1's six trials. An arm keeps the setting
whose book has the higher Sharpe of weekly net returns; a tie, or a Sharpe ratio neither book has,
goes to S1. The kept setting then meets the stop rule against BTC (§3.4). The run writes the trial
log and each arm's frozen_params.json under output/, and never loads a bar from the sealed
windows."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from research.siglib.backtest import BacktestResult
from research.siglib.costs import CostModel
from research.siglib.data import load_klines, to_ms
from research.siglib.stats import max_drawdown, sharpe, weekly_returns
from research.signals.model_lab import arms, gates, models
from research.signals.model_lab.features import ANNUAL_DAYS, TIMING_FEATURES, daily_grid
from research.signals.model_lab.labels import HORIZON_DAYS
from research.signals.model_lab.walkforward import EMBARGO_DAYS

VALIDATION_START = "2021-07-01"
VALIDATION_END = "2023-07-01"  # where the sealed windows begin
OUTPUT = Path(__file__).parent / "output"
COSTS = CostModel()  # baseline: 10 bp per side
SPOT = tuple(asset for asset, _ in arms.TIMING_ARMS.values())


def load_spot(end=VALIDATION_END) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """(daily, hourly) archive spot klines of both assets: every bar that opened before `end`."""
    daily = {s: load_klines(s, "1d", end=end, source="archive_spot_klines") for s in SPOT}
    hourly = {s: load_klines(s, "1h", end=end, source="archive_spot_klines") for s in SPOT}
    for bars in [*daily.values(), *hourly.values()]:
        if len(bars) and bars["open_time"].max() >= to_ms(end):
            raise RuntimeError("the study loaded a bar from the sealed windows")
    return daily, hourly


def run_trial(daily: dict[str, pd.DataFrame], hourly: dict[str, pd.DataFrame], arm: str,
              setting: str) -> BacktestResult:
    """One arm under one setting over the validation decisions, at baseline costs."""
    asset, _ = arms.TIMING_ARMS[arm]
    decisions = arms.timing_decisions(daily, hourly[asset], arm, setting, VALIDATION_START,
                                      VALIDATION_END)
    return arms.run_book(daily_grid(daily[asset])["close"], decisions["w"], VALIDATION_START,
                         VALIDATION_END, COSTS)


def trial_row(arm: str, setting: str, book: BacktestResult) -> dict:
    """One trial-log row. sharpe_per_week, the Sharpe ratio in weekly units, feeds G6 (§3.3)."""
    weekly = weekly_returns(book.returns)
    return {"arm": arm, "setting": setting, "sharpe": sharpe(weekly),
            "sharpe_per_week": sharpe(weekly, periods_per_year=1), "weeks": len(weekly),
            "max_drawdown": max_drawdown(book.returns), "total_return": book.total_return,
            "turnover": book.turnover, "trades": book.n_trades,
            "trade_cost": float(book.trade_costs.sum())}


def choose(rows: pd.DataFrame) -> str:
    """S2 only if its Sharpe beats S1's; a missing Sharpe ranks below any number."""
    sharpes = rows.set_index("setting")["sharpe"].fillna(-math.inf)
    return "S2" if sharpes["S2"] > sharpes["S1"] else "S1"


def frozen_params(arm: str, setting: str, rows: pd.DataFrame, stop: dict[str, bool],
                  btc: BacktestResult) -> dict:
    """Everything the unseal needs to rerun this arm exactly: the kept setting and every
    constant, plus the validation evidence for the choice."""
    asset, other = arms.TIMING_ARMS[arm]
    by_setting = rows.set_index("setting")
    return {
        "arm": arm, "asset": asset, "other_asset": other,
        "status": "frozen" if all(stop.values()) else "failed_on_validation",
        "setting": setting,
        "lightgbm_params": models.lightgbm_params(setting),
        "versions": {package: version(package) for package in ("lightgbm", "numpy", "pandas")},
        "features": TIMING_FEATURES,
        "constants": {"threshold": models.THRESHOLD, "band": arms.BAND,
                      "horizon_days": HORIZON_DAYS, "embargo_days": EMBARGO_DAYS,
                      "refits": "first day of each calendar quarter", "har_start": arms.HAR_START,
                      "sigma_star_days": models.SIGMA_STAR_DAYS, "annual_days": ANNUAL_DAYS},
        "costs": asdict(COSTS),
        "validation": {
            "start": VALIDATION_START, "end": VALIDATION_END,
            "sharpe": by_setting["sharpe"].to_dict(),
            "max_drawdown": float(by_setting.loc[setting, "max_drawdown"]),
            "btc_sharpe": sharpe(weekly_returns(btc.returns)),
            "btc_max_drawdown": max_drawdown(btc.returns),
            **stop,
        },
    }


def main() -> None:
    daily, hourly = load_spot()
    btc_close = daily_grid(daily["BTCUSDT"])["close"]
    btc = arms.run_book(btc_close, pd.Series(1.0, index=btc_close.index), VALIDATION_START,
                        VALIDATION_END, COSTS)
    rows, books = [], {}
    for arm in arms.TIMING_ARMS:
        for setting in models.SETTINGS:
            books[arm, setting] = run_trial(daily, hourly, arm, setting)
            rows.append(trial_row(arm, setting, books[arm, setting]))
            print(f"{arm} {setting}: weekly Sharpe {rows[-1]['sharpe']:+.3f}, "
                  f"max drawdown {rows[-1]['max_drawdown']:.1%}, {rows[-1]['trades']} trades")
    log = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    log.to_csv(OUTPUT / "combo_log.csv", index=False)
    for arm in arms.TIMING_ARMS:
        mine = log[log["arm"] == arm]
        setting = choose(mine)
        stop = gates.stop_rule(books[arm, setting].returns, btc.returns)
        params = frozen_params(arm, setting, mine, stop, btc)
        path = OUTPUT / arm / "frozen_params.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(params, indent=2) + "\n")
        print(f"{arm}: keeps {setting}; G1 {stop['G1']}, G2 {stop['G2']}: {params['status']}")


if __name__ == "__main__":
    main()
