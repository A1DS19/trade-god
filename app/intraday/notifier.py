"""Telegram notifications for the intraday paper engine."""

import html
import logging

import requests

from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send(msg: str):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram rejected message: %s", data)
    except Exception as e:
        log.error("Telegram error: %s", e)


def notify_fill(symbol: str, entry_price: float, z: float):
    send(f"📥 <b>PAPER FILL {html.escape(symbol)}</b>\n"
         f"Entry: ${entry_price:,.6g}  (z={z:.2f})")


def notify_exit(symbol: str, pnl_usd: float, pnl_pct: float, hold_bars: int):
    emoji = "✅" if pnl_usd >= 0 else "🛑"
    send(f"{emoji} <b>PAPER EXIT {html.escape(symbol)}</b>\n"
         f"PnL: <b>{pnl_usd:+.2f} USDT</b> ({pnl_pct * 100:+.2f}%) "
         f"over {hold_bars} bars")


def notify_halt(reason: str, equity: float):
    send(f"⛔ <b>KILL-SWITCH: {html.escape(reason)}</b>\n"
         f"Paper equity: ${equity:,.2f}\n"
         f"Trading halted. Resume with INTRADAY_RESUME=1.")


def notify_error_strikes(symbol: str, n: int):
    send(f"⚠️ <b>{html.escape(symbol)}</b> failed {n} consecutive cycles")


def notify_daily_summary(text: str):
    send(f"📊 <b>Intraday daily summary</b>\n{text}")
