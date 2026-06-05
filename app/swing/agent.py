"""Rule-based trading decision engine — no LLM required."""

import logging
from app.swing import config

log = logging.getLogger(__name__)


def decide(snapshot: dict) -> dict:
    ind    = snapshot["indicators"]
    regime = snapshot["market_regime"]
    pos    = snapshot.get("open_position")

    ema4h     = ind["ema_alignment"]
    ema_d     = ind["daily_ema_alignment"]
    rsi       = ind["rsi14_4h"]
    adx       = ind["adx14"]
    macd      = ind["macd_hist"]
    macd_p    = ind["macd_hist_prev"]
    vol       = ind["vol_ratio"]
    funding   = snapshot["funding_rate_pct"]
    oi_chg    = ind["oi_change_4h_pct"]
    vs_ema200 = ind["price_vs_ema200"]
    plus_di   = ind["plus_di"]
    minus_di  = ind["minus_di"]
    stoch_k     = ind["stoch_rsi_k"]
    atr_rank    = ind["atr_pct_rank"]
    vs_vwap     = ind["price_vs_vwap"]
    ls_ratio    = ind["ls_ratio"]
    taker_ratio = ind["taker_ratio"]

    # ── STEP 1: Exit check for open position ──────────────────
    if pos:
        side = pos["side"]
        entry = float(pos.get("entry", 0))
        price = snapshot["price"]
        if entry > 0:
            unrealized_pct = (price - entry) / entry if side == "long" else (entry - price) / entry
        else:
            unrealized_pct = None
        if side == "short":
            exit_reason = _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx, unrealized_pct)
        else:
            exit_reason = _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx, unrealized_pct)

        if exit_reason:
            log.info("EXIT %s — %s", snapshot["coin"], exit_reason)
            return _close(exit_reason)

        # Position still valid — score hold confidence
        conf, reasons = _score_hold(side, ema4h, ema_d, rsi, macd, macd_p,
                                    adx, vol, funding, oi_chg, vs_ema200,
                                    plus_di, minus_di, stoch_k, vs_vwap)
        return _hold(conf, "; ".join(reasons))

    # ── STEP 2: Regime gate ────────────────────────────────────
    if regime == "ranging":
        return _hold(0.0, "ADX < 20 — ranging market, no entry")

    # ── STEP 3: Entry check ────────────────────────────────────
    direction, entry_mode, block_reason = _check_entry(
        ema4h, ema_d, macd, adx,
        snapshot["price"], ind["ema9"], ind["ema21"], ind["ema50"],
        plus_di, minus_di,
    )
    if direction is None:
        return _hold(0.0, block_reason)

    # ── STEP 3b: Hard RSI gate — don't enter into the exit/bounce zone ──
    gated = (
        (direction == "short" and rsi < config.SHORT_ENTRY_RSI_FLOOR)
        or (direction == "long" and rsi > config.LONG_ENTRY_RSI_CEIL)
    )
    if gated:
        # Score it anyway (cheap) so the shadow tracker knows whether the gate
        # actually prevented a TRADE (conf >= MIN) vs a setup that would have held.
        would_be_conf, _ = _score_entry(direction, rsi, vol, funding, oi_chg,
                                        vs_ema200, plus_di, minus_di, macd, macd_p, regime,
                                        stoch_k, atr_rank, vs_vwap, ls_ratio, taker_ratio,
                                        entry_mode)
        if direction == "short":
            reason = f"short blocked — RSI {rsi:.1f} < {config.SHORT_ENTRY_RSI_FLOOR:.0f} (deep oversold, exit zone)"
        else:
            reason = f"long blocked — RSI {rsi:.1f} > {config.LONG_ENTRY_RSI_CEIL:.0f} (deep overbought, exit zone)"
        decision = _hold(0.0, reason)
        decision["gate_block"] = {"direction": direction, "rsi": rsi, "would_be_conf": would_be_conf}
        return decision

    # ── STEP 4: Confidence scoring ─────────────────────────────
    conf, reasons = _score_entry(direction, rsi, vol, funding, oi_chg,
                                 vs_ema200, plus_di, minus_di, macd, macd_p, regime,
                                 stoch_k, atr_rank, vs_vwap, ls_ratio, taker_ratio,
                                 entry_mode)
    if conf < config.MIN_CONFIDENCE:
        return _hold(conf, f"Confidence {conf:.2f} < {config.MIN_CONFIDENCE} — " + "; ".join(reasons))
    if entry_mode == "partial" and conf < config.PARTIAL_MIN_CONFIDENCE:
        return _hold(
            conf,
            f"Partial entry confidence {conf:.2f} < {config.PARTIAL_MIN_CONFIDENCE:.2f} — " + "; ".join(reasons),
        )

    sl = snapshot["suggested_sl_pct"]
    tp = snapshot["suggested_tp_pct"]
    reasoning = f"{direction.upper()} entry | " + "; ".join(reasons)
    log.info("SIGNAL %s %s conf=%.2f sl=%.2f%% tp=%.2f%%",
             snapshot["coin"], direction, conf, sl * 100, tp * 100)
    return {"action": direction, "confidence": conf,
            "sl_pct": sl, "tp_pct": tp, "reasoning": reasoning, "entry_mode": entry_mode}


