"""Binance testnet integration — real Algo-order round-trip (validates the -4120 fix).

OPT-IN / manual: needs a funded USDⓈ-M futures testnet account. Skipped by default
(see the conftest hook). Run with:

    RUN_TESTNET=1 BINANCE_TESTNET_KEY=... BINANCE_TESTNET_SECRET=... \
        python -m pytest -m testnet

This is the ONLY test that exercises the live /fapi/v1/algoOrder contract — the
unit test (FakeBinanceClient) only checks the request shape, not that Binance
actually accepts it.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.testnet

COIN = "DOGE"


@pytest.fixture
def testnet_client():
    key = os.environ.get("BINANCE_TESTNET_KEY")
    secret = os.environ.get("BINANCE_TESTNET_SECRET")
    if not key or not secret:
        pytest.skip("BINANCE_TESTNET_KEY / BINANCE_TESTNET_SECRET not set")
    from binance.client import Client

    return Client(key, secret, testnet=True)


def test_algo_conditional_order_is_accepted(testnet_client):
    """Open a tiny short, then place a STOP_MARKET via the Algo endpoint directly.

    `_place_conditional` raises BinanceAPIException on failure, so a -4120 regression
    fails this test. Position + orders are cleaned up regardless.
    """
    from app.swing import exchange

    client = testnet_client
    symbol = f"{COIN}USDT"
    resp = None
    exchange.open_short(client, COIN, usdt=5.0, leverage=5)  # no SL/TP — placed explicitly below
    try:
        price = exchange.get_price(client, COIN)
        trigger = round(price * 1.05, 5)  # stop above market for a short (out of the money)
        resp = exchange._place_conditional(client, symbol, "BUY", "STOP_MARKET", trigger)
        assert resp.get("algoId"), "algoOrder endpoint did not accept the order (-4120?)"
    finally:
        if resp and resp.get("algoId"):
            try:  # best-effort: 1.0.19 has no algo-cancel wrapper
                client._request_futures_api("delete", "algoOrder", True, data={"algoId": resp["algoId"]})
            except Exception:
                pass
        exchange.cancel_open_orders(client, COIN)
        positions = exchange.get_open_positions(client)
        if COIN in positions:
            exchange.close_position(client, COIN, positions)
