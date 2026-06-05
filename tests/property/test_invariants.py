"""Property-based invariants for swing money math (Hypothesis).

These assert rules that must hold for ALL inputs, not just chosen examples:
position size stays within bounds and rises with confidence; long and short PnL
are exact mirror images; PnL sign follows price direction.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.swing import config
from app.swing.main import _calc_realized_pnl, _position_size_usdt

pytestmark = pytest.mark.property

_price = st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False)
_qty = st.floats(min_value=1e-4, max_value=1e6, allow_nan=False, allow_infinity=False)
_conf = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@given(conf=_conf)
def test_position_size_within_bounds(conf):
    size = _position_size_usdt(conf)
    assert config.POSITION_USDT_MIN <= size <= config.POSITION_USDT_MAX


@given(a=_conf, b=_conf)
def test_position_size_monotonic_in_confidence(a, b):
    lo, hi = sorted((a, b))
    assert _position_size_usdt(lo) <= _position_size_usdt(hi)


@given(entry=_price, exit_=_price, qty=_qty)
def test_long_and_short_pnl_are_mirror_images(entry, exit_, qty):
    notional = entry * qty
    long_pnl, _ = _calc_realized_pnl(
        {"side": "long", "qty": qty, "entry": entry, "notional": notional}, exit_
    )
    short_pnl, _ = _calc_realized_pnl(
        {"side": "short", "qty": qty, "entry": entry, "notional": notional}, exit_
    )
    assert long_pnl == pytest.approx(-short_pnl)


@given(entry=_price, exit_=_price, qty=_qty)
def test_long_pnl_sign_follows_price_direction(entry, exit_, qty):
    notional = entry * qty
    pnl, pct = _calc_realized_pnl(
        {"side": "long", "qty": qty, "entry": entry, "notional": notional}, exit_
    )
    if exit_ > entry:
        assert pnl > 0
    elif exit_ < entry:
        assert pnl < 0
    # pct shares the sign of pnl (notional is strictly positive here)
    assert (pct > 0) == (pnl > 0)