# ── Exit conditions ────────────────────────────────────────────

def _check_short_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx, unrealized_pct=None) -> str | None:
    if ema4h == "bullish":
        return "4h EMA turned bullish"
    if ema_d == "bullish":
        return "daily EMA turned bullish"
    if rsi < config.SHORT_EXIT_RSI_FLOOR:
        return f"RSI {rsi:.1f} < {config.SHORT_EXIT_RSI_FLOOR:.0f} (deep oversold)"
    if macd > macd_p and rsi < config.MACD_DIV_EXIT_RSI_SHORT:
        return f"MACD divergence (hist {macd:.4f} > prev {macd_p:.4f}) with RSI {rsi:.1f}"
    if oi_chg < -3 and macd > macd_p:
        return f"OI falling {oi_chg:.1f}% (shorts covering)"
    if adx < 20:
        return f"ADX {adx:.1f} < 20 — trend collapsed"
    return None


def _check_long_exit(ema4h, ema_d, rsi, macd, macd_p, oi_chg, adx, unrealized_pct=None) -> str | None:
    if ema4h == "bearish":
        return "4h EMA turned bearish"
    if ema_d == "bearish":
        return "daily EMA turned bearish"
    if rsi > config.LONG_EXIT_RSI_CEIL:
        return f"RSI {rsi:.1f} > {config.LONG_EXIT_RSI_CEIL:.0f} (deep overbought)"
    if macd < macd_p and rsi > config.MACD_DIV_EXIT_RSI_LONG:
        return f"MACD divergence (hist {macd:.4f} < prev {macd_p:.4f}) with RSI {rsi:.1f}"
    if oi_chg < -3 and macd < macd_p:
        return f"OI falling {oi_chg:.1f}% (longs covering)"
    if adx < 20:
        return f"ADX {adx:.1f} < 20 — trend collapsed"
    return None


# ── Entry conditions ───────────────────────────────────────────

def _is_partial_4h_alignment(direction: str, price: float, ema9: float, ema21: float, ema50: float) -> bool:
    if direction == "short":
        return price < ema9 < ema21 and ema21 >= ema50
    return price > ema9 > ema21 and ema21 <= ema50


def _check_entry(ema4h, ema_d, macd, adx, price, ema9, ema21, ema50, plus_di, minus_di) -> tuple[str | None, str, str]:
    """Returns (direction, entry_mode, reason). direction is None if no entry."""
    blocks = []
    for direction in ("short", "long"):
        req_ema = "bearish" if direction == "short" else "bullish"
        fails = []

        if ema_d != req_ema:
            fails.append(f"daily={ema_d}")
        if direction == "short" and macd >= 0:
            fails.append(f"MACD hist={macd:.4f}>=0")
        if direction == "long" and macd <= 0:
            fails.append(f"MACD hist={macd:.4f}<=0")
        if adx < config.MIN_ADX_ENTRY:
            fails.append(f"ADX={adx:.1f}<{config.MIN_ADX_ENTRY:.0f}")
        if config.REQUIRE_DI_ALIGNMENT:
            if direction == "short" and minus_di <= plus_di:
                fails.append(f"-DI={minus_di:.1f}<=+DI={plus_di:.1f}")
            if direction == "long" and plus_di <= minus_di:
                fails.append(f"+DI={plus_di:.1f}<=-DI={minus_di:.1f}")

        if not fails:
            if ema4h == req_ema:
                return direction, "strict", ""
            if (
                config.ENABLE_PARTIAL_ENTRIES
                and
                ema4h == "mixed"
                and adx >= config.PARTIAL_MIN_ADX
                and _is_partial_4h_alignment(direction, price, ema9, ema21, ema50)
            ):
                return direction, "partial", ""
            fails.append(f"4h={ema4h} (no strict/partial alignment)")

        blocks.append(f"{direction}: {', '.join(fails)}")

    return None, "", "No entry — " + " | ".join(blocks)


# ── Confidence scoring ─────────────────────────────────────────

