"""Golden bucket tests per family + a shared no-lookahead (truncation
invariance) test: the bucket at bar t must not change when future bars are
removed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import families

BAR_MS = 900_000


def _frame(closes, symbol="AAAUSDT", volume=None, taker=None, quote=None):
    n = len(closes)
    volume = volume if volume is not None else [10.0] * n
    return pd.DataFrame({
        "symbol": symbol,
        "open_time": np.arange(n) * BAR_MS,
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": volume,
        "quote_volume": quote if quote is not None else list(np.asarray(closes) * np.asarray(volume)),
        "taker_buy_volume": taker if taker is not None else [5.0] * n,
        "trades": 1,
    })


def test_breakout_flags_new_high():
    # oscillating prior range (100..101) so the Donchian width is non-zero
    closes = [100.0 + (i % 2) for i in range(200)] + [110.0]
    data = {"klines_15m": _frame(closes)}
    b = families.breakout_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "break_up"


def test_breakout_flags_new_low():
    closes = [100.0 + (i % 2) for i in range(200)] + [90.0]
    data = {"klines_15m": _frame(closes)}
    b = families.breakout_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "break_down"


def test_mr_vwap_flags_positive_spike():
    rng = np.random.default_rng(3)
    closes = list(100.0 + rng.normal(0, 0.05, 300))
    closes.append(103.0)
    data = {"klines_15m": _frame(closes)}
    b = families.mr_vwap_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "z>3"


def test_squeeze_flags_compression():
    rng = np.random.default_rng(4)
    wild = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, 700))
    quiet = wild[-1] * np.cumprod(1 + rng.normal(0, 0.0005, 200))
    data = {"klines_15m": _frame(list(wild) + list(quiet))}
    b = families.squeeze_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "r<.4"


def _synthetic_data(n=900, seed=11):
    rng = np.random.default_rng(seed)
    frames = []
    for sym in ("AAAUSDT", "BBBUSDT"):
        closes = list(100.0 * np.cumprod(1 + rng.normal(0, 0.004, n)))
        vol = list(rng.uniform(5, 50, n))
        taker = [v * r for v, r in zip(vol, rng.uniform(0.2, 0.8, n))]
        frames.append(_frame(closes, symbol=sym, volume=vol, taker=taker))
    df = pd.concat(frames, ignore_index=True)
    funding = pd.DataFrame({
        "symbol": "AAAUSDT",
        "funding_time": np.arange(0, n * BAR_MS, 32 * BAR_MS),
        "funding_rate": rng.normal(0, 3e-4, len(np.arange(0, n * BAR_MS, 32 * BAR_MS))),
        "mark_price": 100.0,
    })
    return {"klines_15m": df, "funding": funding}


def test_funding_buckets_use_last_known_rate_no_lookahead():
    n = 200
    data = {"klines_15m": _frame([100.0] * n)}
    data["funding"] = pd.DataFrame({
        "symbol": "AAAUSDT",
        "funding_time": [50 * BAR_MS, 120 * BAR_MS],
        "funding_rate": [2e-3, -2e-3],
        "mark_price": 100.0,
    })
    b = families.funding_buckets(data)
    assert pd.isna(b["AAAUSDT"].iloc[10])          # before first event: unknown
    assert b["AAAUSDT"].iloc[60] == "f>+.1%"       # after +0.2% event
    assert b["AAAUSDT"].iloc[119] == "f>+.1%"      # event at bar 120 not yet known at 119
    assert b["AAAUSDT"].iloc[125] == "f<-.1%"      # after -0.2% event


def test_vol_impulse_flags_buy_surge():
    n = 200
    vol = [10.0] * n
    taker = [5.0] * n
    vol[-1] = 100.0       # 10x surge
    taker[-1] = 90.0      # 90% taker-buy
    data = {"klines_15m": _frame([100.0] * n, volume=vol, taker=taker)}
    b = families.vol_impulse_buckets(data)
    assert b["AAAUSDT"].iloc[-1] == "i>1.5"


def test_tod_buckets_are_utc_hour():
    data = {"klines_15m": _frame([100.0] * 8)}   # bars at 00:00..01:45 UTC
    b = families.tod_buckets(data)
    assert b["AAAUSDT"].iloc[0] == "h00"
    assert b["AAAUSDT"].iloc[4] == "h01"


@pytest.mark.parametrize("spec", families.FAMILIES, ids=lambda s: s.name)
def test_no_lookahead_truncation_invariance(spec):
    data = _synthetic_data()
    full = spec.build(data)

    cut = 700
    cut_ms = cut * BAR_MS
    data_trunc = {
        "klines_15m": data["klines_15m"][data["klines_15m"]["open_time"] < cut_ms],
        "funding": data["funding"][data["funding"]["funding_time"] < cut_ms],
    }
    trunc = spec.build(data_trunc)

    common = trunc.index
    a = full.loc[common].fillna("~nan~")
    b = trunc.fillna("~nan~")
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
