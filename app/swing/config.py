"""Swing agent configuration — strategy constants and swing-specific env vars."""

import os
from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # shared credentials

# ── Swing-specific credentials ────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY_FUTURES"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY_FUTURES"]
NVIDIA_API_KEY     = os.environ["NVIDIA_API_KEY"]

# ── NVIDIA ────────────────────────────────────────────────
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL    = "meta/llama-3.3-70b-instruct"

# ── Coins to watch ────────────────────────────────────────
COINS = ["ETH", "SOL", "BNB", "XRP"]

# ── Risk / sizing ─────────────────────────────────────────
LEVERAGE       = 5      # Default futures leverage
POSITION_USDT  = 5.0    # USDT per trade (notional / leverage = margin used)
MAX_OPEN       = 3      # Max simultaneous open positions
DEFAULT_SL_PCT = 0.03   # 3% stop loss from entry
DEFAULT_TP_PCT = 0.08   # 8% take profit from entry
MIN_CONFIDENCE = 0.70   # Skip trade if agent confidence < this

# ── Loop ──────────────────────────────────────────────────
CHECK_INTERVAL = 3600   # Seconds between scans (1 hour)
