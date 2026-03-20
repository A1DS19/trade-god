"""Binance USDT-M Futures: price, positions, open/close orders."""

import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException

log = logging.getLogger(__name__)


def get_price(client: Client, coin: str) -> float:
    ticker = client.futures_symbol_ticker(symbol=f"{coin}USDT")
    return float(ticker["price"])


def get_funding_rate(client: Client, coin: str) -> float:
    rates = client.futures_funding_rate(symbol=f"{coin}USDT", limit=1)
    return float(rates[0]["fundingRate"]) if rates else 0.0


def get_open_positions(client: Client) -> dict[str, dict]:
    """Return open futures positions keyed by coin symbol (e.g. 'BTC')."""
    positions = client.futures_position_information()
    result = {}
    for p in positions:
        qty = float(p["positionAmt"])
        if qty == 0:
            continue
        symbol = p["symbol"]
        if not symbol.endswith("USDT"):
            continue
        coin = symbol[:-4]
        result[coin] = {
            "side":      "long" if qty > 0 else "short",
            "qty":       abs(qty),
            "entry":     float(p["entryPrice"]),
            "pnl":       float(p["unRealizedProfit"]),
            "notional":  abs(float(p["notional"])),
            "leverage":  int(p["leverage"]),
            "liq_price": float(p["liquidationPrice"]),
        }
    return result


def set_leverage(client: Client, coin: str, leverage: int):
    try:
        client.futures_change_leverage(symbol=f"{coin}USDT", leverage=leverage)
    except BinanceAPIException as e:
        log.warning("Could not set leverage for %s: %s", coin, e)


def open_long(client: Client, coin: str, usdt: float, leverage: int) -> dict:
    set_leverage(client, coin, leverage)
    price = get_price(client, coin)
    raw_qty = (usdt * leverage) / price
    qty = _round_qty(client, coin, raw_qty)
    if qty <= 0:
        raise ValueError(f"Position too small for {coin}: ${usdt} x {leverage}x = {raw_qty:.6f} rounds to zero")
    order = client.futures_create_order(
        symbol=f"{coin}USDT",
        side="BUY",
        type="MARKET",
        quantity=qty,
    )
    log.info("OPEN LONG %s qty=%.4f", coin, qty)
    return order


def open_short(client: Client, coin: str, usdt: float, leverage: int) -> dict:
    set_leverage(client, coin, leverage)
    price = get_price(client, coin)
    raw_qty = (usdt * leverage) / price
    qty = _round_qty(client, coin, raw_qty)
    if qty <= 0:
        raise ValueError(f"Position too small for {coin}: ${usdt} x {leverage}x = {raw_qty:.6f} rounds to zero")
    order = client.futures_create_order(
        symbol=f"{coin}USDT",
        side="SELL",
        type="MARKET",
        quantity=qty,
    )
    log.info("OPEN SHORT %s qty=%.4f", coin, qty)
    return order


def close_position(client: Client, coin: str, positions: dict) -> dict | None:
    pos = positions.get(coin)
    if not pos:
        log.warning("close_position: no open position for %s", coin)
        return None
    side = "SELL" if pos["side"] == "long" else "BUY"
    order = client.futures_create_order(
        symbol=f"{coin}USDT",
        side=side,
        type="MARKET",
        quantity=pos["qty"],
        reduceOnly=True,
    )
    log.info("CLOSE %s side=%s qty=%.4f", coin, pos["side"], pos["qty"])
    return order


def _round_qty(client: Client, coin: str, qty: float) -> float:
    info = client.futures_exchange_info()
    for s in info["symbols"]:
        if s["symbol"] == f"{coin}USDT":
            for f in s["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step = float(f["stepSize"])
                    precision = len(f["stepSize"].rstrip("0").split(".")[-1]) if "." in f["stepSize"] else 0
                    return round(qty - (qty % step), precision)
    return round(qty, 3)
