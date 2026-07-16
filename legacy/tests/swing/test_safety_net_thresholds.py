"""The client-side net must back up the trade's OWN ATR-sized stops, not
override them with the flat defaults (live incident: IOTA's 4.69% stop was
preempted by the 3% default at 3.77% on 2026-06-12)."""

from __future__ import annotations

from types import SimpleNamespace

from app.swing import config
from app.swing.main import _net_thresholds


def test_uses_trade_row_stops() -> None:
    row = SimpleNamespace(entry_sl_pct=0.0469, entry_tp_pct=0.0938)
    assert _net_thresholds(row) == (0.0469, 0.0938)


def test_falls_back_to_defaults_when_no_row() -> None:
    assert _net_thresholds(None) == (config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT)


def test_falls_back_per_field_when_zero_or_none() -> None:
    row = SimpleNamespace(entry_sl_pct=0.0, entry_tp_pct=None)
    assert _net_thresholds(row) == (config.DEFAULT_SL_PCT, config.DEFAULT_TP_PCT)
