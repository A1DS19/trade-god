#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║         DCA Crypto Bot — Binance + Telegram      ║
║  Buys dips automatically, sells at profit/loss   ║
╚══════════════════════════════════════════════════╝

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in your keys
  3. python dca_bot.py
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests

# ─────────────────────────────────────────────────────────
#  LOAD CONFIG  (credentials from .env, never config.json)
# ─────────────────────────────────────────────────────────
load_dotenv()

BINANCE_API_KEY    = os.environ["BINANCE_API_KEY"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# ─────────────────────────────────────────────────────────
#  STRATEGY SETTINGS  (tweak these anytime)
# ─────────────────────────────────────────────────────────
COINS = [
    "BTC",
    "ETH",
    "SOL",   # Majors
    "BNB",
    "XRP",
    "ADA",   # Large caps
    "AVAX",
    "LINK",
    "POL",   # Mid caps  (POL = MATIC)
    "TAO",
    "SUI",   # Trending
]
# NOTE: HYPE is not on Binance Spot yet — add it manually once listed.

TRADE_AMOUNT_USDT  = 8.0   # $ spent per buy order
MAX_POSITION_USDT  = 50.0  # Max total cost basis per coin (caps DCA stacking)
MAX_DAILY_SPEND    = 80.0  # Max USDT to spend across all coins per UTC day
DIP_THRESHOLD      = 0.03  # Buy when price dips 3% from 24h high
TAKE_PROFIT        = 0.05  # Sell when position is up +5%
STOP_LOSS          = 0.15  # Sell when position is down -15%
BUY_COOLDOWN_HRS   = 4     # Min hours between buys for same coin
CHECK_INTERVAL     = 300   # Seconds between market checks (5 min)
DAILY_REPORT_HOUR  = 8     # UTC hour to send daily summary

STATE_FILE = "bot_state.json"
LOG_FILE   = "bot.log"

# ─────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  TELEGRAM HELPERS
# ─────────────────────────────────────────────────────────
def send_telegram(msg: str):
    """Send a message to your Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok:
            log.warning(f"Telegram non-200: {r.status_code} {r.text}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


# ─────────────────────────────────────────────────────────
#  STATE  (persisted to bot_state.json between restarts)
# ─────────────────────────────────────────────────────────
def empty_coin_state():
    return {"avg_buy": 0.0, "qty": 0.0, "last_buy": None}


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            saved = json.load(f)
        # Add any new coins that weren't in the saved file
        for coin in COINS:
            if coin not in saved:
                saved[coin] = empty_coin_state()
        if "daily_spend" not in saved:
            saved["daily_spend"] = {"date": None, "amount": 0.0}
        return saved
    except FileNotFoundError:
        state = {coin: empty_coin_state() for coin in COINS}
        state["daily_spend"] = {"date": None, "amount": 0.0}
        return state


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─────────────────────────────────────────────────────────
#  BINANCE HELPERS
# ─────────────────────────────────────────────────────────
def get_price(client: Client, coin: str) -> float:
    ticker = client.get_symbol_ticker(symbol=f"{coin}USDT")
    return float(ticker["price"])


def get_24h_high(client: Client, coin: str) -> float:
    stats = client.get_ticker(symbol=f"{coin}USDT")
    return float(stats["highPrice"])


def get_usdt_balance(client: Client) -> float:
    bal = client.get_asset_balance(asset="USDT")
    return float(bal["free"])


def buy_market(client: Client, coin: str, usdt_amount: float) -> dict:
    """Market buy using quoteOrderQty (spend exact USDT amount)."""
    return client.order_market_buy(
        symbol=f"{coin}USDT",
        quoteOrderQty=round(usdt_amount, 2),
    )


def sell_market(client: Client, coin: str, qty: float) -> dict:
    """Market sell all of a coin, respecting lot-size filter."""
    info = client.get_symbol_info(f"{coin}USDT")
    lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    step = float(lot["stepSize"])
    # Truncate to valid step size
    if step > 0:
        precision = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
        qty = round(qty - (qty % step), precision)
    return client.order_market_sell(symbol=f"{coin}USDT", quantity=qty)


# ─────────────────────────────────────────────────────────
#  REPORTS
# ─────────────────────────────────────────────────────────
def send_daily_summary(client: Client, state: dict):
    lines = [
        "📊 <b>Daily Portfolio Summary</b>",
        f"🕗 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n",
    ]
    held_value = 0.0
    for coin in COINS:
        data = state[coin]
        if data["qty"] > 0 and data["avg_buy"] > 0:
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
    lines.append(f"📉 Daily spent: ${state['daily_spend']['amount']:.2f} / ${MAX_DAILY_SPEND:.2f}")
    lines.append(f"💰 <b>Total est. value: ${total:.2f}</b>")
    send_telegram("\n".join(lines))


# ─────────────────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────────────────
def run():
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    state = load_state()
    last_summary_date = None

    send_telegram(
        "🤖 <b>DCA Bot is LIVE!</b>\n"
        f"👀 Watching: {', '.join(COINS)}\n"
        f"📉 Buy trigger: -{DIP_THRESHOLD * 100:.0f}% dip from 24h high\n"
        f"✅ Take profit: +{TAKE_PROFIT * 100:.0f}%\n"
        f"🛑 Stop loss: -{STOP_LOSS * 100:.0f}%\n"
        f"💵 Per trade: ${TRADE_AMOUNT_USDT}  |  Max/coin: ${MAX_POSITION_USDT}  |  Max/day: ${MAX_DAILY_SPEND}"
    )
    log.info("Bot started. Watching: %s", ", ".join(COINS))

    while True:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.date().isoformat()

            # ── Reset daily spend counter at UTC midnight ──
            if state["daily_spend"]["date"] != today_str:
                state["daily_spend"] = {"date": today_str, "amount": 0.0}

            # ── Daily summary ──
            if now.hour == DAILY_REPORT_HOUR and now.date() != last_summary_date:
                send_daily_summary(client, state)
                last_summary_date = now.date()

            usdt_balance = get_usdt_balance(client)

            for coin in COINS:
                data = state[coin]
                try:
                    price = get_price(client, coin)
                    high_24h = get_24h_high(client, coin)

                    # ────── SELL LOGIC ──────────────────────────────
                    if data["qty"] > 0 and data["avg_buy"] > 0:
                        pnl = (price - data["avg_buy"]) / data["avg_buy"]

                        if pnl >= TAKE_PROFIT:
                            order = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            profit_usd = filled_sell_qty * (price - data["avg_buy"])
                            send_telegram(
                                f"✅ <b>SOLD {coin}</b>  (Take Profit)\n"
                                f"Price: ${price:,.4f}\n"
                                f"P&L:   <b>+{pnl * 100:.2f}% (${profit_usd:.2f})</b>"
                            )
                            log.info("SELL %s @ %.4f | +%.2f%%", coin, price, pnl * 100)
                            remaining = data["qty"] - filled_sell_qty
                            if remaining / data["qty"] < 0.001:
                                data["qty"] = 0.0
                                data["avg_buy"] = 0.0
                            else:
                                data["qty"] = remaining
                                log.warning("Partial sell %s: %.6f remaining", coin, remaining)

                        elif pnl <= -STOP_LOSS:
                            order = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            loss_usd = filled_sell_qty * (data["avg_buy"] - price)
                            send_telegram(
                                f"🛑 <b>STOP LOSS {coin}</b>\n"
                                f"Price: ${price:,.4f}\n"
                                f"P&L:   <b>{pnl * 100:.2f}% (-${loss_usd:.2f})</b>\n"
                                f"Capital protected — watching for next dip."
                            )
                            log.info("STOP  %s @ %.4f | %.2f%%", coin, price, pnl * 100)
                            remaining = data["qty"] - filled_sell_qty
                            if remaining / data["qty"] < 0.001:
                                data["qty"] = 0.0
                                data["avg_buy"] = 0.0
                            else:
                                data["qty"] = remaining
                                log.warning("Partial sell %s: %.6f remaining", coin, remaining)

                    # ────── BUY LOGIC ───────────────────────────────
                    else:
                        dip = (high_24h - price) / high_24h if high_24h > 0 else 0

                        # Cooldown check
                        if data["last_buy"]:
                            last_buy_dt = datetime.fromisoformat(data["last_buy"])
                            # Handle naive datetimes from old state files (assume UTC)
                            if last_buy_dt.tzinfo is None:
                                last_buy_dt = last_buy_dt.replace(tzinfo=timezone.utc)
                        else:
                            last_buy_dt = None
                        cooldown_ok = last_buy_dt is None or (
                            now - last_buy_dt
                        ) >= timedelta(hours=BUY_COOLDOWN_HRS)

                        # Position cap check (cost basis, not current value)
                        current_position_cost = data["avg_buy"] * data["qty"]
                        position_ok = current_position_cost + TRADE_AMOUNT_USDT <= MAX_POSITION_USDT

                        # Daily spend cap check
                        daily_ok = state["daily_spend"]["amount"] + TRADE_AMOUNT_USDT <= MAX_DAILY_SPEND

                        if not daily_ok:
                            log.info("Daily spend cap reached ($%.2f). Skipping %s.", MAX_DAILY_SPEND, coin)
                            continue

                        if (
                            dip >= DIP_THRESHOLD
                            and usdt_balance >= TRADE_AMOUNT_USDT
                            and cooldown_ok
                            and position_ok
                        ):
                            order = buy_market(client, coin, TRADE_AMOUNT_USDT)
                            filled_qty = float(order["executedQty"])
                            filled_price = (
                                float(order["cummulativeQuoteQty"]) / filled_qty
                            )

                            # DCA average — stack positions if re-entering
                            if data["qty"] > 0:
                                total_cost = (
                                    data["avg_buy"] * data["qty"] + TRADE_AMOUNT_USDT
                                )
                                data["qty"] += filled_qty
                                data["avg_buy"] = total_cost / data["qty"]
                            else:
                                data["qty"] = filled_qty
                                data["avg_buy"] = filled_price

                            data["last_buy"] = now.isoformat()
                            usdt_balance -= TRADE_AMOUNT_USDT
                            state["daily_spend"]["amount"] += TRADE_AMOUNT_USDT

                            send_telegram(
                                f"🟢 <b>BOUGHT {coin}</b>\n"
                                f"Price:    ${filled_price:,.4f}\n"
                                f"Spent:    ${TRADE_AMOUNT_USDT}\n"
                                f"Dip:      -{dip * 100:.2f}% from 24h high\n"
                                f"Position: ${data['avg_buy'] * data['qty']:.2f} / ${MAX_POSITION_USDT}\n"
                                f"Day spend: ${state['daily_spend']['amount']:.2f} / ${MAX_DAILY_SPEND}\n"
                                f"USDT left: ${usdt_balance:.2f}"
                            )
                            log.info(
                                "BUY  %s @ %.4f | dip=%.2f%%",
                                coin,
                                filled_price,
                                dip * 100,
                            )

                except BinanceAPIException as e:
                    log.error("Binance API error [%s]: %s", coin, e)
                except Exception as e:
                    log.error("Unexpected error [%s]: %s", coin, e)

            save_state(state)
            log.info("Cycle done. Sleeping %ds...", CHECK_INTERVAL)
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ <b>Bot stopped manually.</b> Goodbye!")
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.error("Main loop crash: %s", e)
            send_telegram(f"⚠️ <b>Bot error:</b> {e}\nRetrying in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    run()
