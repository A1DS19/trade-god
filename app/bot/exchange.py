"""Binance API wrappers — price data and order execution."""

import functools
import logging
import time

import requests.exceptions
from binance.client import Client
from binance.exceptions import BinanceAPIException

log = logging.getLogger(__name__)

# Transient Binance error codes safe to retry on any call
_RETRYABLE_CODES = {-1003, -1021}  # TOO_MANY_REQUESTS, TIMESTAMP_OUTSIDE_RECV_WINDOW

# For order functions: only retry timestamp drift — rate limit means request may
# have been queued, so retrying risks a double-fill
_RETRYABLE_CODES_ORDER = {-1021}

_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
)


def binance_retry(_func=None, *, codes=_RETRYABLE_CODES, max_attempts=3):
    """Retry decorator for Binance API calls with exponential backoff."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except BinanceAPIException as e:
                    if e.code not in codes:
                        raise
                    last_exc = e
                except _NETWORK_ERRORS as e:
                    last_exc = e
                delay = 2**attempt
                log.warning(
                    "%s transient error — retrying in %ds (%d/%d): %s",
                    func.__name__,
                    delay,
                    attempt + 1,
                    max_attempts,
                    last_exc,
                )
                time.sleep(delay)
            raise last_exc

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator


@binance_retry
def get_price(client: Client, coin: str) -> float:
    ticker = client.get_symbol_ticker(symbol=f"{coin}USDT")
    return float(ticker["price"])


@binance_retry
def get_24h_high(client: Client, coin: str) -> float:
    stats = client.get_ticker(symbol=f"{coin}USDT")
    return float(stats["highPrice"])


@binance_retry
def get_usdt_balance(client: Client) -> float:
    bal = client.get_asset_balance(asset="USDT")
    return float(bal["free"])


@binance_retry(codes=_RETRYABLE_CODES_ORDER)
def buy_market(client: Client, coin: str, usdt_amount: float) -> dict:
    """Market buy using quoteOrderQty (spend exact USDT amount)."""
    return client.order_market_buy(
        symbol=f"{coin}USDT",
        quoteOrderQty=round(usdt_amount, 2),
    )


class BelowMinQtyError(Exception):
    """Raised when qty is below the exchange minimum lot size."""


@binance_retry(codes=_RETRYABLE_CODES_ORDER)
def sell_market(client: Client, coin: str, qty: float) -> dict:
    """Market sell, truncating qty to the symbol's valid lot size."""
    info = client.get_symbol_info(f"{coin}USDT")
    lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    step = float(lot["stepSize"])
    min_qty = float(lot["minQty"])
    if step > 0:
        precision = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
        qty = round(qty - (qty % step), precision)
    if qty < min_qty:
        raise BelowMinQtyError(f"{coin}: qty {qty} below minQty {min_qty}")
    return client.order_market_sell(symbol=f"{coin}USDT", quantity=qty)
