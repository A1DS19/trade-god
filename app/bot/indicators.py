"""Quant indicators — EMA, RSI, volume ratio. Pure Python, no extra deps."""

import logging
from datetime import datetime
from binance.client import Client
from app.config import INDICATOR_TTL_SECS

log = logging.getLogger(__name__)


def calc_ema(closes: list[float], period: int) -> float:
    """Exponential moving average."""
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
    """RSI using Wilder's smoothing method."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
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
    """
    Fetch 215 daily candles and return:
      ema200    — 200-day EMA of closing prices
      rsi14     — RSI(14) of closing prices
      vol_ratio — today's volume vs 20-day average
    """
    klines = client.get_klines(
        symbol=f"{coin}USDT",
        interval=Client.KLINE_INTERVAL_1DAY,
        limit=215,
    )
    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    ema200 = calc_ema(closes, 200)
    rsi14 = calc_rsi(closes[-30:], 14)
    avg_vol = sum(volumes[-21:-1]) / 20
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    return {"ema200": ema200, "rsi14": rsi14, "vol_ratio": vol_ratio}


def get_cached_indicators(
    client: Client,
    coin: str,
    cache: dict,
    now: datetime,
) -> dict | None:
    """Return indicators from cache if fresh, otherwise fetch and update cache."""
    cached = cache.get(coin)
    if cached:
        age = (now - cached["cached_at"]).total_seconds()
        if age < INDICATOR_TTL_SECS:
            return cached
    try:
        ind = get_indicators(client, coin)
        ind["cached_at"] = now
        cache[coin] = ind
        return ind
    except Exception as e:
        log.error("Failed to get indicators for %s: %s", coin, e)
        return cached  # return stale data rather than nothing
