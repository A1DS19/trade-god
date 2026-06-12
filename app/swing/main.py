"""Swing agent main loop — scan coins, ask LLM, execute on Binance Futures."""

import logging
import time
from datetime import datetime, timezone
from binance.client import Client

from app import db
from app.swing import config, agent, notifier, reconcile, shadow, snapshot
from app.swing.exchange import (
    get_open_positions, get_price,
    open_long, open_short, close_position, cancel_open_orders,
)

log = logging.getLogger(__name__)


def _is_hard_exit(reason: str) -> bool:
    return (
        reason.startswith("4h EMA turned bullish")
        or reason.startswith("4h EMA turned bearish")
        or reason.startswith("daily EMA turned bullish")
        or reason.startswith("daily EMA turned bearish")
        or reason.startswith("ADX ")
        or reason.startswith("client-side ")
    )


def _extract_exit_price(close_order: dict | None, fallback_price: float) -> float:
    if close_order and close_order.get("avgPrice") is not None:
        try:
            avg_price = float(close_order["avgPrice"])
            if avg_price > 0:
                return avg_price
        except (TypeError, ValueError):
            pass
    return fallback_price


def _calc_realized_pnl(pos: dict, exit_price: float) -> tuple[float, float]:
    qty = float(pos["qty"])
    entry = float(pos["entry"])
    if pos["side"] == "long":
        pnl = (exit_price - entry) * qty
    else:
        pnl = (entry - exit_price) * qty
    pnl_pct = pnl / pos["notional"] if pos["notional"] else 0.0
    return pnl, pnl_pct


def _position_size_usdt(confidence: float) -> float:
    lo = config.POSITION_USDT_MIN
    hi = config.POSITION_USDT_MAX
    if hi <= lo:
        return lo
    floor = config.MIN_CONFIDENCE
    cap = max(config.CONFIDENCE_SIZING_CAP, floor + 0.01)
    x = min(max(confidence, floor), cap)
    ratio = (x - floor) / (cap - floor)
    return round(lo + (hi - lo) * ratio, 2)


def _expected_move_ok(tp_pct: float) -> tuple[bool, str]:
    roundtrip_cost_pct = 2.0 * (config.EST_FEE_BPS + config.EST_SLIPPAGE_BPS) / 10_000.0
    required_tp_pct = roundtrip_cost_pct * config.MIN_TP_TO_COST_MULT
    net_tp_pct = tp_pct - roundtrip_cost_pct
    if tp_pct < required_tp_pct:
        return False, f"tp {tp_pct*100:.2f}% < {config.MIN_TP_TO_COST_MULT:.1f}x est costs ({required_tp_pct*100:.2f}%)"
    if net_tp_pct < config.MIN_NET_TP_PCT:
        return False, f"net tp {net_tp_pct*100:.2f}% < min {config.MIN_NET_TP_PCT*100:.2f}%"
    return True, ""


def _safety_net_label(side: str, entry: float, price: float,
                      sl_pct: float, tp_pct: float) -> str | None:
    """Client-side stop check: 'SL', 'TP', or None for a position at ``price``.

    Hourly backstop mirroring the exchange-side stops, which can fail to place
    (see the -4120 history). SL takes priority if both somehow trigger.
    """
    chg = (price - entry) / entry
    hit_sl = (side == "long" and chg <= -sl_pct) or (side == "short" and chg >= sl_pct)
    hit_tp = (side == "long" and chg >= tp_pct) or (side == "short" and chg <= -tp_pct)
    if hit_sl:
        return "SL"
    if hit_tp:
        return "TP"
    return None


def _net_thresholds(db_trade) -> tuple[float, float]:
    """Per-trade SL/TP for the client-side net, falling back to the defaults.

    The net exists to back up the exchange-side ATR-sized stops, so it must use
    the same percentages — a flat default tighter than the ATR stop would
    preempt the exchange order and become the de-facto (wrong) stop.
    """
    sl = getattr(db_trade, "entry_sl_pct", None) or config.DEFAULT_SL_PCT
    tp = getattr(db_trade, "entry_tp_pct", None) or config.DEFAULT_TP_PCT
    return sl, tp


