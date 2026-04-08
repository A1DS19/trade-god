"""Replay backtest for swing strategy: compare legacy v1 vs current v2.

This is an OHLCV replay model (no order book, no latency).
Fees/slippage are configurable via CLI and default to zero.
It is intended for directional comparison of rule sets, not exact live PnL replication.
"""

from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from typing import Any

from binance.client import Client


LEVERAGE = 5
V1_MIN_CONFIDENCE = 0.70
V2_MIN_CONFIDENCE = 0.85
V2_PARTIAL_MIN_ADX = 32.0
V2_PARTIAL_MIN_CONFIDENCE = 0.80
V2_ENABLE_PARTIAL_ENTRIES = False
V2_REQUIRE_DI_ALIGNMENT = True
V2_MIN_TP_TO_COST_MULT = 3.0
V2_MIN_NET_TP_PCT = 0.004
V2_MACD_DIV_EXIT_RSI_SHORT = 32.0       # mirrors config.MACD_DIV_EXIT_RSI_SHORT
V2_MACD_DIV_EXIT_RSI_LONG = 62.0        # mirrors config.MACD_DIV_EXIT_RSI_LONG
V2_MIXED_EMA_EXIT_MIN_LOSS_PCT = 0.005  # mirrors config.MIXED_EMA_EXIT_MIN_LOSS_PCT

# Set in main() before threads start; read-only during replay.
_DISABLE_MIXED_EMA_EXIT: bool = False


# ---------------------------------------------------------------------------
# Vectorized O(n) indicator helpers — precompute full series in one pass.
# These replace per-bar recomputation from scratch (which was O(n²) overall).
# ---------------------------------------------------------------------------

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
    # sm_*[j] aligns to bar index (period + j)
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


def _parse_iso_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _ema_alignment(price: float, ema_fast: float, ema_mid: float, ema_slow: float) -> str:
    if price > ema_fast > ema_mid > ema_slow:
        return "bullish"
    if price < ema_fast < ema_mid < ema_slow:
        return "bearish"
    return "mixed"


def _position_size_usdt_v2(confidence: float) -> float:
    lo = 5.0
    hi = 10.0
    floor = V2_MIN_CONFIDENCE
    cap = 0.95
    x = min(max(confidence, floor), cap)
    ratio = (x - floor) / (cap - floor)
    return round(lo + (hi - lo) * ratio, 2)


def _map_confidence(score: float) -> float:
    if score >= 0.12:
        return round(0.85 + min(score - 0.12, 0.09), 2)
    if score >= 0.07:
        return round(0.75 + (score - 0.07) / 0.05 * 0.09, 2)
    if score >= 0.03:
        return round(0.70 + (score - 0.03) / 0.04 * 0.04, 2)
    return round(0.60 + max(score, -0.10) * 0.5, 2)


