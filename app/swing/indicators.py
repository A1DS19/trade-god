"""Market indicators for the swing agent — 4h candles, EMAs, RSI, volume."""

import logging
from binance.client import Client

log = logging.getLogger(__name__)


def calc_ema(closes: list[float], period: int) -> float:
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def get_indicators(client: Client, coin: str) -> dict:
    symbol = f"{coin}USDT"

    klines_4h = client.futures_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_4HOUR,
        limit=200,
    )
    closes_4h  = [float(k[4]) for k in klines_4h]
    volumes_4h = [float(k[5]) for k in klines_4h]

    ema9  = calc_ema(closes_4h, 9)
    ema21 = calc_ema(closes_4h, 21)
    ema50 = calc_ema(closes_4h, 50)
    rsi14 = calc_rsi(closes_4h[-30:], 14)

    avg_vol   = sum(volumes_4h[-21:-1]) / 20
    vol_ratio = volumes_4h[-1] / avg_vol if avg_vol > 0 else 1.0

    candles_4h = [
        {
            "open":  float(k[1]),
            "high":  float(k[2]),
            "low":   float(k[3]),
            "close": float(k[4]),
            "vol":   float(k[5]),
        }
        for k in klines_4h[-5:]
    ]

    klines_1d = client.futures_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_1DAY,
        limit=220,
    )
    closes_1d    = [float(k[4]) for k in klines_1d]
    ema200_daily = calc_ema(closes_1d, 200)

    return {
        "price":        closes_4h[-1],
        "ema9":         ema9,
        "ema21":        ema21,
        "ema50":        ema50,
        "ema200_daily": ema200_daily,
        "rsi14_4h":     rsi14,
        "vol_ratio":    round(vol_ratio, 2),
        "candles_4h":   candles_4h,
    }
