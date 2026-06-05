"""Money math in app.swing.main: position sizing, realized PnL, expected-move filter."""

from __future__ import annotations

from app.swing import config
from app.swing.main import _calc_realized_pnl, _expected_move_ok, _position_size_usdt


# ── _position_size_usdt: confidence → [MIN, MAX], linear above the conf floor ──

def test_size_at_or_below_floor_is_min():
    assert _position_size_usdt(config.MIN_CONFIDENCE) == config.POSITION_USDT_MIN
    assert _position_size_usdt(0.0) == config.POSITION_USDT_MIN


def test_size_at_or_above_cap_is_max():
    assert _position_size_usdt(config.CONFIDENCE_SIZING_CAP) == config.POSITION_USDT_MAX
    assert _position_size_usdt(1.0) == config.POSITION_USDT_MAX


def test_size_midpoint_is_halfway():
    mid = (config.MIN_CONFIDENCE + config.CONFIDENCE_SIZING_CAP) / 2
    expected = round((config.POSITION_USDT_MIN + config.POSITION_USDT_MAX) / 2, 2)
    assert _position_size_usdt(mid) == expected


# ── _calc_realized_pnl: long profits up, short profits down; pct = pnl / notional ──

def test_long_pnl_sign_and_pct():
    pos = {"side": "long", "qty": 10.0, "entry": 100.0, "notional": 1000.0}
    assert _calc_realized_pnl(pos, 110.0) == (100.0, 0.10)
    assert _calc_realized_pnl(pos, 90.0) == (-100.0, -0.10)


def test_short_pnl_sign_and_pct():
    pos = {"side": "short", "qty": 10.0, "entry": 100.0, "notional": 1000.0}
    assert _calc_realized_pnl(pos, 90.0) == (100.0, 0.10)
    assert _calc_realized_pnl(pos, 110.0) == (-100.0, -0.10)


def test_pnl_pct_zero_when_notional_zero():
    pos = {"side": "long", "qty": 10.0, "entry": 100.0, "notional": 0.0}
    pnl, pct = _calc_realized_pnl(pos, 110.0)
    assert pnl == 100.0
    assert pct == 0.0


# ── _expected_move_ok: TP must clear 3× round-trip cost AND net ≥ MIN_NET_TP_PCT ──
# round-trip cost = 2*(EST_FEE_BPS + EST_SLIPPAGE_BPS)/1e4 = 0.12%; required = 0.36%.

def test_tp_below_cost_multiple_rejected():
    ok, reason = _expected_move_ok(0.0030)   # 0.30% < 0.36% required
    assert ok is False
    assert reason


def test_tp_with_thin_net_rejected():
    ok, reason = _expected_move_ok(0.0050)   # clears 0.36% but net 0.38% < 0.40%
    assert ok is False
    assert reason


def test_healthy_tp_accepted():
    ok, _ = _expected_move_ok(0.0060)        # net 0.48% ≥ 0.40%
    assert ok is True
