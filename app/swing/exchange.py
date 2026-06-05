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


def open_long(client: Client, coin: str, usdt: float, leverage: int,
              sl_pct: float = 0.0, tp_pct: float = 0.0) -> dict:
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
    _place_sl_tp(client, coin, "long", qty, price, sl_pct, tp_pct)
    return order


def open_short(client: Client, coin: str, usdt: float, leverage: int,
               sl_pct: float = 0.0, tp_pct: float = 0.0) -> dict:
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
    _place_sl_tp(client, coin, "short", qty, price, sl_pct, tp_pct)
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


def cancel_open_orders(client: Client, coin: str):
    try:
        client.futures_cancel_all_open_orders(symbol=f"{coin}USDT")
    except BinanceAPIException as e:
        log.warning("Could not cancel open orders for %s: %s", coin, e)


def _place_conditional(client: Client, symbol: str, close_side: str,
                       order_type: str, trigger_price: float):
    """Place a position-closing conditional order via the Algo endpoint.

    Binance migrated STOP_MARKET/TAKE_PROFIT_MARKET off POST /fapi/v1/order to the
    Algo service on 2025-12-09; the old path now rejects them with -4120. They must
    go to POST /fapi/v1/algoOrder. python-binance 1.0.19 has no wrapper, so reuse the
    same signed-request helper that futures_create_order itself calls.
    closePosition="true" closes the whole position on trigger (no qty/reduceOnly) and
    auto-cancels the paired order, so SL+TP form a natural OCO.
    """
    return client._request_futures_api("post", "algoOrder", True, data={
        "algoType": "CONDITIONAL",
        "symbol": symbol,
        "side": close_side,
        "type": order_type,
        "triggerPrice": trigger_price,
        "closePosition": "true",
        "workingType": "MARK_PRICE",
    })


def _place_sl_tp(client: Client, coin: str, side: str, qty: float,
                 entry: float, sl_pct: float, tp_pct: float):
    symbol = f"{coin}USDT"
    close_side = "SELL" if side == "long" else "BUY"

    if sl_pct and sl_pct > 0:
        sl_price = entry * (1 - sl_pct) if side == "long" else entry * (1 + sl_pct)
        sl_price = round(sl_price, 4)
        try:
            _place_conditional(client, symbol, close_side, "STOP_MARKET", sl_price)
            log.info("SL placed %s @ %.4f", coin, sl_price)
        except BinanceAPIException as e:
            log.warning("SL placement failed for %s: %s", coin, e)

    if tp_pct and tp_pct > 0:
        tp_price = entry * (1 + tp_pct) if side == "long" else entry * (1 - tp_pct)
        tp_price = round(tp_price, 4)
        try:
            _place_conditional(client, symbol, close_side, "TAKE_PROFIT_MARKET", tp_price)
            log.info("TP placed %s @ %.4f", coin, tp_price)
        except BinanceAPIException as e:
            log.warning("TP placement failed for %s: %s", coin, e)


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