def _score_entry_common(
    direction: str,
    regime: str,
    rsi: float,
    vol: float,
    funding: float,
    oi_chg: float,
    vs_ema200: float,
    plus_di: float,
    minus_di: float,
    macd: float,
    macd_p: float,
    stoch_k: float,
    atr_rank: float,
    vs_vwap: float,
    ls_ratio: float,
    taker_ratio: float,
    *,
    rsi_soft_v2: bool,
    partial_mode: bool,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    def add(delta: float, label: str) -> None:
        nonlocal score
        score += delta
        reasons.append(f"{'+' if delta >= 0 else '-'}{abs(delta):.2f} {label}")

    if partial_mode:
        add(-0.04, "partial 4h alignment")

    if vol > 1.5:
        add(0.05, f"vol {vol:.2f}↑")
    if direction == "short" and funding > 0.05:
        add(0.04, f"funding +{funding:.4f}% (crowded longs)")
    elif direction == "long" and funding < -0.05:
        add(0.04, f"funding {funding:.4f}% (crowded shorts)")

    if direction == "short" and oi_chg > 1 and macd < macd_p * 0.95:
        add(0.04, f"OI +{oi_chg:.1f}% (new shorts)")
    elif direction == "long" and oi_chg > 1 and macd > macd_p * 1.05:
        add(0.04, f"OI +{oi_chg:.1f}% (new longs)")

    if 40 <= rsi <= 60:
        add(0.03, f"RSI {rsi:.1f} healthy")

    if direction == "short" and vs_ema200 < 0:
        add(0.03, f"price {vs_ema200:.1f}% below EMA200")
    elif direction == "long" and vs_ema200 > 0:
        add(0.03, f"price +{vs_ema200:.1f}% above EMA200")

    if direction == "short" and minus_di > plus_di:
        add(0.04, f"-DI {minus_di:.1f} > +DI {plus_di:.1f}")
    elif direction == "long" and plus_di > minus_di:
        add(0.04, f"+DI {plus_di:.1f} > -DI {minus_di:.1f}")

    if direction == "short" and stoch_k > 80:
        add(0.04, f"StochRSI {stoch_k:.0f} overbought")
    elif direction == "long" and stoch_k < 20:
        add(0.04, f"StochRSI {stoch_k:.0f} oversold")

    if direction == "short" and ls_ratio >= 2.0:
        add(0.04, f"L/S ratio {ls_ratio:.2f} (crowded longs)")
    elif direction == "long" and ls_ratio <= 0.5:
        add(0.04, f"L/S ratio {ls_ratio:.2f} (crowded shorts)")

    if direction == "short" and taker_ratio < 0.8:
        add(0.03, f"taker ratio {taker_ratio:.2f} (sellers aggressive)")
    elif direction == "long" and taker_ratio > 1.2:
        add(0.03, f"taker ratio {taker_ratio:.2f} (buyers aggressive)")

    if atr_rank > 70:
        add(0.03, f"ATR rank {atr_rank:.0f}% (vol expanding)")

    if direction == "short" and vs_vwap < 0:
        add(0.03, f"price {vs_vwap:.1f}% below VWAP")
    elif direction == "long" and vs_vwap > 0:
        add(0.03, f"price +{vs_vwap:.1f}% above VWAP")

    # Contradicting
    if rsi_soft_v2:
        if direction == "short" and rsi < 42:
            add(-0.05, f"RSI {rsi:.1f} below short comfort 42")
        elif direction == "long" and rsi > 58:
            add(-0.05, f"RSI {rsi:.1f} above long comfort 58")
        if direction == "short" and rsi < 36:
            add(-0.04, f"RSI {rsi:.1f} deeply oversold")
        elif direction == "long" and rsi > 64:
            add(-0.04, f"RSI {rsi:.1f} deeply overbought")
    else:
        if direction == "short" and rsi < 45:
            add(-0.05, f"RSI {rsi:.1f} near oversold")
        elif direction == "long" and rsi > 55:
            add(-0.05, f"RSI {rsi:.1f} near overbought")

    if direction == "short" and funding < -0.05:
        add(-0.04, f"funding {funding:.4f}% opposes short")
    elif direction == "long" and funding > 0.05:
        add(-0.04, f"funding +{funding:.4f}% opposes long")

    if oi_chg < -2:
        add(-0.04, f"OI {oi_chg:.1f}% (positions closing)")

    if direction == "short" and macd > macd_p:
        add(-0.04, "MACD hist improving (contra short)")
    elif direction == "long" and macd < macd_p:
        add(-0.04, "MACD hist deteriorating (contra long)")

    if direction == "short" and stoch_k < 20:
        add(-0.03, f"StochRSI {stoch_k:.0f} already oversold (contra short)")
    elif direction == "long" and stoch_k > 80:
        add(-0.03, f"StochRSI {stoch_k:.0f} already overbought (contra long)")

    if direction == "short" and taker_ratio > 1.2:
        add(-0.02, f"taker ratio {taker_ratio:.2f} (buyers aggressive, contra short)")
    elif direction == "long" and taker_ratio < 0.8:
        add(-0.02, f"taker ratio {taker_ratio:.2f} (sellers aggressive, contra long)")

    if atr_rank < 30:
        add(-0.03, f"ATR rank {atr_rank:.0f}% (vol compressed, poor trend)")

    if direction == "short" and vs_vwap > 2:
        add(-0.02, f"price +{vs_vwap:.1f}% above VWAP (contra short)")
    elif direction == "long" and vs_vwap < -2:
        add(-0.02, f"price {vs_vwap:.1f}% below VWAP (contra long)")

    if regime == "borderline":
        add(-0.08, "ADX borderline penalty")

    return _map_confidence(score), reasons


def _check_short_exit(ema4h: str, ema_d: str, rsi: float, macd: float, macd_p: float, oi_chg: float, adx: float, unrealized_pct: float | None = None) -> str | None:
    if ema4h == "bullish":
        return "4h EMA turned bullish"
    if ema_d == "bullish":
        return "daily EMA turned bullish"
    if not _DISABLE_MIXED_EMA_EXIT and ema4h == "mixed" and macd > macd_p and adx < 25:
        if unrealized_pct is None or unrealized_pct < -V2_MIXED_EMA_EXIT_MIN_LOSS_PCT:
            return "4h EMA mixed + MACD weakening"
    if rsi < 32:
        return "RSI deep oversold"
    if macd > macd_p and rsi < V2_MACD_DIV_EXIT_RSI_SHORT:
        return "MACD divergence (short)"
    if oi_chg < -3 and macd > macd_p:
        return "OI falling (shorts covering)"
    if adx < 20:
        return "ADX trend collapsed"
    return None


def _check_long_exit(ema4h: str, ema_d: str, rsi: float, macd: float, macd_p: float, oi_chg: float, adx: float, unrealized_pct: float | None = None) -> str | None:
    if ema4h == "bearish":
        return "4h EMA turned bearish"
    if ema_d == "bearish":
        return "daily EMA turned bearish"
    if not _DISABLE_MIXED_EMA_EXIT and ema4h == "mixed" and macd < macd_p and adx < 25:
        if unrealized_pct is None or unrealized_pct < -V2_MIXED_EMA_EXIT_MIN_LOSS_PCT:
            return "4h EMA mixed + MACD weakening"
    if rsi > 68:
        return "RSI deep overbought"
    if macd < macd_p and rsi > V2_MACD_DIV_EXIT_RSI_LONG:
        return "MACD divergence (long)"
    if oi_chg < -3 and macd < macd_p:
        return "OI falling (longs covering)"
    if adx < 20:
        return "ADX trend collapsed"
    return None


def _partial_ok(direction: str, price: float, ema9: float, ema21: float, ema50: float) -> bool:
    if direction == "short":
        return price < ema9 < ema21 and ema21 >= ema50
    return price > ema9 > ema21 and ema21 <= ema50


def decide_v2(snapshot: dict[str, Any]) -> dict[str, Any]:
    ind = snapshot["indicators"]
    regime = snapshot["market_regime"]
    pos = snapshot.get("open_position")

    ema4h = ind["ema_alignment"]
    ema_d = ind["daily_ema_alignment"]
    rsi = ind["rsi14_4h"]
    adx = ind["adx14"]
    macd = ind["macd_hist"]
    macd_p = ind["macd_hist_prev"]
    oi = ind["oi_change_4h_pct"]

    if pos:
        entry = float(pos.get("entry", 0))
        price = snapshot["price"]
        if entry > 0:
            unrealized_pct: float | None = (price - entry) / entry if pos["side"] == "long" else (entry - price) / entry
        else:
            unrealized_pct = None
        reason = _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx, unrealized_pct) if pos["side"] == "short" else _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx, unrealized_pct)
        if reason:
            return {"action": "close", "confidence": 0.0, "reasoning": reason}
        return {"action": "hold", "confidence": 0.7, "reasoning": "hold"}

    if regime == "ranging":
        return {"action": "hold", "confidence": 0.0, "reasoning": "ranging"}

    direction: str | None = None
    entry_mode = "strict"
    for d in ("short", "long"):
        req = "bearish" if d == "short" else "bullish"
        if ema_d != req:
            continue
        if (d == "short" and macd >= 0) or (d == "long" and macd <= 0):
            continue
        if adx < 32:
            continue
        if V2_REQUIRE_DI_ALIGNMENT:
            plus_di = float(ind["plus_di"])
            minus_di = float(ind["minus_di"])
            if d == "short" and minus_di <= plus_di:
                continue
            if d == "long" and plus_di <= minus_di:
                continue
        if ema4h == req:
            direction = d
            entry_mode = "strict"
            break
        if (
            V2_ENABLE_PARTIAL_ENTRIES
            and
            ema4h == "mixed"
            and adx >= V2_PARTIAL_MIN_ADX
            and _partial_ok(d, snapshot["price"], ind["ema9"], ind["ema21"], ind["ema50"])
        ):
            direction = d
            entry_mode = "partial"
            break

    if direction is None:
        return {"action": "hold", "confidence": 0.0, "reasoning": "no entry"}

    conf, reasons = _score_entry_common(
        direction,
        regime,
        rsi,
        ind["vol_ratio"],
        snapshot["funding_rate_pct"],
        oi,
        ind["price_vs_ema200"],
        ind["plus_di"],
        ind["minus_di"],
        macd,
        macd_p,
        ind["stoch_rsi_k"],
        ind["atr_pct_rank"],
        ind["price_vs_vwap"],
        ind["ls_ratio"],
        ind["taker_ratio"],
        rsi_soft_v2=True,
        partial_mode=(entry_mode == "partial"),
    )
    if conf < V2_MIN_CONFIDENCE:
        return {"action": "hold", "confidence": conf, "reasoning": "; ".join(reasons)}
    if entry_mode == "partial" and conf < V2_PARTIAL_MIN_CONFIDENCE:
        return {"action": "hold", "confidence": conf, "reasoning": "; ".join(reasons)}

    return {
        "action": direction,
        "confidence": conf,
        "sl_pct": snapshot["suggested_sl_pct"],
        "tp_pct": snapshot["suggested_tp_pct"],
        "reasoning": "; ".join(reasons),
    }


