"""Swing agent main loop — scan coins, ask LLM, execute on Binance Futures."""

import logging
import time
from datetime import datetime, timezone
from binance.client import Client

from app import db
from app.swing import config, agent, notifier, snapshot
from app.swing.exchange import (
    get_open_positions, get_price,
    open_long, open_short, close_position, cancel_open_orders,
)

log = logging.getLogger(__name__)


def run():
    db.init_db()
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)

    notifier.send(
        f"📊 <b>Swing Agent LIVE</b>\n"
        f"Coins: {', '.join(config.COINS)}\n"
        f"Leverage: {config.LEVERAGE}x  |  Size: ${config.POSITION_USDT}\n"
        f"Min confidence: {config.MIN_CONFIDENCE * 100:.0f}%  |  "
        f"Max positions: {config.MAX_OPEN}"
    )

    while True:
        try:
            positions = get_open_positions(client)
            log.info("Open positions: %s", list(positions.keys()) or "none")

            for coin in config.COINS:
                try:
                    snap     = snapshot.build(client, coin)
                    decision = agent.decide(snap)
                    action   = decision["action"]
                    conf     = decision["confidence"]
                    price    = snap["price"]
                    pos      = positions.get(coin)

                    # ── Close existing position ────────────────────────
                    if action == "close" and pos:
                        cancel_open_orders(client, coin)
                        close_position(client, coin, positions)
                        pnl = pos["pnl"]
                        pnl_pct = pnl / pos["notional"] if pos["notional"] else 0.0
                        log.info("NOTIFY close %s pnl=%.4f", coin, pnl)
                        notifier.notify_close(coin, pos, pnl, decision["reasoning"])
                        db_trade = db.get_open_swing_trade(coin)
                        if db_trade:
                            db.log_swing_close(
                                trade_id=db_trade.id,
                                exit_price=get_price(client, coin),
                                realized_pnl_usd=pnl,
                                realized_pnl_pct=pnl_pct,
                                exit_reason=decision["reasoning"][:50],
                            )
                        continue

                    # ── Hold ──────────────────────────────────────────
                    if action == "hold":
                        log.info("HOLD %s (%.0f%%) — %s", coin, conf * 100, decision["reasoning"])
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
                        close_position(client, coin, positions)
                        pnl = pos["pnl"]
                        pnl_pct = pnl / pos["notional"] if pos["notional"] else 0.0
                        log.info("NOTIFY flip-close %s pnl=%.4f", coin, pnl)
                        notifier.notify_close(coin, pos, pnl, f"flipping to {action}")
                        db_trade = db.get_open_swing_trade(coin)
                        if db_trade:
                            db.log_swing_close(
                                trade_id=db_trade.id,
                                exit_price=get_price(client, coin),
                                realized_pnl_usd=pnl,
                                realized_pnl_pct=pnl_pct,
                                exit_reason=f"flip to {action}",
                            )
                        positions = get_open_positions(client)

                    # ── Open new position ─────────────────────────────
                    sl = decision.get("sl_pct", 0.0) or 0.0
                    tp = decision.get("tp_pct", 0.0) or 0.0
                    if action == "long":
                        open_long(client, coin, config.POSITION_USDT, config.LEVERAGE, sl, tp)
                    else:
                        open_short(client, coin, config.POSITION_USDT, config.LEVERAGE, sl, tp)

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
                        agent_reasoning=decision["reasoning"],
                    )
                    notifier.notify_open(coin, action, price, decision)


                except Exception as e:
                    log.error("Error processing %s: %s", coin, e)

        except Exception as e:
            log.error("Main loop error: %s", e)
            notifier.send(f"⚠️ <b>Swing agent error:</b> {e}\nRetrying next cycle...")

        log.info("Cycle done. Sleeping %ds...", config.CHECK_INTERVAL)
        time.sleep(config.CHECK_INTERVAL)
