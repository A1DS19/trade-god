"""Quant indicators — EMA, RSI, MACD, Bollinger Bands, ATR. Pure Python, no extra deps."""

import logging
from datetime import datetime
from binance.client import Client
from app.config import INDICATOR_TTL_SECS

log = logging.getLogger(__name__)


def calc_ema(closes: list[float], period: int) -> float:
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def _calc_ema_series(closes: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    ema = closes[0]
    result = [ema]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
        result.append(ema)
    return result


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


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD histogram and previous bar — used to detect momentum turning points."""
    ema_fast    = _calc_ema_series(closes, fast)
    ema_slow    = _calc_ema_series(closes, slow)
    macd_line   = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _calc_ema_series(macd_line, signal)
    histogram   = [m - s for m, s in zip(macd_line, signal_line)]
    return {
        "macd_hist":      histogram[-1],
        "macd_hist_prev": histogram[-2],
    }


def calc_bollinger(closes: list[float], period: int = 20, std_devs: float = 2.0) -> dict:
    """Bollinger Bands — %B position tells how close price is to the lower band.
    %B < 0.2 = price near or below lower band (oversold relative to recent range).
    """
    window   = closes[-period:]
    mean     = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std      = variance ** 0.5
    lower    = mean - std_devs * std
    upper    = mean + std_devs * std
    price    = closes[-1]
    pct_b    = (price - lower) / (upper - lower) if upper != lower else 0.5
    return {"bb_lower": lower, "bb_upper": upper, "bb_pct_b": round(pct_b, 4)}


def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Wilder's ATR on daily candles."""
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def get_indicators(client: Client, coin: str) -> dict:
    """
    Returns daily indicators:
      ema50         — 50-day EMA
      ema200        — 200-day EMA
      ema200_slope  — True if 200-day EMA is rising (now > 20 days ago)
      ema200_weekly — 200-week EMA
      rsi14         — RSI(14) on daily closes
      vol_ratio     — today's volume vs 20-day average
      macd_hist     — MACD(12,26,9) histogram current bar
      macd_hist_prev— MACD histogram previous bar (detect turning point)
      bb_pct_b      — Bollinger %B (< 0.2 = near lower band = oversold)
      atr14_pct     — ATR(14) as % of current price (dynamic dip sizing)
    """
    klines = client.get_klines(
        symbol=f"{coin}USDT",
        interval=Client.KLINE_INTERVAL_1DAY,
        limit=220,
    )
    closes  = [float(k[4]) for k in klines]
    highs   = [float(k[2]) for k in klines]
    lows    = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    ema50        = calc_ema(closes, 50)
    ema200_now   = calc_ema(closes, 200)
    ema200_prev  = calc_ema(closes[:-20], 200)
    ema200_slope = ema200_now > ema200_prev

    rsi14     = calc_rsi(closes[-30:], 14)
    avg_vol   = sum(volumes[-21:-1]) / 20
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    macd = calc_macd(closes)
    bb   = calc_bollinger(closes)
    atr  = calc_atr(highs, lows, closes)

    # Weekly candles for 200-week EMA (BTC macro filter)
    weekly        = client.get_klines(symbol=f"{coin}USDT",
                                      interval=Client.KLINE_INTERVAL_1WEEK, limit=205)
    weekly_closes = [float(k[4]) for k in weekly]
    ema200_weekly = calc_ema(weekly_closes, 200)

    return {
        "ema50":          ema50,
        "ema200":         ema200_now,
        "ema200_slope":   ema200_slope,
        "ema200_weekly":  ema200_weekly,
        "rsi14":          rsi14,
        "vol_ratio":      round(vol_ratio, 2),
        "macd_hist":      macd["macd_hist"],
        "macd_hist_prev": macd["macd_hist_prev"],
        "bb_pct_b":       bb["bb_pct_b"],
        "bb_lower":       bb["bb_lower"],
        "atr14_pct":      round(atr / closes[-1] * 100, 3),
    }


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
