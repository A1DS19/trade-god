"""SL/TP sizing in snapshot.build().

Pins the rule: SL = max(ATR14/price * 1.5, 1%), TP = max(ATR14/price * 3.0, 2%),
both rounded to 4 dp. The collaborators that hit the exchange are monkeypatched
so we exercise the real assembly logic without network.
"""

from __future__ import annotations

import pytest

from app.swing import snapshot


def _ind(*, price: float, atr14: float) -> dict:
    """A complete indicator dict — only price/atr14 matter for SL/TP."""
    return {
        "price": price,
        "atr14": atr14,
        "ema9": price, "ema21": price, "ema50": price,
        "ema21_daily": price, "ema50_daily": price, "ema200_daily": price,
        "adx14": 25.0, "plus_di": 20.0, "minus_di": 15.0,
        "rsi14_4h": 50.0, "vol_ratio": 1.0,
        "macd_hist": 0.0, "macd_hist_prev": 0.0,
        "oi_change_pct": 0.0, "stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0,
        "atr_pct_rank": 50.0, "vwap": price, "ls_ratio": 1.0, "taker_ratio": 1.0,
        "candles_4h": [],
    }


@pytest.fixture
def build_with(monkeypatch):
    """Return a builder that runs snapshot.build() with a controlled ATR/price."""
    def _run(*, price: float, atr14: float) -> dict:
        monkeypatch.setattr(snapshot, "get_indicators", lambda c, coin: _ind(price=price, atr14=atr14))
        monkeypatch.setattr(snapshot, "get_funding_rate", lambda c, coin: 0.0)
        monkeypatch.setattr(snapshot, "get_open_positions", lambda c: {})
        return snapshot.build(client=None, coin="X")

    return _run


def test_sltp_from_atr_when_above_floors(build_with):
    snap = build_with(price=100.0, atr14=2.0)         # atr_frac = 0.02
    assert snap["suggested_sl_pct"] == 0.03           # 0.02 * 1.5
    assert snap["suggested_tp_pct"] == 0.06           # 0.02 * 3.0


def test_sltp_floors_apply_when_atr_tiny(build_with):
    snap = build_with(price=100.0, atr14=0.1)         # atr_frac = 0.001
    assert snap["suggested_sl_pct"] == 0.01           # 1% floor
    assert snap["suggested_tp_pct"] == 0.02           # 2% floor


def test_sltp_mixed_floor_and_atr(build_with):
    snap = build_with(price=100.0, atr14=0.8)         # atr_frac = 0.008
    assert snap["suggested_sl_pct"] == 0.012          # max(0.012, 0.01)
    assert snap["suggested_tp_pct"] == 0.024          # max(0.024, 0.02)


def test_tp_always_greater_than_sl(build_with):
    for atr in (0.01, 0.1, 0.5, 0.8, 2.0, 10.0):
        snap = build_with(price=100.0, atr14=atr)
        assert snap["suggested_tp_pct"] > snap["suggested_sl_pct"]
