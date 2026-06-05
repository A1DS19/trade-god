"""Unit tests for app.swing.exchange SL/TP placement.

Pins the 2026-06-05 fix: Binance migrated STOP_MARKET / TAKE_PROFIT_MARKET to the
Algo service (2025-12-09), so protective orders must POST to /fapi/v1/algoOrder,
not /fapi/v1/order (which now rejects them with -4120). These tests fail loudly if
the code ever regresses to the old endpoint or the old param shape.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("BINANCE_API_KEY", "test")
os.environ.setdefault("BINANCE_SECRET_KEY", "test")
os.environ.setdefault("BINANCE_API_KEY_FUTURES", "test")
os.environ.setdefault("BINANCE_SECRET_KEY_FUTURES", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.swing import exchange  # noqa: E402


class FakeClient:
    """Records Algo-endpoint calls; explodes if the legacy order path is used."""

    def __init__(self) -> None:
        self.algo_calls: list[dict] = []

    def _request_futures_api(self, method, path, signed=False, **kwargs):
        self.algo_calls.append(
            {"method": method, "path": path, "signed": signed, "data": kwargs.get("data", {})}
        )
        return {"algoId": 1, "algoStatus": "NEW"}

    def futures_create_order(self, **params):  # pragma: no cover - must never run
        raise AssertionError("SL/TP must not use the legacy /fapi/v1/order endpoint")


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


def test_sl_tp_use_algo_endpoint_for_short() -> None:
    client = FakeClient()
    exchange._place_sl_tp(
        client, "DOGE", "short", qty=301, entry=0.09401, sl_pct=0.0362, tp_pct=0.0724
    )

    assert len(client.algo_calls) == 2
    sl, tp = client.algo_calls

    sl_d = _assert_algo_call_shape(sl, symbol="DOGEUSDT", close_side="BUY")
    assert sl_d["type"] == "STOP_MARKET"
    assert sl_d["triggerPrice"] == round(0.09401 * (1 + 0.0362), 4)   # stop ABOVE for a short

    tp_d = _assert_algo_call_shape(tp, symbol="DOGEUSDT", close_side="BUY")
    assert tp_d["type"] == "TAKE_PROFIT_MARKET"
    assert tp_d["triggerPrice"] == round(0.09401 * (1 - 0.0724), 4)   # target BELOW for a short


def test_sl_tp_use_algo_endpoint_for_long() -> None:
    client = FakeClient()
    exchange._place_sl_tp(
        client, "RENDER", "long", qty=10.4, entry=2.389, sl_pct=0.0547, tp_pct=0.1094
    )

    sl, tp = client.algo_calls

    sl_d = _assert_algo_call_shape(sl, symbol="RENDERUSDT", close_side="SELL")
    assert sl_d["type"] == "STOP_MARKET"
    assert sl_d["triggerPrice"] == round(2.389 * (1 - 0.0547), 4)     # stop BELOW for a long

    tp_d = _assert_algo_call_shape(tp, symbol="RENDERUSDT", close_side="SELL")
    assert tp_d["type"] == "TAKE_PROFIT_MARKET"
    assert tp_d["triggerPrice"] == round(2.389 * (1 + 0.1094), 4)     # target ABOVE for a long


def test_sl_tp_skipped_when_pct_zero() -> None:
    client = FakeClient()
    exchange._place_sl_tp(client, "IOTA", "long", qty=5, entry=0.20, sl_pct=0.0, tp_pct=0.0)
    assert client.algo_calls == []
