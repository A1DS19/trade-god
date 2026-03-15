"""Main trading loop — buy/sell logic and state management."""

import logging
import time
from datetime import datetime, timedelta, timezone

from binance.client import Client
from binance.exceptions import BinanceAPIException

from app import config
from app import db
from app.bot.exchange import (
    get_price, get_24h_high, get_usdt_balance, buy_market, sell_market,
)
from app.bot.indicators import get_cached_indicators
from app.bot.notifier import send_telegram, send_daily_summary
from app.bot.universe import get_top_coins

log = logging.getLogger(__name__)


# ── State helpers ─────────────────────────────────────────
def empty_coin_state() -> dict:
    return {"avg_buy": 0.0, "qty": 0.0, "last_buy": None}


def ensure_coin_slots(state: dict, coins: list[str]):
    for coin in coins:
        if coin not in state:
            state[coin] = empty_coin_state()


def active_coins(state: dict) -> list[str]:
    """Watch list + any coins with an open position (never drops held coins)."""
    watch = set(state["coin_list"]["coins"])
    held  = {
        coin for coin, data in state.items()
        if isinstance(data, dict)
        and data.get("qty", 0) > 0
        and coin not in ("daily_spend", "coin_list")
    }
    return list(watch | held)


def _clear_position(data: dict, filled_sell_qty: float, coin: str):
    remaining = data["qty"] - filled_sell_qty
    if data["qty"] == 0 or remaining / data["qty"] < 0.001:
        data["qty"]     = 0.0
        data["avg_buy"] = 0.0
    else:
        data["qty"] = remaining
        log.warning("Partial sell %s: %.6f remaining", coin, remaining)


