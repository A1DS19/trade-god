"""Rule-based trading decision engine — no LLM required."""

import logging
from app.swing import config

log = logging.getLogger(__name__)


def decide(snapshot: dict) -> dict:
    ind    = snapshot["indicators"]
    regime = snapshot["market_regime"]
    pos    = snapshot.get("open_position")

    ema4h    = ind["ema_alignment"]
    ema_d    = ind["daily_ema_alignment"]
    rsi      = ind["rsi14_4h"]
    adx      = ind["adx14"]
    macd     = ind["macd_hist"]
    macd_p   = ind["macd_hist_prev"]
    vol      = ind["vol_ratio"]
    funding  = snapshot["funding_rate_pct"]
    oi_chg   = ind["oi_change_4h_pct"]
    vs_ema200 = ind["price_vs_ema200"]
    plus_di  = ind["plus_di"]
    minus_di = ind["minus_di"]

    # ── STEP 1: Exit check for open position ──────────────────
    if pos:
        side = pos["side"]
        if side == "short":
            exit_reason = _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx)
        else:
            exit_reason = _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx)

        if exit_reason:
            log.info("EXIT %s — %s", snapshot["coin"], exit_reason)
            return _close(exit_reason)

        # Position still valid — score hold confidence
        conf, reasons = _score_hold(side, ema4h, ema_d, rsi, macd, macd_p,
                                    adx, vol, funding, oi_chg, vs_ema200,
                                    plus_di, minus_di)
        return _hold(conf, "; ".join(reasons))

    # ── STEP 2: Regime gate ────────────────────────────────────
    if regime == "ranging":
        return _hold(0.0, "ADX < 20 — ranging market, no entry")

    # ── STEP 3: Entry check ────────────────────────────────────
    direction, block_reason = _check_entry(regime, ema4h, ema_d, rsi, macd, adx)
    if direction is None:
        return _hold(0.0, block_reason)

    # ── STEP 4: Confidence scoring ─────────────────────────────
    conf, reasons = _score_entry(direction, rsi, vol, funding, oi_chg,
                                 vs_ema200, plus_di, minus_di, macd, macd_p, regime)
    if conf < config.MIN_CONFIDENCE:
        return _hold(conf, f"Confidence {conf:.2f} < {config.MIN_CONFIDENCE} — " + "; ".join(reasons))

    sl = snapshot["suggested_sl_pct"]
    tp = snapshot["suggested_tp_pct"]
    reasoning = f"{direction.upper()} entry | " + "; ".join(reasons)
    log.info("SIGNAL %s %s conf=%.2f sl=%.3f tp=%.3f",
             snapshot["coin"], direction, conf, sl, tp)
    return {"action": direction, "confidence": conf,
            "sl_pct": sl, "tp_pct": tp, "reasoning": reasoning}


# ── Exit conditions ────────────────────────────────────────────

def _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx) -> str | None:
    if ema4h in ("bullish", "mixed"):
        return f"4h EMA turned {ema4h}"
    if ema_d == "bullish":
        return "daily EMA turned bullish"
    if rsi < 38:
        return f"RSI {rsi:.1f} < 38 (oversold approach)"
    if macd > macd_p and rsi < 45:
        return f"MACD divergence (hist {macd:.4f} > prev {macd_p:.4f}) with RSI {rsi:.1f}"
    if oi_chg < -3 and macd > macd_p:
        return f"OI falling {oi_chg:.1f}% (shorts covering)"
    if adx < 20:
        return f"ADX {adx:.1f} < 20 — trend collapsed"
    return None


def _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx) -> str | None:
    if ema4h in ("bearish", "mixed"):
        return f"4h EMA turned {ema4h}"
    if ema_d == "bearish":
        return "daily EMA turned bearish"
    if rsi > 62:
        return f"RSI {rsi:.1f} > 62 (overbought approach)"
    if macd < macd_p and rsi > 55:
        return f"MACD divergence (hist {macd:.4f} < prev {macd_p:.4f}) with RSI {rsi:.1f}"
    if oi_chg < -3 and macd < macd_p:
        return f"OI falling {oi_chg:.1f}% (longs covering)"
    if adx < 20:
        return f"ADX {adx:.1f} < 20 — trend collapsed"
    return None


# ── Entry conditions ───────────────────────────────────────────

def _check_entry(regime, ema4h, ema_d, rsi, macd, adx) -> tuple[str | None, str]:
    """Returns (direction, reason). direction is None if no entry."""
    blocks = []
    for direction in ("short", "long"):
        req_ema = "bearish" if direction == "short" else "bullish"
        fails = []
        if ema_d != req_ema:
            fails.append(f"daily={ema_d}")
        if ema4h != req_ema:
            fails.append(f"4h={ema4h}")
        if direction == "short" and macd >= 0:
            fails.append(f"MACD hist={macd:.4f}>=0")
        if direction == "long" and macd <= 0:
            fails.append(f"MACD hist={macd:.4f}<=0")
        if adx <= 25:
            fails.append(f"ADX={adx:.1f}<=25")
        if direction == "short" and rsi <= config.MIN_RSI_SHORT:
            fails.append(f"RSI={rsi:.1f}<={config.MIN_RSI_SHORT}")
        if direction == "long" and rsi >= config.MAX_RSI_LONG:
            fails.append(f"RSI={rsi:.1f}>={config.MAX_RSI_LONG}")
        if not fails:
            return direction, ""
        blocks.append(f"{direction}: {', '.join(fails)}")

    return None, "No entry — " + " | ".join(blocks)


