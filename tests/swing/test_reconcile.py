"""Tests for app.swing.reconcile — closing stale DB rows after exchange-side fills.

The live incident this pins: DOGE id=71's algo SL fired 2026-06-11 ~17:45 UTC;
the position vanished between hourly cycles and the DB row stayed status='open'
with no alert and no cooldown. reconcile() must detect DB-open/exchange-absent
trades, backfill the close from account fills, alert, and mark them closed so
the loss cooldown can see them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.swing import reconcile


def _row(**kw):
    """A SwingTrade-shaped stand-in (only the fields reconcile reads)."""
    defaults = dict(
        id=71,
        coin="DOGE",
        direction="short",
        entry_price=0.0834,
        qty=499.0,
        notional_usdt=41.62,
        entry_time="2026-06-10T08:54:16+00:00",
        status="open",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


@pytest.fixture
def capture(monkeypatch):
    """Patch db + notifier seams; return the capture dict."""
    cap = {"closes": [], "alerts": [], "rows": []}
    monkeypatch.setattr(reconcile.db, "get_all_open_swing_trades", lambda: cap["rows"])
    monkeypatch.setattr(
        reconcile.db, "log_swing_close", lambda **kw: cap["closes"].append(kw)
    )
    monkeypatch.setattr(
        reconcile.notifier, "notify_close",
        lambda coin, pos, pnl, reason: cap["alerts"].append((coin, pnl, reason)),
    )
    # Reset retry state so tests that exercise the no-fills fallback start clean.
    reconcile._no_fill_misses.clear()
    return cap


def test_stale_row_closed_from_fills(fake_client, capture) -> None:
    capture["rows"] = [_row()]
    # Position absent from exchange; the short was closed by two BUY fills.
    fake_client.fills = [
        {"side": "SELL", "price": "0.0834", "qty": "499", "realizedPnl": "0", "time": 1781100856000},
        {"side": "BUY", "price": "0.0863", "qty": "300", "realizedPnl": "-0.87", "time": 1781199900000},
        {"side": "BUY", "price": "0.0863", "qty": "199", "realizedPnl": "-0.58", "time": 1781199901000},
    ]

    results = reconcile.reconcile(fake_client, positions={})

    assert len(capture["closes"]) == 1
    close = capture["closes"][0]
    assert close["trade_id"] == 71
    assert close["exit_price"] == pytest.approx(0.0863)
    assert close["realized_pnl_usd"] == pytest.approx(-1.45)
    assert close["realized_pnl_pct"] == pytest.approx(-1.45 / 41.62)
    assert "SL" in close["exit_reason"] and "reconciled" in close["exit_reason"]
    assert capture["alerts"] and capture["alerts"][0][0] == "DOGE"
    assert results[0]["coin"] == "DOGE"
    # Fills were requested from the trade's entry time onward
    assert fake_client.fills_requests[0]["symbol"] == "DOGEUSDT"
    assert fake_client.fills_requests[0]["startTime"] == 1781081656000  # 2026-06-10T08:54:16Z in ms


def test_winning_fill_labelled_tp(fake_client, capture) -> None:
    capture["rows"] = [_row()]
    fake_client.fills = [
        {"side": "BUY", "price": "0.0776", "qty": "499", "realizedPnl": "2.89", "time": 1781199900000},
    ]

    reconcile.reconcile(fake_client, positions={})

    assert "TP" in capture["closes"][0]["exit_reason"]


def test_open_position_left_alone(fake_client, capture) -> None:
    capture["rows"] = [_row(coin="BSV")]
    results = reconcile.reconcile(fake_client, positions={"BSV": {"side": "short"}})
    assert capture["closes"] == [] and capture["alerts"] == [] and results == []


def test_no_fills_falls_back_to_current_price(fake_client, capture) -> None:
    """Retry NO_FILL_RETRY_CYCLES times before booking the price-estimated close."""
    capture["rows"] = [_row()]
    fake_client.fills = []
    fake_client.price = 0.0850

    # First two calls: no close yet — still within the retry window.
    reconcile.reconcile(fake_client, positions={})
    assert capture["closes"] == []

    reconcile.reconcile(fake_client, positions={})
    assert capture["closes"] == []

    # Third call: retry limit hit — book the estimated close.
    reconcile.reconcile(fake_client, positions={})

    close = capture["closes"][0]
    assert close["exit_price"] == pytest.approx(0.0850)
    # short from 0.0834 to 0.0850 = a loss of (0.0834-0.0850)*499
    assert close["realized_pnl_usd"] == pytest.approx((0.0834 - 0.0850) * 499)
    assert "no fills" in close["exit_reason"]


def test_per_row_errors_isolated(fake_client, capture, monkeypatch) -> None:
    """One bad row must not stop the others from reconciling."""
    capture["rows"] = [_row(id=1, coin="AAA", entry_time="not-a-timestamp"), _row(id=2)]
    fake_client.fills = [
        {"side": "BUY", "price": "0.0863", "qty": "499", "realizedPnl": "-1.45", "time": 1781199900000},
    ]

    results = reconcile.reconcile(fake_client, positions={})

    assert [c["trade_id"] for c in capture["closes"]] == [2]
    assert len(results) == 1


def test_reentry_fills_do_not_pollute_older_row(fake_client, capture) -> None:
    """Closing fills of a LATER trade in the same coin (same side) must not be
    blended into a stale row's VWAP/PnL — only the first row.qty of closing
    quantity belongs to this position."""
    capture["rows"] = [_row()]  # short, qty=499
    fake_client.fills = [
        {"side": "BUY", "price": "0.0863", "qty": "300", "realizedPnl": "-0.87", "time": 1781199900000},
        {"side": "BUY", "price": "0.0863", "qty": "199", "realizedPnl": "-0.58", "time": 1781199901000},
        # a later re-entry's closing fills — must be ignored
        {"side": "BUY", "price": "0.0900", "qty": "400", "realizedPnl": "-3.00", "time": 1781290000000},
    ]

    reconcile.reconcile(fake_client, positions={})

    close = capture["closes"][0]
    assert close["exit_price"] == pytest.approx(0.0863)
    assert close["realized_pnl_usd"] == pytest.approx(-1.45)
