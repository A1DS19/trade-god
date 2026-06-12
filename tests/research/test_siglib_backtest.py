"""Golden tests for the siglib backtest engine (the lookahead contract lives here)."""

import numpy as np
import pandas as pd
import pytest

from research.siglib.backtest import run_backtest
from research.siglib.costs import CostModel
from research.siglib.data import eligible_mask

HOUR = 3_600_000
DAY = 24 * HOUR
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC

FREE = CostModel(taker_bps=0.0, slippage_bps=0.0)


def _panel(values, columns=("A",), start=BASE):
    times = [start + i * HOUR for i in range(len(values))]
    return pd.DataFrame(values, index=pd.Index(times, name="open_time"), columns=list(columns))


# ---------------------------------------------------------------------------
# a. LOOKAHEAD CONTRACT
# ---------------------------------------------------------------------------
def test_lookahead_contract_random_walk():
    """The lookahead pin, in two halves:

    1. The same-bar cheat w[t] = sign(ret[t]) must earn ~nothing on a random
       walk, because the engine only applies w[t] to ret[t+1].
    2. The impossible future signal w[t] = sign(ret[t+1]) must earn hugely
       through the same engine.
    Together these prove the engine shifts decided weights exactly once.
    """
    rng = np.random.default_rng(7)
    n = 3000
    sigma = 0.005
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, sigma, n)))
    prices = _panel(close)
    ret = prices["A"] / prices["A"].shift(1) - 1.0

    cheat = pd.DataFrame({"A": np.sign(ret.fillna(0.0))}, index=prices.index)
    future = pd.DataFrame({"A": np.sign(ret.shift(-1).fillna(0.0))}, index=prices.index)

    res_cheat = run_backtest(prices, cheat, FREE)
    res_future = run_backtest(prices, future, FREE)

    cheat_edge = abs(float(res_cheat.returns.sum()))
    future_edge = float(res_future.returns.sum())
    abs_ret_budget = float(ret.abs().sum())  # what perfect foresight collects, ~ n*sigma*0.8

    assert cheat_edge < 4 * sigma * np.sqrt(n)  # statistically zero
    assert future_edge > 0.5 * abs_ret_budget  # collects most of every bar's |move|
    assert future_edge > 10 * cheat_edge


# ---------------------------------------------------------------------------
# b. HAND-COMPUTED 3-BAR SCENARIO (pnl + turnover cost + funding, to 1e-12)
# ---------------------------------------------------------------------------
def test_three_bar_hand_computed():
    prices = _panel([[100.0], [110.0], [99.0]])
    t0, t1, t2 = prices.index
    weights = pd.DataFrame({"A": [1.0, 1.0, 0.0]}, index=prices.index)
    cm = CostModel(taker_bps=5.0, slippage_bps=5.0)  # 10 bps = 0.001 per side
    funding = pd.DataFrame(
        {"symbol": ["A"], "funding_time": [t2 + 123], "funding_rate": [0.0001]}
    )  # ms jitter: lands in holding interval (t2, t2+1h] -> charged at bar t2 vs w[t1]

    res = run_backtest(prices, weights, cm, funding_long=funding)

    assert res.returns.loc[t0] == 0.0  # nothing held yet; entry cost hits at t1
    expected_t1 = (110.0 / 100.0 - 1.0) - 1.0 * 0.001  # pnl - |1-0|*cps
    assert res.returns.loc[t1] == pytest.approx(expected_t1, abs=1e-12)
    expected_t2 = (99.0 / 110.0 - 1.0) - 0.0001  # held weight unchanged; funding paid
    assert res.returns.loc[t2] == pytest.approx(expected_t2, abs=1e-12)

    assert res.turnover == pytest.approx(1.0, abs=1e-12)  # exit decided at t2 never executes
    assert res.n_trades == 1
    assert float(res.trade_costs.sum()) == pytest.approx(0.001, abs=1e-12)
    assert float(res.funding_costs.sum()) == pytest.approx(0.0001, abs=1e-12)
    expected_total = (1.0 + expected_t1) * (1.0 + expected_t2) - 1.0
    assert res.total_return == pytest.approx(expected_total, abs=1e-12)


# ---------------------------------------------------------------------------
# c. FUNDING SIGN: longs pay positive funding, shorts receive it
# ---------------------------------------------------------------------------
def test_funding_sign_long_pays_short_receives():
    prices = _panel([[50.0]] * 5)  # flat: all pnl comes from funding
    idx = prices.index
    funding = pd.DataFrame(
        {
            "symbol": ["A", "A"],
            "funding_time": [idx[1] + 5, idx[3] + 5],
            "funding_rate": [0.0001, 0.0001],
        }
    )
    long_w = pd.DataFrame({"A": [1.0] * 5}, index=idx)
    short_w = pd.DataFrame({"A": [-1.0] * 5}, index=idx)

    res_long = run_backtest(prices, long_w, FREE, funding_long=funding)
    res_short = run_backtest(prices, short_w, FREE, funding_long=funding)

    assert float(res_long.returns.sum()) == pytest.approx(-0.0002, abs=1e-15)
    assert float(res_short.returns.sum()) == pytest.approx(0.0002, abs=1e-15)
    # negative rate flips: long receives
    funding_neg = funding.assign(funding_rate=[-0.0001, -0.0001])
    res_long_neg = run_backtest(prices, long_w, FREE, funding_long=funding_neg)
    assert float(res_long_neg.returns.sum()) == pytest.approx(0.0002, abs=1e-15)


