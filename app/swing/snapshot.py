"""Assemble a market snapshot dict to feed the agent."""

from binance.client import Client
from app.swing import config
from app.swing.exchange import get_funding_rate, get_open_positions
from app.swing.indicators import get_indicators


def build(client: Client, coin: str) -> dict:
    ind       = get_indicators(client, coin)
    funding   = get_funding_rate(client, coin)
    positions = get_open_positions(client)
    open_pos  = positions.get(coin)
    price     = ind["price"]

    ema9, ema21, ema50 = ind["ema9"], ind["ema21"], ind["ema50"]
    if price > ema9 > ema21 > ema50:
        ema_alignment = "bullish"
    elif price < ema9 < ema21 < ema50:
        ema_alignment = "bearish"
    else:
        ema_alignment = "mixed"

    return {
        "coin":  coin,
        "price": price,
        "indicators": {
            "ema_alignment":   ema_alignment,
            "ema9":            round(ema9, 4),
            "ema21":           round(ema21, 4),
            "ema50":           round(ema50, 4),
            "ema200_daily":    round(ind["ema200_daily"], 4),
            "rsi14_4h":        round(ind["rsi14_4h"], 2),
            "vol_ratio":       ind["vol_ratio"],
            "price_vs_ema9":   round((price - ema9)               / ema9               * 100, 2),
            "price_vs_ema21":  round((price - ema21)              / ema21              * 100, 2),
            "price_vs_ema200": round((price - ind["ema200_daily"]) / ind["ema200_daily"] * 100, 2),
        },
        "candles_4h":       ind["candles_4h"],
        "funding_rate_pct": round(funding * 100, 4),
        "open_position":    open_pos,
        "config": {
            "leverage":      config.LEVERAGE,
            "position_usdt": config.POSITION_USDT,
            "default_sl":    config.DEFAULT_SL_PCT,
            "default_tp":    config.DEFAULT_TP_PCT,
        },
    }
