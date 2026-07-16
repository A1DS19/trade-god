"""Market indicators for the swing agent — 4h candles, EMAs, RSI, MACD, ATR, ADX, OI."""

import logging
import time
from binance.client import Client

log = logging.getLogger(__name__)


def _drop_unclosed(klines: list, now_ms: int | None = None) -> list:
    """Drop the still-forming last candle (close_time in the future).

    Binance always includes the current candle; every indicator here must see
    closed bars only, or signals repaint intra-bar and vol_ratio compares a
    partial candle against full ones.
    """
    if not klines:
        return klines
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if int(klines[-1][6]) > now_ms:
        return klines[:-1]
    return klines


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
    """Returns current MACD histogram and previous bar's histogram for divergence detection."""
    ema_fast   = _calc_ema_series(closes, fast)
    ema_slow   = _calc_ema_series(closes, slow)
    macd_line  = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _calc_ema_series(macd_line, signal)
    histogram  = [m - s for m, s in zip(macd_line, signal_line)]
    return {
        "macd":      macd_line[-1],
        "signal":    signal_line[-1],
        "hist":      histogram[-1],
        "hist_prev": histogram[-2],
    }


def _wilder_smooth(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return [0.0]
    result = [sum(data[:period])]
    for val in data[period:]:
        result.append(result[-1] - result[-1] / period + val)
    return result


def calc_stoch_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14) -> dict:
    """Stochastic RSI — applies Stochastic formula to a rolling RSI series.
    %K < 20 = oversold, %K > 80 = overbought.
    """
    rsi_values = []
    window_size = rsi_period * 2 + 1
    for i in range(rsi_period, len(closes) + 1):
        rsi_values.append(calc_rsi(closes[max(0, i - window_size):i], rsi_period))
    if len(rsi_values) < stoch_period:
        return {"stoch_rsi_k": 50.0, "stoch_rsi_d": 50.0}
    k_values = []
    for i in range(stoch_period - 1, len(rsi_values)):
        window = rsi_values[i - stoch_period + 1: i + 1]
        lo, hi = min(window), max(window)
        k_values.append((rsi_values[i] - lo) / (hi - lo) * 100 if hi > lo else 50.0)
    d = sum(k_values[-3:]) / min(3, len(k_values))
    return {"stoch_rsi_k": round(k_values[-1], 2), "stoch_rsi_d": round(d, 2)}


def _calc_tr_list(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    return [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]))
        for i in range(1, len(closes))
    ]


def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Wilder's ATR — absolute price units."""
    trs = _calc_tr_list(highs, lows, closes)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def calc_atr_percentile(highs: list[float], lows: list[float], closes: list[float],
                        period: int = 14, lookback: int = 100) -> float:
    """Percentile rank of current ATR within its last `lookback` values.
    < 30 = compressed (range), > 70 = expanding (trend/breakout).
    """
    trs = _calc_tr_list(highs, lows, closes)
    if len(trs) < period + lookback:
        return 50.0
    atr = sum(trs[:period]) / period
    series = [atr]
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
        series.append(atr)
    window = series[-lookback:]
    current = window[-1]
    rank = sum(1 for a in window if a <= current) / len(window) * 100
    return round(rank, 1)


def calc_vwap(klines: list, periods: int = 6) -> float:
    """VWAP over last `periods` candles (default 6 × 4h = 24h).
    klines row: [open_time, open, high, low, close, volume, ...]
    """
    candles = klines[-periods:]
    total_pv = sum((float(k[2]) + float(k[3]) + float(k[4])) / 3 * float(k[5]) for k in candles)
    total_v  = sum(float(k[5]) for k in candles)
    return total_pv / total_v if total_v > 0 else 0.0


def calc_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> dict:
    """Wilder's ADX with +DI/-DI. Returns adx, plus_di, minus_di."""
    plus_dm_list, minus_dm_list, tr_list = [], [], []

    for i in range(1, len(closes)):
        up   = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm_list.append(up   if up > down and up > 0   else 0.0)
        minus_dm_list.append(down if down > up and down > 0 else 0.0)
        tr_list.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        ))

    sm_tr    = _wilder_smooth(tr_list,       period)
    sm_plus  = _wilder_smooth(plus_dm_list,  period)
    sm_minus = _wilder_smooth(minus_dm_list, period)

    plus_di  = [100 * p / t if t > 0 else 0.0 for p, t in zip(sm_plus,  sm_tr)]
    minus_di = [100 * m / t if t > 0 else 0.0 for m, t in zip(sm_minus, sm_tr)]

    dx_list = [
        100 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0
        for p, m in zip(plus_di, minus_di)
    ]

    # ADX seed must be an average of DX values, not a Wilder sum
    adx = sum(dx_list[:period]) / period
    for dx in dx_list[period:]:
        adx = (adx * (period - 1) + dx) / period

    return {
        "adx":      adx,
        "plus_di":  plus_di[-1],
        "minus_di": minus_di[-1],
    }


