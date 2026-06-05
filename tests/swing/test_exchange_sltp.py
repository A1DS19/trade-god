"""Unit tests for app.swing.exchange SL/TP placement.

Pins the 2026-06-05 fix: STOP_MARKET / TAKE_PROFIT_MARKET must POST to
/fapi/v1/algoOrder (Binance moved conditional orders to the Algo service on
2025-12-09; the legacy /fapi/v1/order path now rejects them with -4120). These
fail loudly if the code regresses to the old endpoint or the old param shape.
The FakeBinanceClient lives in tests/conftest.py.
"""

from __future__ import annotations

from app.swing import exchange


def _assert_algo_call_shape(call: dict, *, symbol: str, close_side: str) -> dict:
    assert call["method"] == "post"
    assert call["path"] == "algoOrder"          # NOT "order" — the -4120 fix
    assert call["signed"] is True
    d = call["data"]
    assert d["algoType"] == "CONDITIONAL"
    assert d["symbol"] == symbol
    assert d["side"] == close_side
    assert d["closePosition"] == "true"
    assert d["workingType"] == "MARK_PRICE"
    # Legacy params that triggered -4120 / position-mode issues must be gone.
    assert "stopPrice" not in d
    assert "quantity" not in d
    assert "reduceOnly" not in d
    return d


def test_sl_tp_use_algo_endpoint_for_short(fake_client) -> None:
    exchange._place_sl_tp(
        fake_client, "DOGE", "short", qty=301, entry=0.09401, sl_pct=0.0362, tp_pct=0.0724
    )

    assert fake_client.created_orders == []  # never the legacy /fapi/v1/order path
    assert len(fake_client.algo_calls) == 2
    sl, tp = fake_client.algo_calls

    sl_d = _assert_algo_call_shape(sl, symbol="DOGEUSDT", close_side="BUY")
    assert sl_d["type"] == "STOP_MARKET"
    assert sl_d["triggerPrice"] == round(0.09401 * (1 + 0.0362), 4)   # stop ABOVE for a short

    tp_d = _assert_algo_call_shape(tp, symbol="DOGEUSDT", close_side="BUY")
    assert tp_d["type"] == "TAKE_PROFIT_MARKET"
    assert tp_d["triggerPrice"] == round(0.09401 * (1 - 0.0724), 4)   # target BELOW for a short


def test_sl_tp_use_algo_endpoint_for_long(fake_client) -> None:
    exchange._place_sl_tp(
        fake_client, "RENDER", "long", qty=10.4, entry=2.389, sl_pct=0.0547, tp_pct=0.1094
    )

    assert fake_client.created_orders == []
    sl, tp = fake_client.algo_calls

    sl_d = _assert_algo_call_shape(sl, symbol="RENDERUSDT", close_side="SELL")
    assert sl_d["type"] == "STOP_MARKET"
    assert sl_d["triggerPrice"] == round(2.389 * (1 - 0.0547), 4)     # stop BELOW for a long

    tp_d = _assert_algo_call_shape(tp, symbol="RENDERUSDT", close_side="SELL")
    assert tp_d["type"] == "TAKE_PROFIT_MARKET"
    assert tp_d["triggerPrice"] == round(2.389 * (1 + 0.1094), 4)     # target ABOVE for a long


def test_sl_tp_skipped_when_pct_zero(fake_client) -> None:
    exchange._place_sl_tp(fake_client, "IOTA", "long", qty=5, entry=0.20, sl_pct=0.0, tp_pct=0.0)
    assert fake_client.algo_calls == []
    assert fake_client.created_orders == []