def decide_v1(snapshot: dict[str, Any]) -> dict[str, Any]:
    ind = snapshot["indicators"]
    regime = snapshot["market_regime"]
    pos = snapshot.get("open_position")

    ema4h = ind["ema_alignment"]
    ema_d = ind["daily_ema_alignment"]
    rsi = ind["rsi14_4h"]
    adx = ind["adx14"]
    macd = ind["macd_hist"]
    macd_p = ind["macd_hist_prev"]
    oi = ind["oi_change_4h_pct"]

    if pos:
        reason = _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx) if pos["side"] == "short" else _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx)
        if reason:
            return {"action": "close", "confidence": 0.0, "reasoning": reason}
        return {"action": "hold", "confidence": 0.7, "reasoning": "hold"}

    if regime == "ranging":
        return {"action": "hold", "confidence": 0.0, "reasoning": "ranging"}

    direction: str | None = None
    for d in ("short", "long"):
        req = "bearish" if d == "short" else "bullish"
        if ema_d != req:
            continue
        if ema4h != req:
            continue
        if (d == "short" and macd >= 0) or (d == "long" and macd <= 0):
            continue
        if adx <= 32:
            continue
        if d == "short" and rsi <= 42:
            continue
        if d == "long" and rsi >= 58:
            continue
        direction = d
        break

    if direction is None:
        return {"action": "hold", "confidence": 0.0, "reasoning": "no entry"}

    conf, reasons = _score_entry_common(
        direction,
        regime,
        rsi,
        ind["vol_ratio"],
        snapshot["funding_rate_pct"],
        oi,
        ind["price_vs_ema200"],
        ind["plus_di"],
        ind["minus_di"],
        macd,
        macd_p,
        ind["stoch_rsi_k"],
        ind["atr_pct_rank"],
        ind["price_vs_vwap"],
        ind["ls_ratio"],
        ind["taker_ratio"],
        rsi_soft_v2=False,
        partial_mode=False,
    )
    if conf < V1_MIN_CONFIDENCE:
        return {"action": "hold", "confidence": conf, "reasoning": "; ".join(reasons)}

    return {
        "action": direction,
        "confidence": conf,
        "sl_pct": snapshot["suggested_sl_pct"],
        "tp_pct": snapshot["suggested_tp_pct"],
        "reasoning": "; ".join(reasons),
    }


