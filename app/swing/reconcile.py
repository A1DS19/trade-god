"""Reconcile DB open swing trades against live exchange positions.

When an exchange-side algo SL/TP fires between cycles, the bot never performs
the close itself: the next cycle just sees the position gone. Without this
module the swing_trades row stays 'open' forever, no Telegram alert is sent,
and the loss cooldown — which only looks at status='closed' rows — is silently
bypassed (live incident: DOGE id=71, 2026-06-11).

Called once per cycle, right after positions are fetched.
"""

import logging
from datetime import datetime, timezone

from app import db
from app.swing import notifier
from app.swing.exchange import get_price, get_recent_fills

log = logging.getLogger(__name__)


def _entry_ms(entry_time: str) -> int:
    dt = datetime.fromisoformat(entry_time)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _close_from_fills(row, fills: list[dict]) -> tuple[float, float, str] | None:
    """(exit_price, pnl_usd, reason) from closing-side fills, or None if absent."""
    closing_side = "SELL" if row.direction == "long" else "BUY"
    closing = [f for f in fills if f["side"] == closing_side]
    if not closing:
        return None
    qty_total = sum(float(f["qty"]) for f in closing)
    if qty_total <= 0:
        return None
    exit_price = sum(float(f["price"]) * float(f["qty"]) for f in closing) / qty_total
    pnl = sum(float(f["realizedPnl"]) for f in closing)
    label = "SL" if pnl < 0 else "TP"
    return exit_price, pnl, f"exchange-side {label} fill (reconciled)"


def reconcile(client, positions: dict) -> list[dict]:
    """Close DB rows whose position no longer exists on the exchange.

    Returns one dict per reconciled trade (coin, pnl, reason) for cycle logging.
    Per-row failures are logged and skipped so one bad row can't block the rest.
    """
    results: list[dict] = []
    for row in db.get_all_open_swing_trades():
        if row.coin in positions:
            continue
        try:
            fills = get_recent_fills(client, row.coin, _entry_ms(row.entry_time))
            closed = _close_from_fills(row, fills)
            if closed is None:
                # Fills unavailable (pruned history / data gap): close at the
                # current price so the row can't stay stale forever, but say so.
                exit_price = get_price(client, row.coin)
                if row.direction == "long":
                    pnl = (exit_price - row.entry_price) * row.qty
                else:
                    pnl = (row.entry_price - exit_price) * row.qty
                reason = "reconciled (no fills found)"
            else:
                exit_price, pnl, reason = closed
            pnl_pct = pnl / row.notional_usdt if row.notional_usdt else 0.0
            db.log_swing_close(
                trade_id=row.id,
                exit_price=exit_price,
                realized_pnl_usd=pnl,
                realized_pnl_pct=pnl_pct,
                exit_reason=reason,
            )
            notifier.notify_close(row.coin, {"entry": row.entry_price}, pnl, reason)
            results.append({"coin": row.coin, "pnl": pnl, "reason": reason})
        except Exception as e:
            log.error("Reconcile failed for %s (id=%s): %s", row.coin, row.id, e)
    return results
