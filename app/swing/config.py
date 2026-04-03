"""Swing agent configuration — strategy constants and swing-specific env vars."""

import os
from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # shared credentials

# ── Swing-specific credentials ────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY_FUTURES"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY_FUTURES"]
# ── Coins to watch ────────────────────────────────────────
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "SUI"]

# ── Risk / sizing ─────────────────────────────────────────
LEVERAGE       = 5      # Default futures leverage
POSITION_USDT  = 5.0    # USDT per trade (notional / leverage = margin used)
MAX_OPEN       = 3      # Max simultaneous open positions
DEFAULT_SL_PCT = 0.03   # 3% stop loss from entry
DEFAULT_TP_PCT = 0.08   # 8% take profit from entry
MIN_CONFIDENCE  = 0.70  # Skip trade if agent confidence < this
MIN_RSI_SHORT   = 42.0  # Don't short if RSI already approaching oversold
MAX_RSI_LONG    = 58.0  # Don't long if RSI already approaching overbought
SHORT_EXIT_RSI_FLOOR = 32.0  # Exit short only if RSI gets very deeply oversold
LONG_EXIT_RSI_CEIL = 68.0    # Exit long only if RSI gets very deeply overbought
SOFT_EXIT_MAX_LOSS_PCT = 0.020  # Delay soft exits while unrealized loss is small (<2.0%)

# ── Loop ──────────────────────────────────────────────────
CHECK_INTERVAL    = 3600  # Seconds between scans (1 hour)
LOSS_COOLDOWN_HRS = 4     # Hours to skip a coin after a losing trade
