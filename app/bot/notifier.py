"""Telegram notifications — trade alerts and daily portfolio summary."""

import logging
from datetime import datetime, timezone
import requests
from binance.client import Client
from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, MAX_DAILY_SPEND
from app.bot.exchange import get_price, get_usdt_balance

log = logging.getLogger(__name__)


def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok:
            log.warning("Telegram non-200: %s %s", r.status_code, r.text)
    except Exception as e:
        log.error("Telegram send failed: %s", e)


def send_daily_summary(client: Client, state: dict, coins: list[str]):
    lines = [
        "📊 <b>Daily Portfolio Summary</b>",
        f"🕗 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n",
    ]
    held_value = 0.0
    for coin in coins:
        data = state.get(coin, {})
        if data.get("qty", 0) > 0 and data.get("avg_buy", 0) > 0:
            try:
                price = get_price(client, coin)
                value = data["qty"] * price
                held_value += value
                pnl_pct = (price - data["avg_buy"]) / data["avg_buy"] * 100
                emoji = "🟢" if pnl_pct >= 0 else "🔴"
                lines.append(f"{emoji} <b>{coin}</b>  {pnl_pct:+.1f}%  |  ${value:.2f}")
            except Exception as e:
                lines.append(f"⚪ {coin}: error — {e}")
        else:
            lines.append(f"⚪ {coin}: no open position")

    usdt_free = get_usdt_balance(client)
    total = held_value + usdt_free
    lines.append(f"\n💵 Free USDT: ${usdt_free:.2f}")
    lines.append(
        f"📉 Daily spent: ${state['daily_spend']['amount']:.2f} / ${MAX_DAILY_SPEND:.2f}"
    )
    lines.append(f"💰 <b>Total est. value: ${total:.2f}</b>")
    send_telegram("\n".join(lines))