def run():
    db.init_db()
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)

    notifier.send(
        f"📊 <b>Swing Agent LIVE</b>\n"
        f"Coins: {', '.join(config.COINS)}\n"
        f"Leverage: {config.LEVERAGE}x  |  Size: ${config.POSITION_USDT_MIN}-${config.POSITION_USDT_MAX}\n"
        f"Min confidence: {config.MIN_CONFIDENCE * 100:.0f}%  |  "
        f"Max positions: {config.MAX_OPEN}"
    )

    tracker = shadow.ShadowTracker(config.SHADOW_MAX_CYCLES)

    while True:
        try:
            positions = get_open_positions(client)
            log.info("Open positions: %s", list(positions.keys()) or "none")

            for rec in reconcile.reconcile(client, positions):
                log.info("RECONCILED %s — %s pnl=%.4f", rec["coin"], rec["reason"], rec["pnl"])

            # ── Client-side SL/TP safety net ──────────────────────────
            for coin, pos in list(positions.items()):
                if coin not in config.COINS:
                    continue
                price_now = get_price(client, coin)
                chg = (price_now - pos["entry"]) / pos["entry"]
                db_trade = db.get_open_swing_trade(coin)
                sl_pct, tp_pct = _net_thresholds(db_trade)
                label = _safety_net_label(
                    pos["side"], pos["entry"], price_now,
                    sl_pct, tp_pct,
                )
                if label:
                    exit_reason = f"client-side {label} ({chg*100:+.1f}%)"
                    log.info("CLIENT %s %s chg=%.2f%%", label, coin, chg * 100)
                    cancel_open_orders(client, coin)
                    close_order = close_position(client, coin, positions)
                    exit_price = _extract_exit_price(close_order, price_now)
                    pnl, pnl_pct = _calc_realized_pnl(pos, exit_price)
                    log.info("NOTIFY client-%s %s pnl=%.4f", label, coin, pnl)
                    notifier.notify_close(coin, pos, pnl, exit_reason)
                    if db_trade:
                        db.log_swing_close(
                            trade_id=db_trade.id,
                            exit_price=exit_price,
                            realized_pnl_usd=pnl,
                            realized_pnl_pct=pnl_pct,
                            exit_reason=exit_reason,
                        )
                    positions = get_open_positions(client)

            for coin in config.COINS:
                try:
                    snap     = snapshot.build(client, coin)
                    decision = agent.decide(snap)
                    action   = decision["action"]
                    conf     = decision["confidence"]
                    price    = snap["price"]
                    pos      = positions.get(coin)

                    for _shadow_line in tracker.observe(coin, price, decision.get("gate_block"), config.MIN_CONFIDENCE):
                        log.info(_shadow_line)

                    # ── Close existing position ────────────────────────
                    if action == "close" and pos:
                        reason = decision["reasoning"]
                        unrealized_pnl, unrealized_pnl_pct = _calc_realized_pnl(pos, price)
                        log.info(
                            "CLOSE-CHECK %s reason=%s unrealized=%.2f%%",
                            coin, reason, unrealized_pnl_pct * 100,
                        )
                        if (
                            not _is_hard_exit(reason)
                            and unrealized_pnl_pct < 0
                            and abs(unrealized_pnl_pct) < config.SOFT_EXIT_MAX_LOSS_PCT
                        ):
                            log.info(
                                "HOLD %s — soft exit delayed at %.2f%% loss (%s)",
                                coin, unrealized_pnl_pct * 100, reason,
                            )
                            continue

                        cancel_open_orders(client, coin)
                        close_order = close_position(client, coin, positions)
                        market_price = get_price(client, coin)
                        exit_price = _extract_exit_price(close_order, market_price)
                        pnl, pnl_pct = _calc_realized_pnl(pos, exit_price)
                        log.info("NOTIFY close %s pnl=%.4f", coin, pnl)
                        notifier.notify_close(coin, pos, pnl, reason)
                        db_trade = db.get_open_swing_trade(coin)
                        if db_trade:
                            db.log_swing_close(
                                trade_id=db_trade.id,
                                exit_price=exit_price,
                                realized_pnl_usd=pnl,
                                realized_pnl_pct=pnl_pct,
                                exit_reason=reason[:50],
                            )
                        continue

                    # ── Hold ──────────────────────────────────────────
                    if action == "hold":
                        label = f"{conf * 100:.0f}%" if conf > 0 else "blocked"
                        log.info("HOLD %s (%s) — %s", coin, label, decision["reasoning"])
                        continue

                    # ── Loss cooldown ─────────────────────────────────
                    last = db.get_last_closed_swing_trade(coin)
                    if last and last.realized_pnl_usd is not None and last.realized_pnl_usd < 0 and last.exit_time:
                        exit_dt = datetime.fromisoformat(last.exit_time)
                        if exit_dt.tzinfo is None:
                            exit_dt = exit_dt.replace(tzinfo=timezone.utc)
                        hours_since = (datetime.now(timezone.utc) - exit_dt).total_seconds() / 3600
                        if hours_since < config.LOSS_COOLDOWN_HRS:
                            log.info(
                                "SKIP %s — loss cooldown (%.1fh remaining)",
                                coin, config.LOSS_COOLDOWN_HRS - hours_since,
                            )
                            continue

                    # ── Confidence gate ───────────────────────────────
                    if conf < config.MIN_CONFIDENCE:
                        log.info("SKIP %s — confidence %.0f%% < %.0f%%",
                                 coin, conf * 100, config.MIN_CONFIDENCE * 100)
                        continue

                    # ── Position cap ──────────────────────────────────
                    if len(positions) >= config.MAX_OPEN and coin not in positions:
                        log.info("SKIP %s — max open positions (%d) reached", coin, config.MAX_OPEN)
                        continue

                    # ── Already in same direction ─────────────────────
                    if pos and pos["side"] == action:
                        log.info("SKIP %s — already %s", coin, action)
                        continue

                    # ── Flip: close existing before opening opposite ───
                    if pos and pos["side"] != action:
                        log.info("FLIP %s — closing %s before opening %s", coin, pos["side"], action)
                        cancel_open_orders(client, coin)
                        close_order = close_position(client, coin, positions)
                        market_price = get_price(client, coin)
                        exit_price = _extract_exit_price(close_order, market_price)
                        pnl, pnl_pct = _calc_realized_pnl(pos, exit_price)
                        log.info("NOTIFY flip-close %s pnl=%.4f", coin, pnl)
                        notifier.notify_close(coin, pos, pnl, f"flipping to {action}")
                        db_trade = db.get_open_swing_trade(coin)
                        if db_trade:
                            db.log_swing_close(
                                trade_id=db_trade.id,
                                exit_price=exit_price,
                                realized_pnl_usd=pnl,
                                realized_pnl_pct=pnl_pct,
                                exit_reason=f"flip to {action}",
                            )
                        positions = get_open_positions(client)

                    # ── Open new position ─────────────────────────────
                    sl = decision.get("sl_pct", 0.0) or 0.0
                    tp = decision.get("tp_pct", 0.0) or 0.0
                    entry_mode = decision.get("entry_mode", "strict")
                    move_ok, move_reason = _expected_move_ok(tp)
                    if not move_ok:
                        log.info("SKIP %s — expected move filter (%s)", coin, move_reason)
                        continue
                    position_usdt = _position_size_usdt(conf)
                    log.info("SIZE %s — mode=%s conf %.2f -> $%.2f", coin, entry_mode, conf, position_usdt)
                    if action == "long":
                        open_long(client, coin, position_usdt, config.LEVERAGE, sl, tp)
                    else:
                        open_short(client, coin, position_usdt, config.LEVERAGE, sl, tp)

                    positions  = get_open_positions(client)
                    opened_pos = positions.get(coin, {})
                    filled_qty = opened_pos.get("qty", 0.0)
                    notional   = opened_pos.get("notional", 0.0)

                    db.log_swing_open(
                        coin=coin,
                        direction=action,
                        entry_price=price,
                        qty=filled_qty,
                        leverage=config.LEVERAGE,
                        notional_usdt=notional,
                        agent_confidence=conf,
                        agent_reasoning=decision["reasoning"][:499],
                        entry_sl_pct=decision.get("sl_pct", 0.0) or 0.0,
                        entry_tp_pct=decision.get("tp_pct", 0.0) or 0.0,
                    )
                    notifier.notify_open(coin, action, price, decision)


                except Exception as e:
                    log.error("Error processing %s: %s", coin, e)

        except Exception as e:
            log.error("Main loop error: %s", e)
            notifier.send(f"⚠️ <b>Swing agent error:</b> {e}\nRetrying next cycle...")

        log.info("Cycle done. Sleeping %ds...", config.CHECK_INTERVAL)
        time.sleep(config.CHECK_INTERVAL)
