"""Cancellation must clear BOTH order layers.

Legacy /fapi/v1/allOpenOrders does not cancel Algo-service conditional orders
(the same 2025-12-09 migration that caused -4120 on placement). A close that
only cancels the legacy layer leaves SL/TP triggers armed with
closePosition="true" — they can market-close a future position in the symbol.
"""

from __future__ import annotations

from app.swing import exchange


def test_cancel_open_orders_cancels_both_layers(fake_client) -> None:
    exchange.cancel_open_orders(fake_client, "IOTA")

    # Legacy layer (regular orders)
    assert fake_client.cancelled == [{"symbol": "IOTAUSDT"}]

    # Algo layer (conditional SL/TP orders)
    deletes = [c for c in fake_client.algo_calls if c["method"] == "delete"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "algoOpenOrders"
    assert deletes[0]["signed"] is True
    assert deletes[0]["data"] == {"symbol": "IOTAUSDT"}


def test_cancel_algo_failure_does_not_raise(fake_client, monkeypatch) -> None:
    """A failed algo cancel must not abort the close path — log and continue."""
    from binance.exceptions import BinanceAPIException

    def _raise(*args, **kwargs):
        raise BinanceAPIException(object(), 400, '{"code":-1102,"msg":"bad"}')

    monkeypatch.setattr(fake_client, "_request_futures_api", _raise)
    exchange.cancel_open_orders(fake_client, "IOTA")  # must not raise
    assert fake_client.cancelled == [{"symbol": "IOTAUSDT"}]


def test_cancel_network_failure_does_not_raise(fake_client, monkeypatch) -> None:
    """Network-class errors (not just API rejections) must not abort the close path:
    cancel runs immediately before close_position at every call site."""
    import requests

    def _raise_legacy(**params):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(fake_client, "futures_cancel_all_open_orders", _raise_legacy)
    exchange.cancel_open_orders(fake_client, "IOTA")  # must not raise
    # algo-layer cancel must still be attempted despite the legacy failure
    deletes = [c for c in fake_client.algo_calls if c["method"] == "delete"]
    assert len(deletes) == 1
