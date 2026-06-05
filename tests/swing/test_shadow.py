"""Shadow tracker for RSI-gate-blocked would-be trades (observe-only diagnostic).

Pins the would-be-PnL sign convention and the open/update/close lifecycle, and that
agent.decide() attaches the gate_block payload the tracker consumes.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.swing import shadow

_GB = {"direction": "short", "rsi": 20.0, "would_be_conf": 0.85}


# ── would_be_pnl_pct: short profits as price falls; long as price rises ──

def test_short_profits_when_price_falls():
    assert shadow.would_be_pnl_pct("short", 100.0, 90.0) == pytest.approx(0.10)
    assert shadow.would_be_pnl_pct("short", 100.0, 110.0) == pytest.approx(-0.10)


def test_long_profits_when_price_rises():
    assert shadow.would_be_pnl_pct("long", 100.0, 110.0) == pytest.approx(0.10)
    assert shadow.would_be_pnl_pct("long", 100.0, 90.0) == pytest.approx(-0.10)


@pytest.mark.property
@given(
    entry=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False),
    cur=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_short_and_long_wb_pnl_are_mirror_images(entry, cur):
    assert shadow.would_be_pnl_pct("short", entry, cur) == pytest.approx(
        -shadow.would_be_pnl_pct("long", entry, cur)
    )


# ── ShadowTracker open / update / close ──

def test_does_not_open_when_would_be_conf_below_min():
    t = shadow.ShadowTracker(max_cycles=8)
    low = {"direction": "short", "rsi": 20.0, "would_be_conf": 0.60}
    assert t.observe("DOGE", 0.08, low, 0.80) == []      # would not have traded → ignore
    assert t.observe("DOGE", 0.08, None, 0.80) == []      # no block → ignore


def test_opens_on_would_be_trade():
    t = shadow.ShadowTracker(max_cycles=8)
    assert any("SHADOW-OPEN DOGE short" in line for line in t.observe("DOGE", 0.08, _GB, 0.80))


def test_updates_then_closes_when_ungated():
    t = shadow.ShadowTracker(max_cycles=8)
    t.observe("DOGE", 0.100, _GB, 0.80)                   # open @ 0.100
    upd = t.observe("DOGE", 0.095, _GB, 0.80)             # still blocked, price fell 5%
    assert any("SHADOW DOGE short would-be +5.00%" in line for line in upd)
    close = t.observe("DOGE", 0.098, None, 0.80)          # un-gated → close, +2%
    assert any("SHADOW-CLOSE DOGE short would-be +2.00%" in line for line in close)
    assert t.observe("DOGE", 0.098, None, 0.80) == []     # closed → no longer tracked


def test_closes_at_max_age():
    t = shadow.ShadowTracker(max_cycles=2)
    t.observe("X", 100.0, _GB, 0.80)                      # open, cycles=0
    assert any("1h" in line for line in t.observe("X", 100.0, _GB, 0.80))   # cycles=1
    assert any("SHADOW-CLOSE" in line for line in t.observe("X", 100.0, _GB, 0.80))  # cycles=2 ≥ max


def test_negative_would_be_pnl_when_gate_avoided_a_loser():
    """A blocked short whose price ROSE = a loser avoided = negative would-be PnL."""
    t = shadow.ShadowTracker(max_cycles=8)
    t.observe("TURBO", 0.00081, _GB, 0.80)
    close = t.observe("TURBO", 0.00085, None, 0.80)       # price rose against the short
    assert any("SHADOW-CLOSE" in line and "-" in line for line in close)


# ── agent integration: the gate must attach gate_block for the tracker ──

def test_agent_attaches_gate_block_on_block(snapshot):
    from app.swing import agent

    s = snapshot(
        ema_alignment="bearish", daily_ema_alignment="bearish",
        adx=40.0, plus_di=6.0, minus_di=35.0, macd_hist=-0.002, rsi=18.0,
    )
    d = agent.decide(s)
    assert d["action"] == "hold" and d["confidence"] == 0.0
    gb = d.get("gate_block")
    assert gb is not None
    assert gb["direction"] == "short"
    assert "would_be_conf" in gb
