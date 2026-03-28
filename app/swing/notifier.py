"""Telegram notifications for the swing agent."""

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


def notify_open(coin: str, action: str, price: float, decision: dict):
    emoji = "🟢" if action == "long" else "🔴"
    send(
        f"{emoji} <b>SWING {action.upper()} {coin}</b>\n"
        f"Entry:      ${price:,.4f}\n"
        f"SL:         -{decision['sl_pct'] * 100:.1f}%\n"
        f"TP:         +{decision['tp_pct'] * 100:.1f}%\n"
        f"Confidence: {decision['confidence'] * 100:.0f}%\n"
        f"Reason:     {decision['reasoning']}"
    )


def notify_close(coin: str, pos: dict, pnl: float, reason: str):
    emoji = "✅" if pnl >= 0 else "🛑"
    send(
        f"{emoji} <b>CLOSE {coin}</b>  ({reason})\n"
        f"Entry: ${pos['entry']:,.4f}\n"
        f"PnL:   <b>{'+'if pnl>=0 else ''}{pnl:.2f} USDT</b>"
    )


def notify_skip(coin: str, action: str, confidence: float, reason: str):
    send(
        f"⏭ <b>SKIP {coin}</b>  agent→{action} ({confidence*100:.0f}%)\n"
        f"{reason}"
    )
