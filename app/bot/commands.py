"""Telegram command handler — polls for /commands and replies."""

import logging
import threading
import time
from datetime import datetime, timezone

import requests
from binance.client import Client

from app import config
from app.bot.exchange import get_price, get_usdt_balance
from app.db.models import Position, Trade, Session, engine

log = logging.getLogger(__name__)


def _send(text: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.error("Command reply failed: %s", e)


def _status() -> str:
    with Session(engine) as session:
        positions = session.query(Position).filter(Position.qty > 0).all()

    if not positions:
        return "📭 No open positions."

    lines = ["📊 <b>Open Positions</b>\n"]
    for p in sorted(positions, key=lambda x: x.coin):
        cost = p.avg_buy * p.qty
        flag = "  🟡 <i>partial sold</i>" if p.partial_taken else ""
        lines.append(
            f"<b>{p.coin}</b>  qty={p.qty:.6f}\n"
            f"  avg buy: ${p.avg_buy:,.4f}  |  cost: ${cost:.2f}{flag}"
        )
    return "\n\n".join(lines)


def _pnl() -> str:
    today_str = datetime.now(timezone.utc).date().isoformat()
    with Session(engine) as session:
        today_sells = (
            session.query(Trade)
            .filter(Trade.side == "SELL", Trade.timestamp.startswith(today_str))
            .all()
        )
        all_sells = session.query(Trade).filter(Trade.side == "SELL").all()

    pnl_today = sum(t.realized_pnl_usd or 0.0 for t in today_sells)
    pnl_total = sum(t.realized_pnl_usd or 0.0 for t in all_sells)
    wins      = sum(1 for t in all_sells if (t.realized_pnl_usd or 0) > 0)
    win_rate  = wins / len(all_sells) * 100 if all_sells else 0

    e_today = "🟢" if pnl_today >= 0 else "🔴"
    e_total = "🟢" if pnl_total >= 0 else "🔴"

    return (
        f"💰 <b>Realized P&L</b>\n\n"
        f"{e_today} Today:     <b>${pnl_today:+.2f}</b>  ({len(today_sells)} trades)\n"
        f"{e_total} All-time:  <b>${pnl_total:+.2f}</b>  ({len(all_sells)} trades)\n"
        f"🎯 Win rate:   {win_rate:.1f}%"
    )


def _trades(n: int) -> str:
    with Session(engine) as session:
        rows = (
            session.query(Trade)
            .order_by(Trade.id.desc())
            .limit(n)
            .all()
        )

    if not rows:
        return "📋 No trades recorded yet."

    lines = [f"📋 <b>Last {len(rows)} Trades</b>\n"]
    for t in rows:
        ts = t.timestamp[:10]
        if t.side == "BUY":
            lines.append(f"🟢 BUY  <b>{t.coin}</b>  ${t.price:,.4f}  [{ts}]")
        else:
            pnl = t.realized_pnl_usd or 0.0
            emoji = "✅" if pnl >= 0 else "🛑"
            pct   = f"{t.realized_pnl_pct * 100:+.1f}%" if t.realized_pnl_pct is not None else ""
            lines.append(
                f"{emoji} SELL <b>{t.coin}</b>  ${t.price:,.4f}  "
                f"<b>${pnl:+.2f}</b> {pct}  ({t.exit_reason})  [{ts}]"
            )
    return "\n".join(lines)


def _balance(client: Client) -> str:
    try:
        usdt = get_usdt_balance(client)
    except Exception as e:
        usdt = None
        log.warning("Could not fetch USDT balance: %s", e)

    with Session(engine) as session:
        positions = session.query(Position).filter(Position.qty > 0).all()

    cost_basis = sum(p.avg_buy * p.qty for p in positions)

    lines = ["💵 <b>Balance</b>\n"]
    if usdt is not None:
        total = usdt + cost_basis
        lines.append(f"Free USDT:    ${usdt:.2f}")
        lines.append(f"In positions: ${cost_basis:.2f}  ({len(positions)} coins)")
        lines.append(f"<b>Total est.:   ${total:.2f}</b>")
    else:
        lines.append(f"In positions: ${cost_basis:.2f}  ({len(positions)} coins)")
        lines.append("(Could not fetch live USDT balance)")
    return "\n".join(lines)


_HELP = (
    "🤖 <b>Commands</b>\n\n"
    "/status        — open positions\n"
    "/pnl           — realized P&L + win rate\n"
    "/trades [n]    — last N trades (default 5)\n"
    "/balance       — free USDT + portfolio cost\n"
    "/help          — this message"
)


def _poll_loop(client: Client):
    offset = 0
    log.info("Telegram command polling started.")

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                timeout=35,
            )
            if not resp.ok:
                time.sleep(5)
                continue

            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                msg     = update.get("message", {})
                text    = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                if chat_id != str(config.TELEGRAM_CHAT_ID):
                    continue

                parts = text.split()
                cmd   = parts[0].lower() if parts else ""
                args  = parts[1:]

                if cmd == "/status":
                    _send(_status())
                elif cmd == "/pnl":
                    _send(_pnl())
                elif cmd == "/trades":
                    n = int(args[0]) if args and args[0].isdigit() else 5
                    _send(_trades(min(n, 20)))
                elif cmd == "/balance":
                    _send(_balance(client))
                elif cmd == "/help":
                    _send(_HELP)

        except Exception as e:
            log.error("Telegram polling error: %s", e)
            time.sleep(10)


def start_command_handler(client: Client):
    thread = threading.Thread(target=_poll_loop, args=(client,), daemon=True)
    thread.start()
