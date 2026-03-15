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

Buy filters (all must pass):
  - Price dip ≥ DIP_THRESHOLD from 24h high
  - Price above 200-day EMA  (uptrend filter)
  - RSI(14) < RSI_BUY_THRESHOLD  (oversold filter)
  - Volume not spiking  (dump filter)
  - BTC in uptrend  (market filter)

Coin selection:
  - Auto-refreshed daily from Binance (top N by 24h USDT volume)
  - Stablecoins and wrapped tokens are excluded automatically
  - Open positions are always kept even if a coin drops off the list
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests
import db

# ─────────────────────────────────────────────────────────
#  LOAD CONFIG  (credentials from .env, never config.json)
# ─────────────────────────────────────────────────────────
load_dotenv()

BINANCE_API_KEY = os.environ["BINANCE_API_KEY"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ─────────────────────────────────────────────────────────
#  STRATEGY SETTINGS  (tweak these anytime)
# ─────────────────────────────────────────────────────────

# ── Coin universe — refreshed daily from Binance ───────
TOP_N_COINS = 20  # How many coins to watch (by 24h USDT volume)

# Exclude stablecoins, wrapped tokens, and high-risk assets
COIN_BLACKLIST = {
    # Stablecoins — pegged to $1, no DCA upside
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDE", "USD1", "USDP",
    # Wrapped / synthetic — duplicates of coins already on the list
    "WBTC", "WBETH", "WBNB", "BETH", "PAXG", "XAUT",
    # WLFI — 78% of supply held by top 10 wallets, extreme whale dump risk
    # ZEC  — privacy coin with active exchange delisting risk
    "WLFI", "ZEC",
}

TRADE_AMOUNT_USDT = 8.0  # $ spent per buy order
MAX_POSITION_USDT = 50.0  # Max total cost basis per coin (caps DCA stacking)
MAX_DAILY_SPEND = 80.0  # Max USDT to spend across all coins per UTC day
DIP_THRESHOLD = 0.03  # Buy when price dips 3% from 24h high
TAKE_PROFIT = 0.05  # Sell when position is up +5%
STOP_LOSS = 0.15  # Sell when position is down -15%
BUY_COOLDOWN_HRS = 4  # Min hours between buys for same coin
CHECK_INTERVAL = 300  # Seconds between market checks (5 min)
DAILY_REPORT_HOUR = 8  # UTC hour to send daily summary

# ── Quant filters ──────────────────────────────────────
RSI_BUY_THRESHOLD = 45  # Only buy when RSI(14) is below this (oversold)
VOLUME_SPIKE_RATIO = 2.0  # Skip buy if volume is this many × the 20-day average
INDICATOR_TTL_SECS = 3600  # Cache daily indicators for 1 hour (they're slow-moving)

LOG_FILE = "bot.log"

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
#  STATE  (persisted to PostgreSQL via db.py)
# ─────────────────────────────────────────────────────────
def empty_coin_state():
    return {"avg_buy": 0.0, "qty": 0.0, "last_buy": None}


def ensure_coin_slots(state: dict, coins: list[str]):
    """Add in-memory slots for any coins not yet in the working state."""
    for coin in coins:
        if coin not in state:
            state[coin] = empty_coin_state()


def active_coins(state: dict) -> list[str]:
    """
    Return the current watch list union any coins with open positions
    (so we never lose track of a held coin that dropped off the top list).
    """
    watch = set(state["coin_list"]["coins"])
    held  = {coin for coin, data in state.items()
             if isinstance(data, dict) and data.get("qty", 0) > 0
             and coin not in ("daily_spend", "coin_list")}
    return list(watch | held)


# ─────────────────────────────────────────────────────────
#  COIN UNIVERSE  (dynamic, refreshed daily via CoinGecko)
# ─────────────────────────────────────────────────────────
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"


def get_top_coins(client: Client) -> list[str]:
    """
    Fetch the top coins by market cap from CoinGecko, then cross-check
    against active Binance USDT spot pairs so we only trade listed coins.
    BTC is always included as it doubles as the market filter.
    """
    # Step 1 — top coins by market cap from CoinGecko (no API key needed)
    resp = requests.get(
        COINGECKO_URL,
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 60,   # fetch extra to absorb blacklist removals
            "page": 1,
            "sparkline": False,
        },
        timeout=15,
    )
    resp.raise_for_status()
    cg_coins = [row["symbol"].upper() for row in resp.json()]

    # Step 2 — active USDT spot pairs on Binance
    info = client.get_exchange_info()
    binance_spot = {
        s["baseAsset"]
        for s in info["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    }

    # Step 3 — filter and pick top N
    coins = []
    for coin in cg_coins:
        if coin in COIN_BLACKLIST:
            continue
        if coin not in binance_spot:
            log.debug("Skipping %s — not on Binance Spot", coin)
            continue
        coins.append(coin)
        if len(coins) >= TOP_N_COINS:
            break

    # BTC must always be present for the market filter
    if "BTC" not in coins:
        coins.insert(0, "BTC")

    return coins


# ─────────────────────────────────────────────────────────
#  QUANT INDICATORS  (pure Python, no extra dependencies)
# ─────────────────────────────────────────────────────────
def calc_ema(closes: list[float], period: int) -> float:
    """Exponential moving average over a list of closing prices."""
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
    """RSI using Wilder's smoothing method."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def get_indicators(client: Client, coin: str) -> dict:
    """
    Fetch 215 daily candles and return:
      ema200     — 200-day EMA of closing prices
      rsi14      — RSI(14) of closing prices
      vol_ratio  — today's volume vs 20-day average volume
    """
    klines = client.get_klines(
        symbol=f"{coin}USDT",
        interval=Client.KLINE_INTERVAL_1DAY,
        limit=215,  # 200 for EMA + 15 buffer for RSI warmup
    )
    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    ema200 = calc_ema(closes, 200)
    rsi14 = calc_rsi(closes[-30:], 14)  # last 30 days is plenty for RSI
    avg_vol = sum(volumes[-21:-1]) / 20  # 20-day average excluding today
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    return {"ema200": ema200, "rsi14": rsi14, "vol_ratio": vol_ratio}


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
    for coin in active_coins(state):
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
    lines.append(
        f"📉 Daily spent: ${state['daily_spend']['amount']:.2f} / ${MAX_DAILY_SPEND:.2f}"
    )
    lines.append(f"💰 <b>Total est. value: ${total:.2f}</b>")
    send_telegram("\n".join(lines))


# ─────────────────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────────────────
def run():
    db.init_db()
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    state = db.load_state()
    last_summary_date = None

    # indicator_cache[coin] = {"ema200": x, "rsi14": x, "vol_ratio": x, "cached_at": datetime}
    indicator_cache: dict[str, dict] = {}

    # ── Initial coin list fetch ──
    log.info("Fetching top %d coins by 24h volume...", TOP_N_COINS)
    coins = get_top_coins(client)
    state["coin_list"] = {"date": datetime.now(timezone.utc).date().isoformat(), "coins": coins}
    ensure_coin_slots(state, coins)
    log.info("Watching: %s", ", ".join(coins))

    send_telegram(
        "🤖 <b>DCA Bot is LIVE!</b>\n"
        f"👀 Top {TOP_N_COINS} by volume: {', '.join(coins)}\n"
        f"📉 Buy trigger: -{DIP_THRESHOLD * 100:.0f}% dip  |  RSI &lt; {RSI_BUY_THRESHOLD}  |  Above 200 EMA  |  BTC uptrend\n"
        f"✅ Take profit: +{TAKE_PROFIT * 100:.0f}%\n"
        f"🛑 Stop loss: -{STOP_LOSS * 100:.0f}%\n"
        f"💵 Per trade: ${TRADE_AMOUNT_USDT}  |  Max/coin: ${MAX_POSITION_USDT}  |  Max/day: ${MAX_DAILY_SPEND}"
    )

    while True:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.date().isoformat()

            # ── Reset daily spend counter at UTC midnight ──
            if state["daily_spend"]["date"] != today_str:
                state["daily_spend"] = {"date": today_str, "amount": 0.0}

            # ── Refresh coin list once per day ──
            if state["coin_list"]["date"] != today_str:
                try:
                    coins = get_top_coins(client)
                    state["coin_list"] = {"date": today_str, "coins": coins}
                    ensure_coin_slots(state, coins)
                    log.info("Coin list refreshed: %s", ", ".join(coins))
                    send_telegram(f"🔄 <b>Coin list updated</b>\n👀 {', '.join(coins)}")
                except Exception as e:
                    log.error("Failed to refresh coin list: %s — keeping previous list", e)

            # ── Daily summary ──
            if now.hour == DAILY_REPORT_HOUR and now.date() != last_summary_date:
                send_daily_summary(client, state)
                last_summary_date = now.date()

            usdt_balance = get_usdt_balance(client)

            # ── BTC market filter — fetch once per cycle ──
            btc_ind = _get_cached_indicators(client, "BTC", indicator_cache, now)
            btc_uptrend = (
                btc_ind is not None and get_price(client, "BTC") > btc_ind["ema200"]
            )

            for coin in active_coins(state):
                data = state[coin]
                try:
                    price = get_price(client, coin)
                    high_24h = get_24h_high(client, coin)

                    # ────── SELL LOGIC ──────────────────────────────
                    # Sells always execute — quant filters only gate buys
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
                            _clear_position(data, filled_sell_qty, coin)

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
                            _clear_position(data, filled_sell_qty, coin)

                    # ────── BUY LOGIC ───────────────────────────────
                    else:
                        dip = (high_24h - price) / high_24h if high_24h > 0 else 0

                        # Cooldown check
                        if data["last_buy"]:
                            last_buy_dt = datetime.fromisoformat(data["last_buy"])
                            if last_buy_dt.tzinfo is None:
                                last_buy_dt = last_buy_dt.replace(tzinfo=timezone.utc)
                        else:
                            last_buy_dt = None
                        cooldown_ok = last_buy_dt is None or (
                            now - last_buy_dt >= timedelta(hours=BUY_COOLDOWN_HRS)
                        )

                        # Position and daily caps
                        current_position_cost = data["avg_buy"] * data["qty"]
                        position_ok = (
                            current_position_cost + TRADE_AMOUNT_USDT
                            <= MAX_POSITION_USDT
                        )
                        daily_ok = (
                            state["daily_spend"]["amount"] + TRADE_AMOUNT_USDT
                            <= MAX_DAILY_SPEND
                        )

                        if not daily_ok:
                            log.info("Daily cap reached. Skipping %s.", coin)
                            continue

                        # Quant filters
                        ind = _get_cached_indicators(client, coin, indicator_cache, now)
                        if ind is None:
                            log.warning(
                                "Could not get indicators for %s, skipping.", coin
                            )
                            continue

                        trend_ok = price > ind["ema200"]
                        rsi_ok = ind["rsi14"] < RSI_BUY_THRESHOLD
                        volume_ok = ind["vol_ratio"] < VOLUME_SPIKE_RATIO

                        if (
                            dip >= DIP_THRESHOLD
                            and cooldown_ok
                            and position_ok
                            and usdt_balance >= TRADE_AMOUNT_USDT
                        ):
                            if not btc_uptrend:
                                log.info(
                                    "SKIP %s — BTC below 200 EMA (bear market)", coin
                                )
                            elif not trend_ok:
                                log.info(
                                    "SKIP %s — price below 200 EMA (downtrend) | EMA=%.2f price=%.2f",
                                    coin,
                                    ind["ema200"],
                                    price,
                                )
                            elif not rsi_ok:
                                log.info(
                                    "SKIP %s — RSI %.1f not oversold (>%d)",
                                    coin,
                                    ind["rsi14"],
                                    RSI_BUY_THRESHOLD,
                                )
                            elif not volume_ok:
                                log.info(
                                    "SKIP %s — volume spike %.1fx avg (possible dump)",
                                    coin,
                                    ind["vol_ratio"],
                                )
                            else:
                                order = buy_market(client, coin, TRADE_AMOUNT_USDT)
                                filled_qty = float(order["executedQty"])
                                filled_price = (
                                    float(order["cummulativeQuoteQty"]) / filled_qty
                                )

                                if data["qty"] > 0:
                                    total_cost = (
                                        data["avg_buy"] * data["qty"]
                                        + TRADE_AMOUNT_USDT
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
                                    f"Price:     ${filled_price:,.4f}\n"
                                    f"Spent:     ${TRADE_AMOUNT_USDT}\n"
                                    f"Dip:       -{dip * 100:.2f}% from 24h high\n"
                                    f"RSI:       {ind['rsi14']:.1f}\n"
                                    f"EMA200:    ${ind['ema200']:,.2f}\n"
                                    f"Position:  ${data['avg_buy'] * data['qty']:.2f} / ${MAX_POSITION_USDT}\n"
                                    f"Day spend: ${state['daily_spend']['amount']:.2f} / ${MAX_DAILY_SPEND}\n"
                                    f"USDT left: ${usdt_balance:.2f}"
                                )
                                log.info(
                                    "BUY  %s @ %.4f | dip=%.2f%% rsi=%.1f ema=%.2f",
                                    coin,
                                    filled_price,
                                    dip * 100,
                                    ind["rsi14"],
                                    ind["ema200"],
                                )

                except BinanceAPIException as e:
                    log.error("Binance API error [%s]: %s", coin, e)
                except Exception as e:
                    log.error("Unexpected error [%s]: %s", coin, e)

            db.save_state(state)
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


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _get_cached_indicators(
    client: Client,
    coin: str,
    cache: dict,
    now: datetime,
) -> dict | None:
    """Return indicators from cache if fresh, otherwise fetch and cache."""
    cached = cache.get(coin)
    if cached:
        age = (now - cached["cached_at"]).total_seconds()
        if age < INDICATOR_TTL_SECS:
            return cached
    try:
        ind = get_indicators(client, coin)
        ind["cached_at"] = now
        cache[coin] = ind
        return ind
    except Exception as e:
        log.error("Failed to get indicators for %s: %s", coin, e)
        return cached  # return stale data rather than nothing


def _clear_position(data: dict, filled_sell_qty: float, coin: str):
    """Zero out position after a sell, warn if partially filled."""
    remaining = data["qty"] - filled_sell_qty
    if data["qty"] == 0 or remaining / data["qty"] < 0.001:
        data["qty"] = 0.0
        data["avg_buy"] = 0.0
    else:
        data["qty"] = remaining
        log.warning("Partial sell %s: %.6f remaining", coin, remaining)


if __name__ == "__main__":
    run()