def _score_entry(direction, rsi, vol, funding, oi_chg, vs_ema200,
                 plus_di, minus_di, macd, macd_p, regime,
                 stoch_k, atr_rank, vs_vwap, ls_ratio, taker_ratio,
                 entry_mode: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    def add(delta: float, text: str) -> None:
        nonlocal score
        score += delta
        sign = "+" if delta >= 0 else "-"
        reasons.append(f"{sign}{abs(delta):.2f} {text}")

    if entry_mode == "partial":
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

    # Stochastic RSI momentum confirmation
    if direction == "short" and stoch_k > 80:
        add(0.04, f"StochRSI {stoch_k:.0f} overbought")
    elif direction == "long" and stoch_k < 20:
        add(0.04, f"StochRSI {stoch_k:.0f} oversold")

    # Long/short ratio — contrarian sentiment
    if direction == "short" and ls_ratio >= 2.0:
        add(0.04, f"L/S ratio {ls_ratio:.2f} (crowded longs)")
    elif direction == "long" and ls_ratio <= 0.5:
        add(0.04, f"L/S ratio {ls_ratio:.2f} (crowded shorts)")

    # Taker buy/sell ratio — aggressive order flow
    if direction == "short" and taker_ratio < 0.8:
        add(0.03, f"taker ratio {taker_ratio:.2f} (sellers aggressive)")
    elif direction == "long" and taker_ratio > 1.2:
        add(0.03, f"taker ratio {taker_ratio:.2f} (buyers aggressive)")

    # ATR percentile — volatility regime
    if atr_rank > 70:
        add(0.03, f"ATR rank {atr_rank:.0f}% (vol expanding)")

    # VWAP bias
    if direction == "short" and vs_vwap < 0:
        add(0.03, f"price {vs_vwap:.1f}% below VWAP")
    elif direction == "long" and vs_vwap > 0:
        add(0.03, f"price +{vs_vwap:.1f}% above VWAP")

    # Contradicting
    if direction == "short" and rsi < config.MIN_RSI_SHORT:
        add(-0.05, f"RSI {rsi:.1f} below short comfort {config.MIN_RSI_SHORT:.0f}")
    elif direction == "long" and rsi > config.MAX_RSI_LONG:
        add(-0.05, f"RSI {rsi:.1f} above long comfort {config.MAX_RSI_LONG:.0f}")
    if direction == "short" and rsi < 36:
        add(-0.04, f"RSI {rsi:.1f} deeply oversold")
    elif direction == "long" and rsi > 64:
        add(-0.04, f"RSI {rsi:.1f} deeply overbought")
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

    # Borderline regime requires extra conviction
    if regime == "borderline":
        add(-config.BORDERLINE_ADX_PENALTY, "ADX borderline penalty")

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
                vol, funding, oi_chg, vs_ema200, plus_di, minus_di,
                stoch_k, vs_vwap) -> tuple[float, list[str]]:
    score = 0.07  # base: both EMA alignments confirmed (or we'd have exited)
    reasons = [f"{side} | EMA {ema4h}/{ema_d} aligned | ADX {adx:.1f}"]

    if side == "short":
        if minus_di > plus_di:
            score += 0.04; reasons.append(f"-DI {minus_di:.1f} > +DI {plus_di:.1f}")
        if vs_ema200 < 0:
            score += 0.03; reasons.append(f"price {vs_ema200:.1f}% below EMA200")
        if vs_vwap < 0:
            score += 0.02; reasons.append(f"price {vs_vwap:.1f}% below VWAP")
        if macd > macd_p:
            score -= 0.04; reasons.append("MACD hist rising (momentum weakening)")
        if rsi < 42:
            score -= 0.04; reasons.append(f"RSI {rsi:.1f} near exit zone")
        if stoch_k < 25:
            score -= 0.03; reasons.append(f"StochRSI {stoch_k:.0f} near oversold")
    else:
        if plus_di > minus_di:
            score += 0.04; reasons.append(f"+DI {plus_di:.1f} > -DI {minus_di:.1f}")
        if vs_ema200 > 0:
            score += 0.03; reasons.append(f"price +{vs_ema200:.1f}% above EMA200")
        if vs_vwap > 0:
            score += 0.02; reasons.append(f"price +{vs_vwap:.1f}% above VWAP")
        if macd < macd_p:
            score -= 0.04; reasons.append("MACD hist falling (momentum weakening)")
        if rsi > 58:
            score -= 0.04; reasons.append(f"RSI {rsi:.1f} near exit zone")
        if stoch_k > 75:
            score -= 0.03; reasons.append(f"StochRSI {stoch_k:.0f} near overbought")

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
