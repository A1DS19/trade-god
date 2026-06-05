"""Correctness tests for app.swing.indicators using analytically-known inputs.

Each case has a hand-derivable answer (EMA of a constant is the constant, RSI of
a monotonic series is 0/100, ATR of a constant range is that range, ADX picks the
trend direction), so these verify the math — not just freeze current output.
"""

from __future__ import annotations

import pytest

from app.swing import indicators as ind


def test_ema_of_constant_is_constant():
    assert ind.calc_ema([5.0] * 30, 10) == pytest.approx(5.0)


def test_ema_stays_within_series_range():
    series = [1.0, 5.0, 3.0, 9.0, 2.0, 7.0]
    assert min(series) <= ind.calc_ema(series, 3) <= max(series)


def test_rsi_all_gains_is_100():
    assert ind.calc_rsi(list(range(1, 40)), 14) == 100.0


def test_rsi_all_losses_is_zero():
    assert ind.calc_rsi(list(range(40, 1, -1)), 14) == 0.0


def test_macd_hist_zero_for_flat_series():
    out = ind.calc_macd([10.0] * 60)
    assert out["hist"] == pytest.approx(0.0)
    assert out["hist_prev"] == pytest.approx(0.0)


def test_atr_of_constant_range_equals_range():
    assert ind.calc_atr([101.0] * 20, [99.0] * 20, [100.0] * 20, 14) == pytest.approx(2.0)


def test_adx_uptrend_is_plus_di_dominant():
    n = 40
    out = ind.calc_adx(
        highs=[100.0 + i for i in range(n)],
        lows=[99.0 + i for i in range(n)],
        closes=[99.5 + i for i in range(n)],
        period=14,
    )
    assert out["minus_di"] == pytest.approx(0.0)
    assert out["plus_di"] > 0
    assert out["adx"] > 20


def test_adx_downtrend_is_minus_di_dominant():
    n = 40
    out = ind.calc_adx(
        highs=[100.0 - i for i in range(n)],
        lows=[99.0 - i for i in range(n)],
        closes=[99.5 - i for i in range(n)],
        period=14,
    )
    assert out["plus_di"] == pytest.approx(0.0)
    assert out["minus_di"] > 0
    assert out["adx"] > 20


def test_vwap_of_constant_price():
    klines = [[0, "10", "10", "10", "10", "5"]] * 6
    assert ind.calc_vwap(klines) == pytest.approx(10.0)


def test_vwap_is_volume_weighted():
    klines = [
        [0, "10", "10", "10", "10", "9"],   # typical 10, volume 9
        [0, "20", "20", "20", "20", "1"],   # typical 20, volume 1
    ]
    assert ind.calc_vwap(klines) == pytest.approx(11.0)   # (10*9 + 20*1) / 10


def test_stoch_rsi_neutral_when_insufficient_data():
    assert ind.calc_stoch_rsi([10.0, 11.0, 12.0], 14, 14) == {"stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0}


def test_atr_percentile_neutral_when_insufficient_data():
    assert ind.calc_atr_percentile([101.0] * 20, [99.0] * 20, [100.0] * 20) == 50.0
