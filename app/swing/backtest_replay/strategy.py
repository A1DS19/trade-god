"""V1 and V2 strategy decision logic: entry/exit rules and confidence scoring."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Strategy constants
# ---------------------------------------------------------------------------

LEVERAGE = 5
V1_MIN_CONFIDENCE = 0.70
V2_MIN_CONFIDENCE = 0.85
V2_PARTIAL_MIN_ADX = 32.0
V2_PARTIAL_MIN_CONFIDENCE = 0.80
V2_ENABLE_PARTIAL_ENTRIES = False
V2_REQUIRE_DI_ALIGNMENT = True
V2_MIN_TP_TO_COST_MULT = 3.0
V2_MIN_NET_TP_PCT = 0.004
V2_MACD_DIV_EXIT_RSI_SHORT = 32.0  # mirrors config.MACD_DIV_EXIT_RSI_SHORT
V2_MACD_DIV_EXIT_RSI_LONG = 68.0   # mirrors config.MACD_DIV_EXIT_RSI_LONG (raised from 62: fires on consolidation, 68 aligns with deep-overbought threshold)

# Set in main() before threads start; read-only during replay.
_DISABLE_MACD_DIV_EXIT: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ema_alignment(price: float, ema_fast: float, ema_mid: float, ema_slow: float) -> str:
    if price > ema_fast > ema_mid > ema_slow:
        return "bullish"
    if price < ema_fast < ema_mid < ema_slow:
        return "bearish"
    return "mixed"


def _map_confidence(score: float) -> float:
    if score >= 0.12:
        return round(0.85 + min(score - 0.12, 0.09), 2)
    if score >= 0.07:
        return round(0.75 + (score - 0.07) / 0.05 * 0.09, 2)
    if score >= 0.03:
        return round(0.70 + (score - 0.03) / 0.04 * 0.04, 2)
    return round(0.60 + max(score, -0.10) * 0.5, 2)


def _position_size_usdt_v2(confidence: float) -> float:
    lo = 5.0
    hi = 10.0
    floor = V2_MIN_CONFIDENCE
    cap = 0.95
    x = min(max(confidence, floor), cap)
    ratio = (x - floor) / (cap - floor)
    return round(lo + (hi - lo) * ratio, 2)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

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

    # Contradicting signals
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


# ---------------------------------------------------------------------------
# Exit checks
# ---------------------------------------------------------------------------

def _check_short_exit(
    ema4h: str,
    ema_d: str,
    rsi: float,
    macd: float,
    macd_p: float,
    oi_chg: float,
    adx: float,
    unrealized_pct: float | None = None,
) -> str | None:
    if ema4h == "bullish":
        return "4h EMA turned bullish"
    if ema_d == "bullish":
        return "daily EMA turned bullish"
    if rsi < 32:
        return "RSI deep oversold"
    if not _DISABLE_MACD_DIV_EXIT and macd > macd_p and rsi < V2_MACD_DIV_EXIT_RSI_SHORT:
        return "MACD divergence (short)"
    if oi_chg < -3 and macd > macd_p:
        return "OI falling (shorts covering)"
    if adx < 20:
        return "ADX trend collapsed"
    return None


def _check_long_exit(
    ema4h: str,
    ema_d: str,
    rsi: float,
    macd: float,
    macd_p: float,
    oi_chg: float,
    adx: float,
    unrealized_pct: float | None = None,
) -> str | None:
    if ema4h == "bearish":
        return "4h EMA turned bearish"
    if ema_d == "bearish":
        return "daily EMA turned bearish"
    if rsi > 68:
        return "RSI deep overbought"
    if not _DISABLE_MACD_DIV_EXIT and macd < macd_p and rsi > V2_MACD_DIV_EXIT_RSI_LONG:
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


# ---------------------------------------------------------------------------
# Decision functions
# ---------------------------------------------------------------------------

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
            unrealized_pct: float | None = (
                (price - entry) / entry if pos["side"] == "long" else (entry - price) / entry
            )
        else:
            unrealized_pct = None
        reason = (
            _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx, unrealized_pct)
            if pos["side"] == "short"
            else _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx, unrealized_pct)
        )
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
            and ema4h == "mixed"
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
        reason = (
            _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx)
            if pos["side"] == "short"
            else _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi, adx)
        )
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
