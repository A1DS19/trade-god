"""Correctness tests for app.bot.indicators — Bollinger %B is the DCA dip signal.

(EMA/RSI/MACD/ATR are duplicated from the swing module; smoke-checked here too so
the bot's own copy can't silently drift.)
"""

from __future__ import annotations

import pytest

from app.bot import indicators as ind


def test_bollinger_pct_b_is_half_for_flat_series():
    out = ind.calc_bollinger([10.0] * 25, period=20)
    assert out["bb_lower"] == pytest.approx(10.0)
    assert out["bb_upper"] == pytest.approx(10.0)
    assert out["bb_pct_b"] == 0.5            # degenerate band → midpoint


def test_bollinger_pct_b_below_zero_when_price_under_lower_band():
    closes = [10.0] * 19 + [8.0]             # last bar dumps below the band
    out = ind.calc_bollinger(closes, period=20)
    assert out["bb_pct_b"] < 0               # < 0.2 is the buy trigger; < 0 is below the band


def test_bot_rsi_extremes_match_convention():
    assert ind.calc_rsi(list(range(1, 40)), 14) == 100.0
    assert ind.calc_rsi(list(range(40, 1, -1)), 14) == 0.0


def test_bot_atr_constant_range():
    assert ind.calc_atr([101.0] * 20, [99.0] * 20, [100.0] * 20, 14) == pytest.approx(2.0)


def test_bot_macd_hist_zero_for_flat_series():
    out = ind.calc_macd([10.0] * 60)
    assert out["macd_hist"] == pytest.approx(0.0)
    assert out["macd_hist_prev"] == pytest.approx(0.0)
