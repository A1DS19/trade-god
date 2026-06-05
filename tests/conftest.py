"""Shared fixtures for the trade-god test suite.

`app.config` / `app.swing.config` read credential env vars at import time, so we
stub them here at import (conftest loads before any test module is collected).
Reusable test doubles live here too, keeping test modules focused on behavior.
"""

from __future__ import annotations

import os

import pytest

# Must run at import time: app modules read these when imported, which happens
# as soon as test modules are collected (conftest is imported first).
_STUB_ENV = {
    "BINANCE_API_KEY": "test",
    "BINANCE_SECRET_KEY": "test",
    "BINANCE_API_KEY_FUTURES": "test",
    "BINANCE_SECRET_KEY_FUTURES": "test",
    "TELEGRAM_BOT_TOKEN": "test",
    "TELEGRAM_CHAT_ID": "test",
    # Valid-looking URL so create_engine() doesn't choke at import; no DB is hit.
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
}
for _key, _value in _STUB_ENV.items():
    os.environ.setdefault(_key, _value)


class FakeBinanceClient:
    """In-memory stand-in for ``binance.Client``.

    Records order calls so tests can assert on them; returns benign defaults for
    market-data / account reads. Seed ``price`` / ``positions`` as needed.
    """

    def __init__(self, *, price: float = 100.0, positions: list | None = None) -> None:
        self.price = price
        self._positions = positions if positions is not None else []
        self.algo_calls: list[dict] = []     # _request_futures_api('post', 'algoOrder', …)
        self.created_orders: list[dict] = []  # futures_create_order(…)
        self.cancelled: list[dict] = []

    # — order endpoints —
    def _request_futures_api(self, method, path, signed=False, **kwargs):
        self.algo_calls.append(
            {"method": method, "path": path, "signed": signed, "data": kwargs.get("data", {})}
        )
        return {"algoId": len(self.algo_calls), "algoStatus": "NEW"}

    def futures_create_order(self, **params):
        self.created_orders.append(params)
        return {"orderId": len(self.created_orders), "status": "NEW", **params}

    def futures_cancel_all_open_orders(self, **params):
        self.cancelled.append(params)
        return {"code": 200, "msg": "success"}

    # — market data / account —
    def futures_symbol_ticker(self, **params):
        return {"price": str(self.price)}

    def futures_position_information(self, **params):
        return list(self._positions)

    def futures_change_leverage(self, **params):
        return {"leverage": params.get("leverage")}


@pytest.fixture
def fake_client():
    """A fresh FakeBinanceClient per test."""
    return FakeBinanceClient()


@pytest.fixture
def snapshot():
    """Factory for a minimal swing snapshot accepted by ``agent.decide()``.

    Defaults are a no-position, mid-RSI, borderline-ADX DOGE row; override any
    field via kwargs. Mirrors ``app.swing.snapshot`` output closely enough for
    the decision logic.
    """

    def _build(
        *,
        coin: str = "DOGE",
        price: float = 0.30,
        regime: str = "trending",
        ema_alignment: str = "mixed",
        daily_ema_alignment: str = "mixed",
        adx: float = 25.5,
        plus_di: float = 29.0,
        minus_di: float = 11.4,
        macd_hist: float = 0.0001,
        macd_hist_prev: float = 0.0,
        rsi: float = 50.0,
    ) -> dict:
        return {
            "coin": coin,
            "price": price,
            "market_regime": regime,
            "indicators": {
                "ema_alignment": ema_alignment,
                "daily_ema_alignment": daily_ema_alignment,
                "ema9": price,
                "ema21": price,
                "ema50": price,
                "ema200_daily": price,
                "rsi14_4h": rsi,
                "vol_ratio": 1.0,
                "price_vs_ema9": 0.0,
                "price_vs_ema21": 0.0,
                "price_vs_ema200": 0.0,
                "adx14": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "macd_hist": macd_hist,
                "macd_hist_prev": macd_hist_prev,
                "oi_change_4h_pct": 0.0,
                "stoch_rsi_k": 50.0,
                "stoch_rsi_d": 50.0,
                "atr_pct_rank": 50.0,
                "vwap": price,
                "price_vs_vwap": 0.0,
                "ls_ratio": 1.0,
                "taker_ratio": 1.0,
            },
            "funding_rate_pct": 0.0,
            "suggested_sl_pct": 0.015,
            "suggested_tp_pct": 0.030,
            "open_position": None,
        }

    return _build
