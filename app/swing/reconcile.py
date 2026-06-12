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

# Cycles to wait for fills to appear before booking an estimated exit price.
# An algo fill normally lands in userTrades within seconds, so a persistent
# miss means pruned/unavailable history. In-memory: a restart resets the
# count, which only delays the fallback — never fabricates earlier.
NO_FILL_RETRY_CYCLES = 3
_no_fill_misses: dict[int, int] = {}


def _entry_ms(entry_time: str) -> int:
    dt = datetime.fromisoformat(entry_time)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _close_from_fills(row, fills: list[dict]) -> tuple[float, float, str] | None:
    """(exit_price, pnl_usd, reason) from closing-side fills, or None if absent.

    Only the first ``row.qty`` of closing-side quantity belongs to this position:
    a later re-entry in the same coin closes with same-side fills, and an
    unbounded sum would pollute this row's VWAP/PnL. realizedPnl intentionally
    excludes commission — consistent with PnL everywhere else in the bot.
    """
    closing_side = "SELL" if row.direction == "long" else "BUY"
    closing = sorted(
        (f for f in fills if f["side"] == closing_side), key=lambda f: f["time"]
    )
    take: list[dict] = []
    cum = 0.0
    for f in closing:
        if cum >= row.qty * 0.999:
            break
        take.append(f)
        cum += float(f["qty"])
    if not take or cum <= 0:
        return None
    exit_price = sum(float(f["price"]) * float(f["qty"]) for f in take) / cum
    pnl = sum(float(f["realizedPnl"]) for f in take)
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
                misses = _no_fill_misses.get(row.id, 0) + 1
                _no_fill_misses[row.id] = misses
                if misses < NO_FILL_RETRY_CYCLES:
                    log.warning(
                        "Reconcile %s (id=%s): no closing fills yet (attempt %d/%d) — retrying next cycle",
                        row.coin, row.id, misses, NO_FILL_RETRY_CYCLES,
                    )
                    continue
                # Fills persistently unavailable: close at the current price so
                # the row can't stay stale forever, but say so in the reason.
                exit_price = get_price(client, row.coin)
                if row.direction == "long":
                    pnl = (exit_price - row.entry_price) * row.qty
                else:
                    pnl = (row.entry_price - exit_price) * row.qty
                reason = "reconciled (no fills found; price-estimated)"
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
            _no_fill_misses.pop(row.id, None)
            notifier.notify_close(row.coin, {"entry": row.entry_price}, pnl, reason)
            results.append({"coin": row.coin, "pnl": pnl, "reason": reason})
        except Exception as e:
            log.error("Reconcile failed for %s (id=%s): %s", row.coin, row.id, e)
    return results