@dataclass
class Position:
    side: str
    entry_price: float
    qty: float
    notional: float
    sl_pct: float
    tp_pct: float
    entry_time: int
    entry_fee: float = 0.0
    entry_rsi: float = 0.0
    entry_adx: float = 0.0
    entry_conf: float = 0.0
    entry_regime: str = ""


@dataclass
class Trade:
    coin: str
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    gross_pnl: float
    total_fees: float
    exit_reason: str
    confidence: float
    entry_rsi: float = 0.0
    entry_adx: float = 0.0
    entry_regime: str = ""


@dataclass
class StrategyState:
    name: str
    fee_rate: float
    slippage_rate: float
    position: Position | None = None
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=lambda: [0.0])
    entries_conf: list[float] = field(default_factory=list)

    def _apply_exit_slippage(self, side: str, price: float) -> float:
        if self.slippage_rate <= 0:
            return price
        if side == "long":
            return price * (1 - self.slippage_rate)
        return price * (1 + self.slippage_rate)

    def close(self, coin: str, now_ms: int, price: float, reason: str, confidence: float = 0.0) -> None:
        if not self.position:
            return
        p = self.position
        exit_price = self._apply_exit_slippage(p.side, price)
        gross_pnl = (exit_price - p.entry_price) * p.qty if p.side == "long" else (p.entry_price - exit_price) * p.qty
        exit_notional = abs(exit_price * p.qty)
        exit_fee = exit_notional * self.fee_rate
        total_fees = p.entry_fee + exit_fee
        pnl = gross_pnl - total_fees
        pnl_pct = pnl / p.notional if p.notional else 0.0
        self.trades.append(
            Trade(
                coin=coin,
                side=p.side,
                entry_time=p.entry_time,
                exit_time=now_ms,
                entry_price=p.entry_price,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                entry_rsi=p.entry_rsi,
                entry_adx=p.entry_adx,
                entry_regime=p.entry_regime,
                gross_pnl=gross_pnl,
                total_fees=total_fees,
                exit_reason=reason,
                confidence=p.entry_conf,
            )
        )
        self.equity_curve.append(self.equity_curve[-1] + pnl)
        self.position = None


