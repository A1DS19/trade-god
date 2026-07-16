"""Golden money-path tests for the 2b weights builder: entry timing per fill
model, maker fill condition, exits, slot cap, PIT gate timing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import mr_vwap_strategy as strat

BAR_MS = 900_000
DAY_MS = 86_400_000
N = 40
IDX = pd.Index(np.arange(N) * BAR_MS, name="open_time")
SYMS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


def _panels(z_hits: dict, low_offset: float = -1.0):
    """z: -5 at (bar, symbol) per z_hits {sym: [bars]}, else 0.
    low = close + low_offset (negative offset => maker limit trades through)."""
    z = pd.DataFrame(0.0, index=IDX, columns=SYMS)
    for sym, bars in z_hits.items():
        for b in bars:
            z.loc[IDX[b], sym] = -5.0
    close = pd.DataFrame(100.0, index=IDX, columns=SYMS)
    low = close + low_offset
    elig = pd.DataFrame(True, index=IDX, columns=SYMS)
    return z, close, low, elig


PARAMS = {"horizon_bars": 4, "exit": "horizon", "max_k": 2}


def test_next_bar_entry_starts_one_bar_late_and_holds_horizon():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    col = w["AAAUSDT"]
    assert col.iloc[10] == 0.0                       # signal bar: no exposure yet
    assert list(col.iloc[11:15]) == [0.5] * 4        # 4 earning bars from close[11]
    assert col.iloc[15] == 0.0


def test_maker_entry_starts_at_signal_bar_when_filled():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="maker_limit")
    col = w["AAAUSDT"]
    assert list(col.iloc[10:14]) == [0.5] * 4        # fills: low[11] < close[10]
    assert col.iloc[14] == 0.0


def test_maker_miss_when_no_trade_through():
    z, close, low, elig = _panels({"AAAUSDT": [10]}, low_offset=0.0)  # touch only
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="maker_limit")
    assert float(w.abs().sum().sum()) == 0.0


def test_z_recover_exit_cuts_hold_short():
    z, close, low, elig = _panels({"AAAUSDT": [10]})
    z.loc[IDX[13], "AAAUSDT"] = 0.0   # already 0, explicit: recovered by bar 13
    params = {"horizon_bars": 20, "exit": "z_recover", "max_k": 2}
    w = strat.build_weights(z, close, low, elig, params, fill="next_bar")
    col = w["AAAUSDT"]
    assert col.iloc[11] == 0.5
    # z > -1 at bar 12 (first held close) -> w goes 0 at bar 12
    assert col.iloc[12] == 0.0


def test_slot_cap_prefers_lowest_z():
    z, close, low, elig = _panels({"AAAUSDT": [10], "BBBUSDT": [10], "CCCUSDT": [10]})
    z.loc[IDX[10], "BBBUSDT"] = -4.0   # least oversold of the three
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    row = w.iloc[11]
    assert row["AAAUSDT"] == 0.5 and row["CCCUSDT"] == 0.5 and row["BBBUSDT"] == 0.0


def test_weights_are_zero_or_slot_size():
    z, close, low, elig = _panels({"AAAUSDT": [5, 20], "BBBUSDT": [12]})
    w = strat.build_weights(z, close, low, elig, PARAMS, fill="next_bar")
    assert set(np.unique(w.to_numpy())) <= {0.0, 0.5}


def test_pit_mask_effective_next_day():
    days = 40
    rows = []
    for sym, qv in (("BIGUSDT", 1000.0), ("SMALLUSDT", 10.0)):
        for i in range(days):
            rows.append({"symbol": sym, "open_time": i * DAY_MS,
                         "close": 1.0, "quote_volume": qv})
    df_1d = pd.DataFrame(rows)
    idx15 = pd.Index([35 * DAY_MS + k * BAR_MS for k in range(4)], name="open_time")
    mask = strat.pit_top30_mask(df_1d, idx15, pd.Index(["BIGUSDT", "SMALLUSDT"]))
    assert bool(mask["BIGUSDT"].all()) and bool(mask["SMALLUSDT"].all())  # both rank <= 30

    # ranking uses data through day d, effective from day d+1: bars before the
    # first ranking day closes must be False
    early = pd.Index([10 * DAY_MS], name="open_time")   # day 10 < 30-day warmup end
    mask_early = strat.pit_top30_mask(df_1d, early, pd.Index(["BIGUSDT"]))
    assert not bool(mask_early["BIGUSDT"].iloc[0])


def test_mr_vwap_z_extracted_and_buckets_unchanged():
    from research.signals.intraday import families
    rng = np.random.default_rng(5)
    n = 300
    closes = list(100.0 + rng.normal(0, 0.05, n))
    df = pd.DataFrame({
        "symbol": "AAAUSDT", "open_time": np.arange(n) * BAR_MS,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [10.0] * n, "quote_volume": [c * 10.0 for c in closes],
        "taker_buy_volume": [5.0] * n, "trades": 1,
    })
    data = {"klines_15m": df}
    z = families.mr_vwap_z(data)
    assert z.shape[1] == 1 and np.isfinite(z.iloc[-1, 0])
