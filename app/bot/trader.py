"""Main trading loop — buy/sell logic and state management."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from binance.client import Client
from binance.exceptions import BinanceAPIException

from app import config
from app import db
from app.bot import heartbeat
from app.bot.exchange import (
    get_price, get_24h_high, get_usdt_balance, buy_market, sell_market,
)
from app.bot.healthcheck import start_health_server
from app.bot.indicators import get_cached_indicators
from app.bot.notifier import send_telegram, send_daily_summary
from app.bot.universe import get_top_coins

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────
def empty_coin_state() -> dict:
    return {"avg_buy": 0.0, "qty": 0.0, "last_buy": None, "peak_price": None}


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


def coin_param(coin: str, param: str, default):
    """Return per-coin override if configured, otherwise return the default."""
    return config.COIN_OVERRIDES.get(coin, {}).get(param, default)


def _clear_position(data: dict, filled_sell_qty: float, coin: str):
    remaining = data["qty"] - filled_sell_qty
    if data["qty"] == 0 or remaining / data["qty"] < 0.001:
        data["qty"]        = 0.0
        data["avg_buy"]    = 0.0
        data["peak_price"] = None
    else:
        data["qty"] = remaining
        log.warning("Partial sell %s: %.6f remaining", coin, remaining)


# ── Watchdog ──────────────────────────────────────────────
def _watchdog_loop(start_time: datetime):
    timeout = timedelta(minutes=config.WATCHDOG_TIMEOUT_MINS)
    alerted = False
    while True:
        time.sleep(60)
        last = heartbeat.get()
        now  = datetime.now(timezone.utc)

        if last is None:
            if now - start_time > timeout:
                if not alerted:
                    send_telegram(
                        f"⚠️ <b>Watchdog Alert</b>\n"
                        f"No cycle completed in >{config.WATCHDOG_TIMEOUT_MINS} minutes."
                    )
                    log.error("Watchdog: no heartbeat since startup")
                    alerted = True
            continue

        age = now - last
        if age > timeout:
            if not alerted:
                send_telegram(
                    f"⚠️ <b>Watchdog Alert</b>\n"
                    f"No cycle in {int(age.total_seconds() // 60)} minutes. Bot may be stuck."
                )
                log.error("Watchdog: no heartbeat for %.0f seconds", age.total_seconds())
                alerted = True
        else:
            alerted = False


def _start_watchdog(start_time: datetime):
    thread = threading.Thread(target=_watchdog_loop, args=(start_time,), daemon=True)
    thread.start()


# ── Main loop ─────────────────────────────────────────────
def run():
    db.init_db()
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
    state  = db.load_state()
    last_summary_date = None
    indicator_cache: dict[str, dict] = {}
    start_time = datetime.now(timezone.utc)

    start_health_server(config.HEALTH_PORT)
    _start_watchdog(start_time)

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
        f"🛑 Trailing stop: -{config.TRAILING_STOP_PCT * 100:.0f}% from peak\n"
        f"📈 DCA drop: -{config.DCA_DROP_PCT * 100:.0f}% below avg buy\n"
        f"💵 Per trade: ${config.TRADE_AMOUNT_USDT}  |  "
        f"Max/coin: ${config.MAX_POSITION_USDT}  |  Max/day: ${config.MAX_DAILY_SPEND}"
    )

    while True:
        try:
            now       = datetime.now(timezone.utc)
            today_str = now.date().isoformat()

            if state["daily_spend"]["date"] != today_str:
                state["daily_spend"] = {"date": today_str, "amount": 0.0}

            if state["coin_list"]["date"] != today_str:
                try:
                    coins = get_top_coins(client)
                    state["coin_list"] = {"date": today_str, "coins": coins}
                    ensure_coin_slots(state, coins)
                    log.info("Coin list refreshed: %s", ", ".join(coins))
                    send_telegram(f"🔄 <b>Coin list updated</b>\n👀 {', '.join(coins)}")
                except Exception as e:
                    log.error("Failed to refresh coin list: %s — keeping previous list", e)

            if now.hour == config.DAILY_REPORT_HOUR and now.date() != last_summary_date:
                send_daily_summary(client, state, active_coins(state))
                last_summary_date = now.date()

            usdt_balance = get_usdt_balance(client)

            btc_ind     = get_cached_indicators(client, "BTC", indicator_cache, now)
            btc_uptrend = btc_ind is not None and get_price(client, "BTC") > btc_ind["ema200"]

            for coin in active_coins(state):
                data = state[coin]
                try:
                    price    = get_price(client, coin)
                    high_24h = get_24h_high(client, coin)

                    # ── Sell logic ───────────────────────────────────
                    if data["qty"] > 0 and data["avg_buy"] > 0:
                        # Keep trailing peak up to date
                        if data["peak_price"] is None or price > data["peak_price"]:
                            data["peak_price"] = price

                        pnl              = (price - data["avg_buy"]) / data["avg_buy"]
                        take_profit      = coin_param(coin, "take_profit",      config.TAKE_PROFIT)
                        trailing_stop    = coin_param(coin, "trailing_stop_pct", config.TRAILING_STOP_PCT)
                        stop_price       = data["peak_price"] * (1 - trailing_stop)
                        drop_from_peak   = (data["peak_price"] - price) / data["peak_price"]

                        if pnl >= take_profit:
                            order           = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            profit_usd      = filled_sell_qty * (price - data["avg_buy"])
                            send_telegram(
                                f"✅ <b>SOLD {coin}</b>  (Take Profit)\n"
                                f"Price:      ${price:,.4f}\n"
                                f"Peak:       ${data['peak_price']:,.4f}\n"
                                f"P&L:        <b>+{pnl * 100:.2f}% (${profit_usd:.2f})</b>"
                            )
                            log.info("SELL %s @ %.4f | +%.2f%%", coin, price, pnl * 100)
                            _clear_position(data, filled_sell_qty, coin)

                        elif price <= stop_price:
                            order           = sell_market(client, coin, data["qty"])
                            filled_sell_qty = float(order["executedQty"])
                            loss_usd        = filled_sell_qty * abs(price - data["avg_buy"])
                            send_telegram(
                                f"🛑 <b>TRAILING STOP {coin}</b>\n"
                                f"Price:      ${price:,.4f}\n"
                                f"Peak:       ${data['peak_price']:,.4f}  "
                                f"(-{drop_from_peak * 100:.1f}% from peak)\n"
                                f"Avg buy:    ${data['avg_buy']:,.4f}\n"
                                f"P&L:        <b>{pnl * 100:.2f}%  "
                                f"({'−' if pnl < 0 else '+'}${loss_usd:.2f})</b>"
                            )
                            log.info("TRAIL %s @ %.4f | pnl=%.2f%% peak=%.4f",
                                     coin, price, pnl * 100, data["peak_price"])
                            _clear_position(data, filled_sell_qty, coin)

                    # ── Buy logic ────────────────────────────────────
                    else:
                        is_first_buy  = data["qty"] == 0
                        dip_threshold = coin_param(coin, "dip_threshold", config.DIP_THRESHOLD)
                        dca_drop      = coin_param(coin, "dca_drop_pct",  config.DCA_DROP_PCT)

                        if is_first_buy:
                            dip    = (high_24h - price) / high_24h if high_24h > 0 else 0
                            dip_ok = dip >= dip_threshold
                        else:
                            # DCA: buy more only when price drops below avg buy
                            dip    = (data["avg_buy"] - price) / data["avg_buy"]
                            dip_ok = price <= data["avg_buy"] * (1 - dca_drop)

                        if data["last_buy"]:
                            last_buy_dt = datetime.fromisoformat(data["last_buy"])
                            if last_buy_dt.tzinfo is None:
                                last_buy_dt = last_buy_dt.replace(tzinfo=timezone.utc)
                        else:
                            last_buy_dt = None

                        cooldown_ok = last_buy_dt is None or (
                            now - last_buy_dt >= timedelta(hours=config.BUY_COOLDOWN_HRS)
                        )
                        position_ok = (
                            data["avg_buy"] * data["qty"] + config.TRADE_AMOUNT_USDT
                            <= config.MAX_POSITION_USDT
                        )
                        daily_ok = (
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
                            dip_ok
                            and cooldown_ok
                            and position_ok
                            and usdt_balance >= config.TRADE_AMOUNT_USDT
                        ):
                            if not btc_uptrend:
                                log.info("SKIP %s — BTC below 200 EMA (bear market)", coin)
                            elif not trend_ok:
                                log.info("SKIP %s — below 200 EMA | EMA=%.2f price=%.2f",
                                         coin, ind["ema200"], price)
                            elif not rsi_ok:
                                log.info("SKIP %s — RSI %.1f not oversold (>%d)",
                                         coin, ind["rsi14"], config.RSI_BUY_THRESHOLD)
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
                                    data["peak_price"] = filled_price  # init peak on first buy

                                data["last_buy"] = now.isoformat()
                                usdt_balance -= config.TRADE_AMOUNT_USDT
                                state["daily_spend"]["amount"] += config.TRADE_AMOUNT_USDT

                                buy_type = "DCA" if not is_first_buy else "Buy"
                                send_telegram(
                                    f"🟢 <b>{buy_type.upper()} {coin}</b>\n"
                                    f"Price:     ${filled_price:,.4f}\n"
                                    f"Spent:     ${config.TRADE_AMOUNT_USDT}\n"
                                    f"Dip:       -{dip * 100:.2f}% "
                                    f"{'from avg buy' if not is_first_buy else 'from 24h high'}\n"
                                    f"Avg buy:   ${data['avg_buy']:,.4f}\n"
                                    f"RSI:       {ind['rsi14']:.1f}\n"
                                    f"EMA200:    ${ind['ema200']:,.2f}\n"
                                    f"Position:  ${data['avg_buy'] * data['qty']:.2f} / ${config.MAX_POSITION_USDT}\n"
                                    f"Day spend: ${state['daily_spend']['amount']:.2f} / ${config.MAX_DAILY_SPEND}\n"
                                    f"USDT left: ${usdt_balance:.2f}"
                                )
                                log.info(
                                    "%s  %s @ %.4f | dip=%.2f%% rsi=%.1f ema=%.2f",
                                    buy_type.upper(), coin, filled_price,
                                    dip * 100, ind["rsi14"], ind["ema200"],
                                )

                except BinanceAPIException as e:
                    log.error("Binance API error [%s]: %s", coin, e)
                except Exception as e:
                    log.error("Unexpected error [%s]: %s", coin, e)

            heartbeat.update()
            try:
                db.save_state(state)
            except Exception as db_err:
                log.error("DB save failed (state held in memory): %s", db_err)
            log.info("Cycle done. Sleeping %ds...", config.CHECK_INTERVAL)
            time.sleep(config.CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ <b>Bot stopped manually.</b> Goodbye!")
            log.info("Bot stopped by user.")
            break
        except BinanceAPIException as e:
            if e.status_code == 503:
                send_telegram("🔧 <b>Binance maintenance (503)</b>\nSleeping 10 minutes...")
                log.warning("Binance 503 — sleeping 10 minutes")
                time.sleep(600)
            else:
                log.error("Binance API error in main loop: %s", e)
                send_telegram(f"⚠️ <b>Binance API error:</b> {e}\nRetrying in 60s...")
                time.sleep(60)
        except Exception as e:
            log.error("Main loop crash: %s", e)
            send_telegram(f"⚠️ <b>Bot error:</b> {e}\nRetrying in 60s...")
            time.sleep(60)