class ReplayEngine:
    def __init__(
        self,
        coins: list[str],
        start: datetime,
        end: datetime,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ):
        self.coins = coins
        self.start = start
        self.end = end
        self.fee_rate = max(fee_bps, 0.0) / 10_000.0
        self.slippage_rate = max(slippage_bps, 0.0) / 10_000.0

    def _v2_expected_move_ok(self, tp_pct: float) -> bool:
        roundtrip_cost_pct = 2.0 * (self.fee_rate + self.slippage_rate)
        required_tp_pct = roundtrip_cost_pct * V2_MIN_TP_TO_COST_MULT
        net_tp_pct = tp_pct - roundtrip_cost_pct
        return tp_pct >= required_tp_pct and net_tp_pct >= V2_MIN_NET_TP_PCT

    @staticmethod
    def _interval_ms(interval: str) -> int:
        if interval == Client.KLINE_INTERVAL_4HOUR:
            return 4 * 60 * 60 * 1000
        if interval == Client.KLINE_INTERVAL_1DAY:
            return 24 * 60 * 60 * 1000
        raise ValueError(f"Unsupported interval: {interval}")

    def _fetch_klines(self, client: Client, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list[Any]]:
        out: list[list[Any]] = []
        cursor = start_ms
        step = self._interval_ms(interval)
        prev_last_open = -1
        while True:
            batch = client.futures_klines(
                symbol=symbol,
                interval=interval,
                startTime=cursor,
                endTime=end_ms,
                limit=1500,
            )
            if not batch:
                break
            out.extend(batch)
            last_open = int(batch[-1][0])
            if last_open <= prev_last_open:
                break
            prev_last_open = last_open
            next_cursor = last_open + step
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(batch) < 1500:
                break
        return out

    def _precompute_coin(self, kl4: list[list[Any]], kl1d: list[list[Any]]) -> list[dict[str, Any] | None]:
        """Precompute all indicator series once (O(n)) and return per-bar snapshots."""
        import bisect
        closes4 = [float(k[4]) for k in kl4]
        highs4 = [float(k[2]) for k in kl4]
        lows4 = [float(k[3]) for k in kl4]
        volumes4 = [float(k[5]) for k in kl4]

        ema9_s = _vs_ema(closes4, 9)
        ema21_s = _vs_ema(closes4, 21)
        ema50_s = _vs_ema(closes4, 50)
        rsi_s = _vs_rsi(closes4, 14)
        macd_s = _vs_macd(closes4)
        atr_s = _vs_atr(highs4, lows4, closes4)
        atr_rank_s = _vs_atr_rank(atr_s)
        adx_s = _vs_adx(highs4, lows4, closes4)
        stoch_s = _vs_stoch_rsi(closes4)
        vwap_s = _vs_vwap(kl4)
        vol_ratio_s = _vs_vol_ratio(volumes4)

        closes1d = [float(k[4]) for k in kl1d]
        d_close_times = [int(k[6]) for k in kl1d]
        ema21_d_s = _vs_ema(closes1d, 21)
        ema50_d_s = _vs_ema(closes1d, 50)
        ema200_d_s = _vs_ema(closes1d, 200)

        results: list[dict[str, Any] | None] = []
        for i in range(len(kl4)):
            if i < 199:
                results.append(None)
                continue
            close_time_ms = int(kl4[i][6])
            # last daily bar whose close_time <= 4h bar's close_time
            d_idx = bisect.bisect_right(d_close_times, close_time_ms) - 1
            if d_idx < 199:
                results.append(None)
                continue

            price = closes4[i]
            adx_val, plus_di, minus_di = adx_s[i]
            macd_hist, macd_hist_prev = macd_s[i]
            stoch_k, stoch_d = stoch_s[i]
            atr = atr_s[i]
            ema200_d = ema200_d_s[d_idx]

            ema_alignment = _ema_alignment(price, ema9_s[i], ema21_s[i], ema50_s[i])
            daily_alignment = _ema_alignment(price, ema21_d_s[d_idx], ema50_d_s[d_idx], ema200_d)
            regime = "trending" if adx_val > 25 else ("borderline" if adx_val >= 20 else "ranging")

            atr_frac = atr / price if price > 0 else 0.0
            results.append({
                "close_time_ms": close_time_ms,
                "price": price,
                "high": highs4[i],
                "low": lows4[i],
                "market_regime": regime,
                "funding_rate_pct": 0.0,
                "suggested_sl_pct": round(max(atr_frac * 1.5, 0.01), 4),
                "suggested_tp_pct": round(max(atr_frac * 3.0, 0.02), 4),
                "open_position": None,
                "indicators": {
                    "ema_alignment": ema_alignment,
                    "daily_ema_alignment": daily_alignment,
                    "ema9": ema9_s[i],
                    "ema21": ema21_s[i],
                    "ema50": ema50_s[i],
                    "ema200_daily": ema200_d,
                    "rsi14_4h": rsi_s[i],
                    "vol_ratio": round(vol_ratio_s[i], 2),
                    "price_vs_ema200": (price - ema200_d) / ema200_d * 100 if ema200_d else 0.0,
                    "adx14": adx_val,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                    "macd_hist": macd_hist,
                    "macd_hist_prev": macd_hist_prev,
                    "oi_change_4h_pct": 0.0,
                    "stoch_rsi_k": stoch_k,
                    "stoch_rsi_d": stoch_d,
                    "atr_pct_rank": atr_rank_s[i],
                    "vwap": vwap_s[i],
                    "price_vs_vwap": (price - vwap_s[i]) / vwap_s[i] * 100 if vwap_s[i] else 0.0,
                    "ls_ratio": 1.0,
                    "taker_ratio": 1.0,
                },
            })
        return results

    def _handle_intrabar_sl_tp(self, state: StrategyState, coin: str, now_ms: int, high: float, low: float) -> bool:
        pos = state.position
        if not pos:
            return False

        if pos.side == "long":
            sl_price = pos.entry_price * (1 - pos.sl_pct)
            tp_price = pos.entry_price * (1 + pos.tp_pct)
            hit_sl = low <= sl_price
            hit_tp = high >= tp_price
        else:
            sl_price = pos.entry_price * (1 + pos.sl_pct)
            tp_price = pos.entry_price * (1 - pos.tp_pct)
            hit_sl = high >= sl_price
            hit_tp = low <= tp_price

        if not hit_sl and not hit_tp:
            return False

        # Conservative tie-break: if both hit in same bar, assume stop first.
        if hit_sl:
            state.close(coin, now_ms, sl_price, "SL", 0.0)
        else:
            state.close(coin, now_ms, tp_price, "TP", 0.0)
        return True

    def _run_coin(self, coin: str) -> tuple[StrategyState, StrategyState, int]:
        client = Client()  # one client per thread to avoid session sharing
        symbol = f"{coin}USDT"
        start_ms = _to_ms(self.start)
        end_ms = _to_ms(self.end)

        kl4 = self._fetch_klines(client, symbol, Client.KLINE_INTERVAL_4HOUR, start_ms, end_ms)
        kl1d = self._fetch_klines(client, symbol, Client.KLINE_INTERVAL_1DAY, start_ms - int(timedelta(days=250).total_seconds() * 1000), end_ms)

        precomputed = self._precompute_coin(kl4, kl1d)

        s_v1 = StrategyState(name="v1", fee_rate=self.fee_rate, slippage_rate=self.slippage_rate)
        s_v2 = StrategyState(name="v2", fee_rate=self.fee_rate, slippage_rate=self.slippage_rate)
        bars = 0

        for snap in precomputed:
            if snap is None:
                continue
            bars += 1
            now_ms = snap["close_time_ms"]
            close_price = snap["price"]
            high = snap["high"]
            low = snap["low"]

            for state, decide_fn in ((s_v1, decide_v1), (s_v2, decide_v2)):
                # Exchange-side SL/TP emulation first
                if self._handle_intrabar_sl_tp(state, coin, now_ms, high, low):
                    continue

                local_snap = dict(snap)
                local_snap["open_position"] = None
                if state.position:
                    local_snap["open_position"] = {
                        "side": state.position.side,
                        "qty": state.position.qty,
                        "entry": state.position.entry_price,
                        "notional": state.position.notional,
                    }

                decision = decide_fn(local_snap)
                action = decision["action"]

                if action == "close" and state.position:
                    state.close(coin, now_ms, close_price, decision.get("reasoning", "rule-close"), 0.0)
                    continue

                if action in ("long", "short") and state.position is None:
                    conf = float(decision.get("confidence", 0.0))
                    min_conf = V1_MIN_CONFIDENCE if state.name == "v1" else V2_MIN_CONFIDENCE
                    if conf < min_conf:
                        continue
                    if state.name == "v2":
                        tp_pct = float(decision.get("tp_pct", 0.0) or 0.0)
                        if not self._v2_expected_move_ok(tp_pct):
                            continue
                    usdt = 5.0 if state.name == "v1" else _position_size_usdt_v2(conf)
                    notional = usdt * LEVERAGE
                    if state.slippage_rate > 0:
                        if action == "long":
                            entry_price = close_price * (1 + state.slippage_rate)
                        else:
                            entry_price = close_price * (1 - state.slippage_rate)
                    else:
                        entry_price = close_price
                    qty = notional / entry_price if entry_price > 0 else 0.0
                    if qty <= 0:
                        continue
                    entry_fee = abs(entry_price * qty) * state.fee_rate
                    state.entries_conf.append(conf)
                    ind = local_snap["indicators"]
                    state.position = Position(
                        side=action,
                        entry_price=entry_price,
                        qty=qty,
                        notional=notional,
                        sl_pct=float(decision.get("sl_pct", 0.03) or 0.03),
                        tp_pct=float(decision.get("tp_pct", 0.08) or 0.08),
                        entry_time=now_ms,
                        entry_fee=entry_fee,
                        entry_rsi=ind["rsi14_4h"],
                        entry_adx=ind["adx14"],
                        entry_conf=conf,
                        entry_regime=local_snap["market_regime"],
                    )

        # Mark-to-market close at final bar close
        if bars > 0:
            last_close = float(kl4[-1][4])
            last_time = int(kl4[-1][6])
            if s_v1.position:
                s_v1.close(coin, last_time, last_close, "EOD", 0.0)
            if s_v2.position:
                s_v2.close(coin, last_time, last_close, "EOD", 0.0)

        return s_v1, s_v2, bars


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for x in equity_curve:
        peak = max(peak, x)
        dd = peak - x
        mdd = max(mdd, dd)
    return mdd


