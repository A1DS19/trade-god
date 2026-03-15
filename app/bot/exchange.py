"""Binance API wrappers — price data and order execution."""

import logging
from binance.client import Client

log = logging.getLogger(__name__)


def get_price(client: Client, coin: str) -> float:
    ticker = client.get_symbol_ticker(symbol=f"{coin}USDT")
    return float(ticker["price"])


def get_24h_high(client: Client, coin: str) -> float:
    stats = client.get_ticker(symbol=f"{coin}USDT")
    return float(stats["highPrice"])


def get_usdt_balance(client: Client) -> float:
    bal = client.get_asset_balance(asset="USDT")
    return float(bal["free"])


def buy_market(client: Client, coin: str, usdt_amount: float) -> dict:
    """Market buy using quoteOrderQty (spend exact USDT amount)."""
    return client.order_market_buy(
        symbol=f"{coin}USDT",
        quoteOrderQty=round(usdt_amount, 2),
    )


def sell_market(client: Client, coin: str, qty: float) -> dict:
    """Market sell, truncating qty to the symbol's valid lot size."""
    info = client.get_symbol_info(f"{coin}USDT")
    lot  = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    step = float(lot["stepSize"])
    if step > 0:
        precision = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
        qty = round(qty - (qty % step), precision)
    return client.order_market_sell(symbol=f"{coin}USDT", quantity=qty)
