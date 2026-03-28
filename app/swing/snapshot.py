"""Assemble a market snapshot dict to feed the agent."""

from binance.client import Client
from app.swing import config
from app.swing.exchange import get_funding_rate, get_open_positions
from app.swing.indicators import get_indicators


def _ema_alignment(price: float, ema_fast: float, ema_mid: float, ema_slow: float) -> str:
    if price > ema_fast > ema_mid > ema_slow:
        return "bullish"
    if price < ema_fast < ema_mid < ema_slow:
        return "bearish"
    return "mixed"


def build(client: Client, coin: str) -> dict:
    ind       = get_indicators(client, coin)
    funding   = get_funding_rate(client, coin)
    positions = get_open_positions(client)
    open_pos  = positions.get(coin)
    price     = ind["price"]

    # 4h trend direction
    ema_alignment = _ema_alignment(price, ind["ema9"], ind["ema21"], ind["ema50"])

    # Daily bias (ema21/50 stack — slower trend direction)
    daily_ema_alignment = _ema_alignment(
        price, ind["ema21_daily"], ind["ema50_daily"], ind["ema200_daily"]
    )

    # Regime from ADX
    adx = ind["adx14"]
    if adx > 25:
        regime = "trending"
    elif adx >= 20:
        regime = "borderline"
    else:
        regime = "ranging"

    # ATR-based SL/TP (1.5× and 3× ATR, min 1%/2%)
    atr_pct      = ind["atr14"] / price * 100
    suggested_sl = round(max(atr_pct * 1.5, 0.01), 3)
    suggested_tp = round(max(atr_pct * 3.0, 0.02), 3)

    # Strip unrealized PnL — prevents model from anchoring to "profitable position"
    open_pos_for_model = None
    if open_pos:
        open_pos_for_model = {k: v for k, v in open_pos.items() if k != "pnl"}

    return {
        "coin":              coin,
        "price":             price,
        "market_regime":     regime,
        "indicators": {
            "ema_alignment":       ema_alignment,
            "daily_ema_alignment": daily_ema_alignment,
            "ema9":                round(ind["ema9"], 4),
            "ema21":               round(ind["ema21"], 4),
            "ema50":               round(ind["ema50"], 4),
            "ema200_daily":        round(ind["ema200_daily"], 4),
            "rsi14_4h":            round(ind["rsi14_4h"], 2),
            "vol_ratio":           ind["vol_ratio"],
            "price_vs_ema9":       round((price - ind["ema9"])         / ind["ema9"]         * 100, 2),
            "price_vs_ema21":      round((price - ind["ema21"])        / ind["ema21"]        * 100, 2),
            "price_vs_ema200":     round((price - ind["ema200_daily"]) / ind["ema200_daily"] * 100, 2),
            "adx14":               round(adx, 2),
            "plus_di":             round(ind["plus_di"], 2),
            "minus_di":            round(ind["minus_di"], 2),
            "macd_hist":           round(ind["macd_hist"], 6),
            "macd_hist_prev":      round(ind["macd_hist_prev"], 6),
            "oi_change_4h_pct":    ind["oi_change_pct"],
        },
        "candles_4h":        ind["candles_4h"],
        "funding_rate_pct":  round(funding * 100, 4),
        "suggested_sl_pct":  suggested_sl,
        "suggested_tp_pct":  suggested_tp,
        "open_position":     open_pos_for_model,
        "config": {
            "leverage":      config.LEVERAGE,
            "position_usdt": config.POSITION_USDT,
        },
    }