def _summarize(state: StrategyState) -> dict[str, float]:
    trades = state.trades
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "avg_conf": 0.0,
            "gross_pnl": 0.0,
            "total_fees": 0.0,
        }

    pnls = [t.pnl for t in trades]
    gross_pnls = [t.gross_pnl for t in trades]
    total_fees = sum(t.total_fees for t in trades)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": float(len(trades)),
        "win_rate": len(wins) / len(trades),
        "net_pnl": sum(pnls),
        "avg_pnl": mean(pnls),
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "max_drawdown": _max_drawdown(state.equity_curve),
        "avg_conf": mean(state.entries_conf) if state.entries_conf else 0.0,
        "gross_pnl": sum(gross_pnls),
        "total_fees": total_fees,
    }


def _exit_breakdown(trades: list[Trade]) -> dict[str, dict]:
    """Group trades by exit reason; return count/win_rate/avg_pnl/median_pnl per reason."""
    buckets: dict[str, list[float]] = {}
    for t in trades:
        buckets.setdefault(t.exit_reason, []).append(t.pnl)
    result = {}
    for reason, pnls in sorted(buckets.items(), key=lambda x: -len(x[1])):
        wins = sum(1 for p in pnls if p > 0)
        result[reason] = {
            "count": len(pnls),
            "wins": wins,
            "win_rate": wins / len(pnls),
            "net_pnl": sum(pnls),
            "avg_pnl": mean(pnls),
            "median_pnl": median(pnls),
        }
    return result