def get_indicators(client: Client, coin: str) -> dict:
    symbol = f"{coin}USDT"

    # ── 4h candles ────────────────────────────────────────────
    klines_4h  = _drop_unclosed(
        client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_4HOUR, limit=200)
    )
    closes_4h  = [float(k[4]) for k in klines_4h]
    highs_4h   = [float(k[2]) for k in klines_4h]
    lows_4h    = [float(k[3]) for k in klines_4h]
    volumes_4h = [float(k[5]) for k in klines_4h]

    ema9  = calc_ema(closes_4h, 9)
    ema21 = calc_ema(closes_4h, 21)
    ema50 = calc_ema(closes_4h, 50)
    rsi14 = calc_rsi(closes_4h, 14)

    avg_vol   = sum(volumes_4h[-21:-1]) / 20
    vol_ratio = volumes_4h[-1] / avg_vol if avg_vol > 0 else 1.0

    macd       = calc_macd(closes_4h)
    atr        = calc_atr(highs_4h, lows_4h, closes_4h)
    adx        = calc_adx(highs_4h, lows_4h, closes_4h)
    stoch_rsi  = calc_stoch_rsi(closes_4h)
    atr_pct_rank = calc_atr_percentile(highs_4h, lows_4h, closes_4h)
    vwap       = calc_vwap(klines_4h)

    candles_4h = [
        {"open":  float(k[1]), "high": float(k[2]),
         "low":   float(k[3]), "close": float(k[4]), "vol": float(k[5])}
        for k in klines_4h[-5:]
    ]

    # ── Daily candles (bias + EMA200) ─────────────────────────
    klines_1d    = _drop_unclosed(
        client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1DAY, limit=601)
    )
    closes_1d    = [float(k[4]) for k in klines_1d]
    ema21_daily  = calc_ema(closes_1d, 21)
    ema50_daily  = calc_ema(closes_1d, 50)
    ema200_daily = calc_ema(closes_1d, 200)

    # ── Open Interest change (4h) ──────────────────────────────
    oi_change_pct = 0.0
    try:
        oi_hist = client.futures_open_interest_hist(symbol=symbol, period="4h", limit=2)
        if len(oi_hist) >= 2:
            oi_now   = float(oi_hist[-1]["sumOpenInterest"])
            oi_prev  = float(oi_hist[-2]["sumOpenInterest"])
            oi_change_pct = (oi_now - oi_prev) / oi_prev * 100 if oi_prev > 0 else 0.0
    except Exception as e:
        log.warning("OI fetch failed for %s: %s", coin, e)

    # ── Long/Short ratio ───────────────────────────────────────
    ls_ratio = 1.0
    try:
        ls_data = client.futures_global_longshort_ratio(symbol=symbol, period="4h", limit=1)
        if ls_data:
            ls_ratio = float(ls_data[-1]["longShortRatio"])
    except Exception as e:
        log.warning("L/S ratio fetch failed for %s: %s", coin, e)

    # ── Taker buy/sell ratio ───────────────────────────────────
    # > 1.0 = aggressive buyers dominate, < 1.0 = aggressive sellers dominate
    taker_ratio = 1.0
    try:
        taker_data = client._request_futures_data_api(
            "get", "takerlongshortRatio", data={"symbol": symbol, "period": "4h", "limit": 1}
        )
        if taker_data:
            taker_ratio = float(taker_data[-1]["buySellRatio"])
    except Exception as e:
        log.warning("Taker ratio fetch failed for %s: %s", coin, e)

    return {
        "price":          closes_4h[-1],
        "ema9":           ema9,
        "ema21":          ema21,
        "ema50":          ema50,
        "ema21_daily":    ema21_daily,
        "ema50_daily":    ema50_daily,
        "ema200_daily":   ema200_daily,
        "rsi14_4h":       rsi14,
        "vol_ratio":      round(vol_ratio, 2),
        "candles_4h":     candles_4h,
        "macd_hist":      macd["hist"],
        "macd_hist_prev": macd["hist_prev"],
        "atr14":          atr,
        "adx14":          adx["adx"],
        "plus_di":        adx["plus_di"],
        "minus_di":       adx["minus_di"],
        "oi_change_pct":  round(oi_change_pct, 2),
        "stoch_rsi_k":    stoch_rsi["stoch_rsi_k"],
        "stoch_rsi_d":    stoch_rsi["stoch_rsi_d"],
        "atr_pct_rank":   atr_pct_rank,
        "vwap":           round(vwap, 6),
        "ls_ratio":       round(ls_ratio, 4),
        "taker_ratio":    round(taker_ratio, 4),
    }
