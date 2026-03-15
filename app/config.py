"""
Central configuration — all env vars and strategy constants live here.
Import from this module instead of reading os.environ directly.
"""

import os
import logging

# ── Credentials ───────────────────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# ── Coin universe ─────────────────────────────────────────
TOP_N_COINS = 20  # How many coins to watch (by market cap)

COIN_BLACKLIST = {
    # Stablecoins — pegged to $1, no DCA upside
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDE", "USD1", "USDP",
    # Wrapped / synthetic — duplicates of coins already on the list
    "WBTC", "WBETH", "WBNB", "BETH", "PAXG", "XAUT",
    # WLFI — 78% of supply held by top 10 wallets, extreme whale dump risk
    # ZEC  — privacy coin with active exchange delisting risk
    "WLFI", "ZEC",
}

# ── Strategy ──────────────────────────────────────────────
TRADE_AMOUNT_USDT = 8.0   # $ spent per buy order
MAX_POSITION_USDT = 50.0  # Max total cost basis per coin
MAX_DAILY_SPEND   = 80.0  # Max USDT to spend per UTC day
DIP_THRESHOLD     = 0.03  # Buy when price dips 3% from 24h high
TAKE_PROFIT       = 0.05  # Sell when position is up +5%
STOP_LOSS         = 0.15  # Sell when position is down -15%
BUY_COOLDOWN_HRS  = 4     # Min hours between buys for same coin
CHECK_INTERVAL    = 300   # Seconds between market checks (5 min)
DAILY_REPORT_HOUR = 8     # UTC hour to send daily summary

# ── Quant filters ─────────────────────────────────────────
RSI_BUY_THRESHOLD  = 45    # Only buy when RSI(14) is below this
VOLUME_SPIKE_RATIO = 2.0   # Skip if today's volume > N × 20-day average
INDICATOR_TTL_SECS = 3600  # Cache daily indicators for 1 hour

# ── Logging ───────────────────────────────────────────────
LOG_FILE = "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