# ── Main loop ─────────────────────────────────────────────
def run():
    db.init_db()
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
    state  = db.load_state()
    last_summary_date = None
    indicator_cache: dict[str, dict] = {}

    # Initial coin list — only fetch from CoinGecko if today's list isn't cached
    today_str = datetime.now(timezone.utc).date().isoformat()
    if state["coin_list"]["date"] == today_str and state["coin_list"]["coins"]:
        coins = state["coin_list"]["coins"]
        log.info("Using cached coin list from DB")
    else:
        log.info("Fetching top %d coins by market cap...", config.TOP_N_COINS)
        try:
            coins = get_top_coins(client)
            state["coin_list"] = {"date": today_str, "coins": coins}
        except Exception as e:
            log.warning("Could not fetch coin list: %s — using previous list", e)
            coins = state["coin_list"]["coins"] or ["BTC", "ETH", "SOL", "BNB", "XRP"]
    ensure_coin_slots(state, coins)
    log.info("Watching: %s", ", ".join(coins))

    send_telegram(
        "🤖 <b>DCA Bot is LIVE!</b>\n"
        f"👀 Top {config.TOP_N_COINS} by market cap: {', '.join(coins)}\n"
        f"📉 Buy trigger: -{config.DIP_THRESHOLD * 100:.0f}% dip  |  "
        f"RSI &lt; {config.RSI_BUY_THRESHOLD}  |  Above 200 EMA  |  BTC uptrend\n"
        f"✅ Take profit: +{config.TAKE_PROFIT * 100:.0f}%\n"
        f"🛑 Stop loss: -{config.STOP_LOSS * 100:.0f}%\n"
        f"💵 Per trade: ${config.TRADE_AMOUNT_USDT}  |  "
        f"Max/coin: ${config.MAX_POSITION_USDT}  |  Max/day: ${config.MAX_DAILY_SPEND}"
    )

    while True:
        try:
            now       = datetime.now(timezone.utc)
            today_str = now.date().isoformat()

            # Reset daily spend at UTC midnight
            if state["daily_spend"]["date"] != today_str:
                state["daily_spend"] = {"date": today_str, "amount": 0.0}

            # Refresh coin list once per day
            if state["coin_list"]["date"] != today_str:
                try:
                    coins = get_top_coins(client)
                    state["coin_list"] = {"date": today_str, "coins": coins}
                    ensure_coin_slots(state, coins)
                    log.info("Coin list refreshed: %s", ", ".join(coins))
                    send_telegram(f"🔄 <b>Coin list updated</b>\n👀 {', '.join(coins)}")
                except Exception as e:
                    log.error("Failed to refresh coin list: %s — keeping previous list", e)

            # Daily summary
            if now.hour == config.DAILY_REPORT_HOUR and now.date() != last_summary_date:
                send_daily_summary(client, state, active_coins(state))
                last_summary_date = now.date()

            usdt_balance = get_usdt_balance(client)

            # BTC market filter — computed once per cycle
            btc_ind = get_cached_indicators(client, "BTC", indicator_cache, now)
            btc_uptrend = btc_ind is not None and get_price(client, "BTC") > btc_ind["ema200"]

            for coin in active_coins(state):
                data = state[coin]
                try:
                    price    = get_price(client, coin)
                    high_24h = get_24h_high(client, coin)

                    # ── Sell logic ───────────────────────────────────
                    if data["qty"] > 0 and data["avg_buy"] > 0:
                        pnl = (price - data["avg_buy"]) / data["avg_buy"]

                        if pnl >= config.TAKE_PROFIT:
                            order           = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            profit_usd      = filled_sell_qty * (price - data["avg_buy"])
                            send_telegram(
                                f"✅ <b>SOLD {coin}</b>  (Take Profit)\n"
                                f"Price: ${price:,.4f}\n"
                                f"P&L:   <b>+{pnl * 100:.2f}% (${profit_usd:.2f})</b>"
                            )
                            log.info("SELL %s @ %.4f | +%.2f%%", coin, price, pnl * 100)
                            _clear_position(data, filled_sell_qty, coin)

                        elif pnl <= -config.STOP_LOSS:
                            order           = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            loss_usd        = filled_sell_qty * (data["avg_buy"] - price)
                            send_telegram(
                                f"🛑 <b>STOP LOSS {coin}</b>\n"
                                f"Price: ${price:,.4f}\n"
                                f"P&L:   <b>{pnl * 100:.2f}% (-${loss_usd:.2f})</b>\n"
                                f"Capital protected — watching for next dip."
                            )
                            log.info("STOP  %s @ %.4f | %.2f%%", coin, price, pnl * 100)
                            _clear_position(data, filled_sell_qty, coin)

                    # ── Buy logic ────────────────────────────────────
                    else:
                        dip = (high_24h - price) / high_24h if high_24h > 0 else 0

                        if data["last_buy"]:
                            last_buy_dt = datetime.fromisoformat(data["last_buy"])
                            if last_buy_dt.tzinfo is None:
                                last_buy_dt = last_buy_dt.replace(tzinfo=timezone.utc)
                        else:
                            last_buy_dt = None

                        cooldown_ok   = last_buy_dt is None or (
                            now - last_buy_dt >= timedelta(hours=config.BUY_COOLDOWN_HRS)
                        )
                        position_ok   = (
                            data["avg_buy"] * data["qty"] + config.TRADE_AMOUNT_USDT
                            <= config.MAX_POSITION_USDT
                        )
                        daily_ok      = (
                            state["daily_spend"]["amount"] + config.TRADE_AMOUNT_USDT
                            <= config.MAX_DAILY_SPEND
                        )

                        if not daily_ok:
                            log.info("Daily cap reached. Skipping %s.", coin)
                            continue

                        ind = get_cached_indicators(client, coin, indicator_cache, now)
                        if ind is None:
                            log.warning("No indicators for %s, skipping.", coin)
                            continue

                        trend_ok  = price > ind["ema200"]
                        rsi_ok    = ind["rsi14"] < config.RSI_BUY_THRESHOLD
                        volume_ok = ind["vol_ratio"] < config.VOLUME_SPIKE_RATIO

                        if (
                            dip >= config.DIP_THRESHOLD
                            and cooldown_ok
                            and position_ok
                            and usdt_balance >= config.TRADE_AMOUNT_USDT
                        ):
                            if not btc_uptrend:
                                log.info("SKIP %s — BTC below 200 EMA (bear market)", coin)
                            elif not trend_ok:
                                log.info("SKIP %s — below 200 EMA | EMA=%.2f price=%.2f", coin, ind["ema200"], price)
                            elif not rsi_ok:
                                log.info("SKIP %s — RSI %.1f not oversold (>%d)", coin, ind["rsi14"], config.RSI_BUY_THRESHOLD)
                            elif not volume_ok:
                                log.info("SKIP %s — volume spike %.1fx avg", coin, ind["vol_ratio"])
                            else:
                                order        = buy_market(client, coin, config.TRADE_AMOUNT_USDT)
                                filled_qty   = float(order["executedQty"])
                                filled_price = float(order["cummulativeQuoteQty"]) / filled_qty

                                if data["qty"] > 0:
                                    total_cost      = data["avg_buy"] * data["qty"] + config.TRADE_AMOUNT_USDT
                                    data["qty"]    += filled_qty
                                    data["avg_buy"] = total_cost / data["qty"]
                                else:
                                    data["qty"]     = filled_qty
                                    data["avg_buy"] = filled_price

                                data["last_buy"] = now.isoformat()
                                usdt_balance -= config.TRADE_AMOUNT_USDT
                                state["daily_spend"]["amount"] += config.TRADE_AMOUNT_USDT

                                send_telegram(
                                    f"🟢 <b>BOUGHT {coin}</b>\n"
                                    f"Price:     ${filled_price:,.4f}\n"
                                    f"Spent:     ${config.TRADE_AMOUNT_USDT}\n"
                                    f"Dip:       -{dip * 100:.2f}% from 24h high\n"
                                    f"RSI:       {ind['rsi14']:.1f}\n"
                                    f"EMA200:    ${ind['ema200']:,.2f}\n"
                                    f"Position:  ${data['avg_buy'] * data['qty']:.2f} / ${config.MAX_POSITION_USDT}\n"
                                    f"Day spend: ${state['daily_spend']['amount']:.2f} / ${config.MAX_DAILY_SPEND}\n"
                                    f"USDT left: ${usdt_balance:.2f}"
                                )
                                log.info(
                                    "BUY  %s @ %.4f | dip=%.2f%% rsi=%.1f ema=%.2f",
                                    coin, filled_price, dip * 100, ind["rsi14"], ind["ema200"],
                                )

                except BinanceAPIException as e:
                    log.error("Binance API error [%s]: %s", coin, e)
                except Exception as e:
                    log.error("Unexpected error [%s]: %s", coin, e)

            db.save_state(state)
            log.info("Cycle done. Sleeping %ds...", config.CHECK_INTERVAL)
            time.sleep(config.CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ <b>Bot stopped manually.</b> Goodbye!")
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.error("Main loop crash: %s", e)
            send_telegram(f"⚠️ <b>Bot error:</b> {e}\nRetrying in 60s...")
            time.sleep(60)
