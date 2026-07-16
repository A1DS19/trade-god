"""Asymmetric buy/sell costs: default unchanged; long-only entry/exit split."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.siglib.backtest import run_backtest
from research.siglib.costs import CostModel

IDX = pd.Index(np.arange(10) * 900_000, name="open_time")


def _flat_prices():
    return pd.DataFrame({"AAAUSDT": [100.0] * 10}, index=IDX)


def _one_round_trip():
    w = pd.DataFrame(0.0, index=IDX, columns=["AAAUSDT"])
    w.iloc[2:5] = 1.0  # decided on bars 2-4 -> enter at bar 3, exit at bar 5
    return w


def test_none_sell_model_matches_symmetric():
    prices, w = _flat_prices(), _one_round_trip()
    base = run_backtest(prices, w, CostModel())
    explicit = run_backtest(prices, w, CostModel(), sell_cost_model=CostModel())
    pd.testing.assert_series_equal(base.returns, explicit.returns)
    pd.testing.assert_series_equal(base.trade_costs, explicit.trade_costs)


def test_long_only_entry_exit_rates_split():
    prices, w = _flat_prices(), _one_round_trip()
    buy = CostModel(taker_bps=2.0, slippage_bps=0.0)    # 2 bps/side
    sell = CostModel(taker_bps=5.0, slippage_bps=3.0)   # 8 bps/side
    res = run_backtest(prices, w, buy, sell_cost_model=sell)
    # entry decided bar 2 executes bar 3; exit decided bar 5 executes bar 6
    assert res.trade_costs.iloc[3] == pytest.approx(1.0 * 0.0002)
    assert res.trade_costs.iloc[6] == pytest.approx(1.0 * 0.0008)
    assert float(res.trade_costs.sum()) == pytest.approx(0.0010)
    assert res.n_trades == 2
    assert float(res.turnover_per_bar.sum()) == pytest.approx(2.0)


def test_maker_cost_models_registered():
    from research.siglib import costs
    assert costs.MAKER_ENTRY.cost_per_side == pytest.approx(0.0002)
    assert costs.MAKER_ENTRY_STRESS.cost_per_side == pytest.approx(0.0004)
