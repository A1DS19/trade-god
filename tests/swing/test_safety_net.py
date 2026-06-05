"""Client-side SL/TP safety net — the only stop protection if exchange orders fail.

Pins app.swing.main._safety_net_label: SL when price moves DEFAULT_SL_PCT against
entry, TP when it moves DEFAULT_TP_PCT in favor, None inside the band — long & short.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.swing import config
from app.swing.main import _safety_net_label


def test_long_hits_sl_below_entry():
    assert _safety_net_label("long", 100.0, 97.0, 0.03, 0.08) == "SL"
    assert _safety_net_label("long", 100.0, 95.0, 0.03, 0.08) == "SL"


def test_long_hits_tp_above_entry():
    assert _safety_net_label("long", 100.0, 108.0, 0.03, 0.08) == "TP"
    assert _safety_net_label("long", 100.0, 120.0, 0.03, 0.08) == "TP"


def test_long_inside_band_is_none():
    assert _safety_net_label("long", 100.0, 102.0, 0.03, 0.08) is None   # +2%
    assert _safety_net_label("long", 100.0, 98.0, 0.03, 0.08) is None    # -2%


def test_short_hits_sl_when_price_rises():
    # a short loses as price RISES
    assert _safety_net_label("short", 100.0, 103.0, 0.03, 0.08) == "SL"
    assert _safety_net_label("short", 100.0, 105.0, 0.03, 0.08) == "SL"


def test_short_hits_tp_when_price_falls():
    # a short profits as price FALLS
    assert _safety_net_label("short", 100.0, 92.0, 0.03, 0.08) == "TP"
    assert _safety_net_label("short", 100.0, 80.0, 0.03, 0.08) == "TP"


def test_short_inside_band_is_none():
    assert _safety_net_label("short", 100.0, 98.0, 0.03, 0.08) is None   # -2% (small profit)
    assert _safety_net_label("short", 100.0, 102.0, 0.03, 0.08) is None  # +2% (small loss)


def test_live_thresholds_trigger_at_config_pcts():
    sl, tp = config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT
    assert _safety_net_label("long", 100.0, 100.0 * (1 - sl), sl, tp) == "SL"
    assert _safety_net_label("long", 100.0, 100.0 * (1 + tp), sl, tp) == "TP"
    assert _safety_net_label("short", 100.0, 100.0 * (1 + sl), sl, tp) == "SL"
    assert _safety_net_label("short", 100.0, 100.0 * (1 - tp), sl, tp) == "TP"


@pytest.mark.property
@given(
    entry=st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
    sl=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
    tp=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
    frac=st.floats(min_value=0.0, max_value=0.98, allow_nan=False),
)
def test_no_trigger_strictly_inside_band(entry, sl, tp, frac):
    band = min(sl, tp) * frac          # strictly less than both thresholds
    for price in (entry * (1 + band), entry * (1 - band)):
        assert _safety_net_label("long", entry, price, sl, tp) is None
        assert _safety_net_label("short", entry, price, sl, tp) is None