def _print_exit_breakdown(title: str, v1_trades: list[Trade], v2_trades: list[Trade]) -> None:
    print(f"\n{title}")
    for label, trades in (("v1", v1_trades), ("v2", v2_trades)):
        bd = _exit_breakdown(trades)
        if not bd:
            continue
        print(f"\n  [{label}]  exit_reason | count | win_rate | net_pnl | avg_pnl | median_pnl")
        print(f"  {'─' * 85}")
        for reason, s in bd.items():
            print(
                f"  {reason:<45} | {s['count']:>5} | {_fmt_pct(s['win_rate']):>8} "
                f"| {s['net_pnl']:>8.2f} | {s['avg_pnl']:>8.3f} | {s['median_pnl']:>10.3f}"
            )


def _print_entry_analysis(title: str, v1_trades: list[Trade], v2_trades: list[Trade]) -> None:
    """For each exit reason, show avg entry RSI, ADX, confidence, and long/short split."""
    print(f"\n{title}")
    for label, trades in (("v1", v1_trades), ("v2", v2_trades)):
        if not trades:
            continue
        buckets: dict[str, list[Trade]] = {}
        for t in trades:
            buckets.setdefault(t.exit_reason, []).append(t)
        print(f"\n  [{label}]  exit_reason | n | long% | avg_rsi | avg_adx | avg_conf | trending% | net_pnl")
        print(f"  {'─' * 95}")
        for reason, ts in sorted(buckets.items(), key=lambda x: -len(x[1])):
            long_pct = sum(1 for t in ts if t.side == "long") / len(ts) * 100
            avg_rsi = mean(t.entry_rsi for t in ts)
            avg_adx = mean(t.entry_adx for t in ts)
            avg_conf = mean(t.confidence for t in ts)
            trending_pct = sum(1 for t in ts if t.entry_regime == "trending") / len(ts) * 100
            net_pnl = sum(t.pnl for t in ts)
            print(
                f"  {reason:<45} | {len(ts):>3} | {long_pct:>5.0f}% | {avg_rsi:>7.1f} "
                f"| {avg_adx:>7.1f} | {avg_conf:>8.2f} | {trending_pct:>9.0f}% | {net_pnl:>8.2f}"
            )