# ---------------------------------------------------------------------------
# d. ELIGIBILITY: <60d of history -> zero weight even if requested
# ---------------------------------------------------------------------------
def test_eligibility_zeroes_young_symbol():
    times = [BASE + i * HOUR for i in range(5)]
    history = pd.concat(
        [
            pd.DataFrame({"symbol": "OLD", "open_time": [BASE - 100 * DAY, *times]}),
            pd.DataFrame({"symbol": "NEW", "open_time": [BASE - 10 * DAY, *times]}),
        ],
        ignore_index=True,
    )
    mask = eligible_mask(history)
    prices = pd.DataFrame(
        {"OLD": [10.0, 11.0, 12.0, 13.0, 14.0], "NEW": [1.0, 2.0, 3.0, 4.0, 5.0]},
        index=pd.Index(times, name="open_time"),
    )
    weights = pd.DataFrame(1.0, index=prices.index, columns=["NEW"])  # only NEW requested

    res = run_backtest(prices, weights, FREE, eligibility=mask)
    assert (res.returns == 0.0).all()
    assert res.n_trades == 0
    assert res.turnover == 0.0

    # control: same request without the mask trades and earns NEW's run-up
    res_no_mask = run_backtest(prices, weights, FREE)
    assert res_no_mask.n_trades == 1
    assert float(res_no_mask.returns.sum()) > 0


def test_nan_prices_force_zero_weight():
    prices = _panel([[100.0], [np.nan], [102.0], [103.0]])
    weights = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=prices.index)
    res = run_backtest(prices, weights, FREE)
    # decided weight at the NaN bar is forced to 0 -> no pnl from the gap bar's
    # NaN return; the gap is a forced exit + re-entry
    assert not res.returns.isna().any()
    assert res.n_trades == 3  # entry t0, forced exit at NaN bar t1, re-entry t2
    assert res.returns.iloc[3] == pytest.approx(103.0 / 102.0 - 1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# e. PROFIT FACTOR / MAX DRAWDOWN on a constructed curve with known values
# ---------------------------------------------------------------------------
def test_profit_factor_and_drawdown_known_values():
    prices = _panel([[100.0], [110.0], [99.0], [108.9]])
    weights = pd.DataFrame({"A": [1.0] * 4}, index=prices.index)
    res = run_backtest(prices, weights, FREE)

    r1 = 110.0 / 100.0 - 1.0   # +0.1
    r2 = 99.0 / 110.0 - 1.0    # -0.1
    r3 = 108.9 / 99.0 - 1.0    # +0.1
    assert res.profit_factor == pytest.approx((r1 + r3) / -r2, rel=1e-12)  # = 2.0
    assert res.profit_factor == pytest.approx(2.0, rel=1e-9)
    # equity: [1, 1.1, 0.99, 1.089]; max dd = 1 - 0.99/1.1 = 0.1
    assert res.max_drawdown == pytest.approx(1.0 - (1.0 + r1) * (1.0 + r2) / (1.0 + r1), rel=1e-12)
    assert res.max_drawdown == pytest.approx(0.1, rel=1e-9)
    assert res.total_return == pytest.approx(1.1 * 0.9 * 1.1 - 1.0, rel=1e-12)
    assert res.n_trades == 1
    assert res.turnover == pytest.approx(1.0)


def test_funding_inside_index_gap_charged_to_live_weight():
    """Audit pin: funding events falling inside an index gap must be charged to
    the weight live during the gap, not a stale earlier bar's weight (the old
    last-open_time-strictly-below mapping charged w[1]=0 here -> zero funding)."""
    times = [BASE + h * HOUR for h in (0, 1, 2, 5, 6)]  # hours 3,4 missing
    prices = pd.DataFrame({"A": [100.0] * 5}, index=pd.Index(times, name="open_time"))
    # w=1 decided at bar 2 (close = wall-clock 3h) is live during (3h, 6h]
    weights = pd.DataFrame({"A": [0.0, 0.0, 1.0, 1.0, 0.0]}, index=prices.index)
    funding = pd.DataFrame(
        {"symbol": ["A"], "funding_time": [BASE + 4 * HOUR + 21], "funding_rate": [0.001]}
    )
    res = run_backtest(prices, weights, FREE, funding_long=funding)
    assert float(res.funding_costs.sum()) == pytest.approx(0.001, abs=1e-15)
    assert res.funding_costs.loc[times[3]] == pytest.approx(0.001, abs=1e-15)


def test_unsorted_or_duplicate_index_rejected():
    """Audit pin: positional shift + searchsorted assume a sorted unique index;
    a shuffled index used to be accepted silently and produced garbage."""
    bad = pd.Index([BASE, BASE + 2 * HOUR, BASE + HOUR], name="open_time")
    prices = pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=bad)
    weights = pd.DataFrame({"A": [1.0] * 3}, index=bad)
    with pytest.raises(ValueError, match="strictly increasing"):
        run_backtest(prices, weights, FREE)
    dup = pd.Index([BASE, BASE, BASE + HOUR], name="open_time")
    with pytest.raises(ValueError, match="strictly increasing"):
        run_backtest(
            pd.DataFrame({"A": [1.0, 1.0, 2.0]}, index=dup),
            pd.DataFrame({"A": [1.0] * 3}, index=dup),
            FREE,
        )


def test_window_slicing_recomputes_metrics():
    prices = _panel([[100.0], [110.0], [99.0], [108.9]])
    weights = pd.DataFrame({"A": [1.0] * 4}, index=prices.index)
    res = run_backtest(prices, weights, FREE)
    sub = res.window(start=prices.index[2], end=prices.index[3] + 1)
    assert len(sub.returns) == 2
    assert sub.total_return == pytest.approx(0.9 * 1.1 - 1.0, rel=1e-12)
    assert sub.n_trades == 0