# ── Confidence scoring ─────────────────────────────────────────

def _score_entry(direction, rsi, vol, funding, oi_chg, vs_ema200,
                 plus_di, minus_di, macd, macd_p, regime) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    if vol > 1.5:
        score += 0.05; reasons.append(f"vol {vol:.2f}↑")
    if direction == "short" and funding > 0.05:
        score += 0.04; reasons.append(f"funding +{funding:.4f}% (crowded longs)")
    elif direction == "long" and funding < -0.05:
        score += 0.04; reasons.append(f"funding {funding:.4f}% (crowded shorts)")
    if direction == "short" and oi_chg > 1 and macd < macd_p * 0.95:
        score += 0.04; reasons.append(f"OI +{oi_chg:.1f}% (new shorts)")
    elif direction == "long" and oi_chg > 1 and macd > macd_p * 1.05:
        score += 0.04; reasons.append(f"OI +{oi_chg:.1f}% (new longs)")
    if 40 <= rsi <= 60:
        score += 0.03; reasons.append(f"RSI {rsi:.1f} healthy")
    if direction == "short" and vs_ema200 < 0:
        score += 0.03; reasons.append(f"price {vs_ema200:.1f}% below EMA200")
    elif direction == "long" and vs_ema200 > 0:
        score += 0.03; reasons.append(f"price +{vs_ema200:.1f}% above EMA200")
    if direction == "short" and minus_di > plus_di:
        score += 0.04; reasons.append(f"-DI {minus_di:.1f} > +DI {plus_di:.1f}")
    elif direction == "long" and plus_di > minus_di:
        score += 0.04; reasons.append(f"+DI {plus_di:.1f} > -DI {minus_di:.1f}")

    # Contradicting
    if direction == "short" and rsi < 45:
        score -= 0.05; reasons.append(f"RSI {rsi:.1f} near oversold")
    elif direction == "long" and rsi > 55:
        score -= 0.05; reasons.append(f"RSI {rsi:.1f} near overbought")
    if direction == "short" and funding < -0.05:
        score -= 0.04; reasons.append(f"funding {funding:.4f}% opposes short")
    elif direction == "long" and funding > 0.05:
        score -= 0.04; reasons.append(f"funding +{funding:.4f}% opposes long")
    if oi_chg < -2:
        score -= 0.04; reasons.append(f"OI {oi_chg:.1f}% (positions closing)")
    if direction == "short" and macd > macd_p:
        score -= 0.04; reasons.append("MACD hist improving (contra short)")
    elif direction == "long" and macd < macd_p:
        score -= 0.04; reasons.append("MACD hist deteriorating (contra long)")

    # Borderline regime requires extra conviction
    if regime == "borderline":
        score -= 0.08; reasons.append("ADX borderline penalty")

    # Map score to confidence band
    if score >= 0.12:
        conf = round(0.85 + min(score - 0.12, 0.09), 2)
    elif score >= 0.07:
        conf = round(0.75 + (score - 0.07) / 0.05 * 0.09, 2)
    elif score >= 0.03:
        conf = round(0.70 + (score - 0.03) / 0.04 * 0.04, 2)
    else:
        conf = round(0.60 + max(score, -0.10) * 0.5, 2)

    return conf, reasons


def _score_hold(side, ema4h, ema_d, rsi, macd, macd_p, adx,
                vol, funding, oi_chg, vs_ema200, plus_di, minus_di) -> tuple[float, list[str]]:
    score = 0.07  # base: both EMA alignments confirmed (or we'd have exited)
    reasons = [f"{side} | EMA {ema4h}/{ema_d} aligned | ADX {adx:.1f}"]

    if side == "short":
        if minus_di > plus_di:
            score += 0.04; reasons.append(f"-DI {minus_di:.1f} > +DI {plus_di:.1f}")
        if vs_ema200 < 0:
            score += 0.03; reasons.append(f"price {vs_ema200:.1f}% below EMA200")
        if macd > macd_p:
            score -= 0.04; reasons.append("MACD hist rising (momentum weakening)")
        if rsi < 42:
            score -= 0.04; reasons.append(f"RSI {rsi:.1f} near exit zone")
    else:
        if plus_di > minus_di:
            score += 0.04; reasons.append(f"+DI {plus_di:.1f} > -DI {minus_di:.1f}")
        if vs_ema200 > 0:
            score += 0.03; reasons.append(f"price +{vs_ema200:.1f}% above EMA200")
        if macd < macd_p:
            score -= 0.04; reasons.append("MACD hist falling (momentum weakening)")
        if rsi > 58:
            score -= 0.04; reasons.append(f"RSI {rsi:.1f} near exit zone")

    conf = round(min(max(0.60 + score, 0.60), 0.94), 2)
    return conf, reasons


# ── Helpers ────────────────────────────────────────────────────

def _close(reason: str) -> dict:
    return {"action": "close", "confidence": 0.0,
            "sl_pct": 0.0, "tp_pct": 0.0, "reasoning": reason}


def _hold(conf: float, reason: str) -> dict:
    log.info("HOLD conf=%.2f — %s", conf, reason)
    return {"action": "hold", "confidence": conf,
            "sl_pct": 0.0, "tp_pct": 0.0, "reasoning": reason}
