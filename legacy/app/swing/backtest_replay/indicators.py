"""Vectorized O(n) indicator helpers — precompute full series in one pass."""

from __future__ import annotations


def _vs_ema(closes: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    ema = closes[0]
    result = [ema]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
        result.append(ema)
    return result


def _vs_rsi(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) <= period:
        return [50.0] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    result = [50.0] * (period + 1)
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    result.append(100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l))
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        result.append(100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l))
    return result


def _vs_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> list[tuple[float, float]]:
    ef = _vs_ema(closes, fast)
    es = _vs_ema(closes, slow)
    macd_line = [f - s for f, s in zip(ef, es)]
    sig_line = _vs_ema(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, sig_line)]
    warm = slow + signal - 2
    result: list[tuple[float, float]] = [(0.0, 0.0)] * warm
    for i in range(warm, len(hist)):
        result.append((hist[i], hist[i - 1] if i > 0 else 0.0))
    return result


def _vs_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    result = [0.0]
    if len(trs) < period:
        return result + [0.0] * len(trs)
    atr = sum(trs[:period]) / period
    result.extend([0.0] * (period - 1))
    result.append(atr)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
        result.append(atr)
    return result


def _vs_atr_rank(atr_series: list[float], lookback: int = 100) -> list[float]:
    result = [50.0] * len(atr_series)
    for i in range(lookback, len(atr_series)):
        window = atr_series[i - lookback + 1: i + 1]
        cur = atr_series[i]
        result[i] = round(sum(1 for a in window if a <= cur) / len(window) * 100, 1)
    return result


def _wilder_smooth_v(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return [0.0]
    result = [sum(data[:period])]
    for val in data[period:]:
        result.append(result[-1] - result[-1] / period + val)
    return result


def _vs_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[tuple[float, float, float]]:
    """Returns (adx, plus_di, minus_di) per bar; zeros before warmup."""
    n = len(closes)
    result: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * n
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    sm_tr = _wilder_smooth_v(trs, period)
    sm_plus = _wilder_smooth_v(plus_dm, period)
    sm_minus = _wilder_smooth_v(minus_dm, period)
    pdi = [100 * p / t if t > 0 else 0.0 for p, t in zip(sm_plus, sm_tr)]
    mdi = [100 * m / t if t > 0 else 0.0 for m, t in zip(sm_minus, sm_tr)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0 for p, m in zip(pdi, mdi)]
    for j in range(len(pdi)):
        b = period + j
        if b < n:
            result[b] = (0.0, pdi[j], mdi[j])
    if len(dx) >= period:
        adx = sum(dx[:period]) / period
        b0 = 2 * period - 1
        if b0 < n:
            result[b0] = (adx, pdi[period - 1], mdi[period - 1])
        for k, dxv in enumerate(dx[period:]):
            adx = (adx * (period - 1) + dxv) / period
            b = 2 * period + k
            if b < n:
                result[b] = (adx, pdi[period + k], mdi[period + k])
    return result


def _vs_stoch_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14) -> list[tuple[float, float]]:
    rsi_s = _vs_rsi(closes, rsi_period)
    n = len(closes)
    k_series = [50.0] * n
    warm = rsi_period + stoch_period - 1
    for i in range(warm, n):
        window = rsi_s[i - stoch_period + 1: i + 1]
        lo, hi = min(window), max(window)
        k_series[i] = (rsi_s[i] - lo) / (hi - lo) * 100 if hi > lo else 50.0
    result: list[tuple[float, float]] = [(50.0, 50.0)] * n
    for i in range(warm + 2, n):
        d = (k_series[i] + k_series[i - 1] + k_series[i - 2]) / 3
        result[i] = (k_series[i], d)
    return result


def _vs_vwap(klines: list, periods: int = 6) -> list[float]:
    result = [0.0] * len(klines)
    for i in range(periods - 1, len(klines)):
        candles = klines[i - periods + 1: i + 1]
        total_pv = sum((float(k[2]) + float(k[3]) + float(k[4])) / 3 * float(k[5]) for k in candles)
        total_v = sum(float(k[5]) for k in candles)
        result[i] = total_pv / total_v if total_v > 0 else 0.0
    return result


def _vs_vol_ratio(volumes: list[float], window: int = 20) -> list[float]:
    result = [1.0] * len(volumes)
    for i in range(window, len(volumes)):
        avg = sum(volumes[i - window: i]) / window
        result[i] = volumes[i] / avg if avg > 0 else 1.0
    return result