def _print_summary(title: str, rows: list[tuple[str, dict[str, float], dict[str, float]]]) -> None:
    print(f"\n{title}")
    print("coin | strat | trades | win_rate | net_pnl | gross_pnl | fees | avg_pnl | pf | max_dd | avg_conf")
    print("-" * 118)
    for coin, a, b in rows:
        print(
            f"{coin} | v1 | {int(a['trades'])} | {_fmt_pct(a['win_rate'])} | {a['net_pnl']:.2f} | {a['gross_pnl']:.2f} | {a['total_fees']:.2f} | {a['avg_pnl']:.2f} | {a['profit_factor']:.2f} | {a['max_drawdown']:.2f} | {a['avg_conf']:.2f}"
        )
        print(
            f"{coin} | v2 | {int(b['trades'])} | {_fmt_pct(b['win_rate'])} | {b['net_pnl']:.2f} | {b['gross_pnl']:.2f} | {b['total_fees']:.2f} | {b['avg_pnl']:.2f} | {b['profit_factor']:.2f} | {b['max_drawdown']:.2f} | {b['avg_conf']:.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay backtest: compare swing v1 vs v2")
    parser.add_argument("--coins", default="BTC,ETH,SOL,BNB,XRP,DOGE,AVAX,LINK,SUI", help="Comma-separated coin tickers")
    parser.add_argument("--start", default=None, help="UTC ISO datetime, e.g. 2025-01-01T00:00:00Z")
    parser.add_argument("--end", default=None, help="UTC ISO datetime, e.g. 2026-01-01T00:00:00Z")
    parser.add_argument("--fee-bps", type=float, default=0.0, help="Fee per side in basis points (e.g. 4 = 0.04%%)")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Adverse slippage per side in basis points")
    parser.add_argument("--exit-breakdown", action="store_true", help="Print exit-reason breakdown with win rate and PnL per reason")
    parser.add_argument("--entry-analysis", action="store_true", help="Print entry condition breakdown by exit reason (RSI, ADX, confidence, direction)")
    parser.add_argument("--no-mixed-ema-exit", action="store_true", help="Disable the '4h EMA mixed + MACD weakening' exit for both strategies")
    parser.add_argument("--workers", type=int, default=8, help="Parallel threads for coin processing (default: 8)")
    args = parser.parse_args()

    global _DISABLE_MIXED_EMA_EXIT
    _DISABLE_MIXED_EMA_EXIT = args.no_mixed_ema_exit

    end = _parse_iso_utc(args.end) if args.end else datetime.now(timezone.utc)
    start = _parse_iso_utc(args.start) if args.start else (end - timedelta(days=180))
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]

    engine = ReplayEngine(
        coins,
        start,
        end,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    agg_v1 = StrategyState("v1", fee_rate=engine.fee_rate, slippage_rate=engine.slippage_rate)
    agg_v2 = StrategyState("v2", fee_rate=engine.fee_rate, slippage_rate=engine.slippage_rate)

    mixed_note = " [--no-mixed-ema-exit]" if _DISABLE_MIXED_EMA_EXIT else ""
    print(f"Running replay from {start.isoformat()} to {end.isoformat()} for {', '.join(coins)}{mixed_note}")
    print(f"Cost model: fee={args.fee_bps:.2f} bps/side, slippage={args.slippage_bps:.2f} bps/side  workers={args.workers}")

    coin_results: dict[str, tuple[StrategyState, StrategyState, int]] = {}
    with ThreadPoolExecutor(max_workers=min(args.workers, len(coins))) as executor:
        futures = {executor.submit(engine._run_coin, coin): coin for coin in coins}
        for future in as_completed(futures):
            coin = futures[future]
            v1, v2, bars = future.result()
            print(f"Processed {coin}: {bars} bars, v1 trades={len(v1.trades)}, v2 trades={len(v2.trades)}")
            coin_results[coin] = (v1, v2, bars)

    rows: list[tuple[str, dict[str, float], dict[str, float]]] = []
    for coin in coins:  # restore original order for display
        v1, v2, _ = coin_results[coin]
        rows.append((coin, _summarize(v1), _summarize(v2)))
        agg_v1.trades.extend(v1.trades)
        agg_v2.trades.extend(v2.trades)
        agg_v1.entries_conf.extend(v1.entries_conf)
        agg_v2.entries_conf.extend(v2.entries_conf)
        # simple concatenation for global mdd approximation by coin-run order
        agg_v1.equity_curve.extend(v1.equity_curve[1:])
        agg_v2.equity_curve.extend(v2.equity_curve[1:])

    _print_summary("Per-coin results", rows)
    total_row = [("TOTAL", _summarize(agg_v1), _summarize(agg_v2))]
    _print_summary("Aggregate results", total_row)

    if args.exit_breakdown:
        _print_exit_breakdown("Exit reason breakdown (aggregate)", agg_v1.trades, agg_v2.trades)

    if args.entry_analysis:
        _print_entry_analysis("Entry condition analysis by exit reason", agg_v1.trades, agg_v2.trades)

    print("\nNotes:")
    print("- Uses public kline data only; funding/OI/L-S/taker are neutralized to baseline values.")
    print("- Fees/slippage are modeled per side using CLI parameters; latency still not modeled.")
    print("- Intrabar SL/TP tie-break is conservative (SL assumed first if both touch in same candle).")


if __name__ == "__main__":
    main()
