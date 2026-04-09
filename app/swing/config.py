"""Swing agent configuration — strategy constants and swing-specific env vars."""

import os
from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # shared credentials

# ── Swing-specific credentials ────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY_FUTURES"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY_FUTURES"]
# ── Coins to watch ────────────────────────────────────────
COINS = ["SOL", "BNB", "DOGE", "LINK", "SUI"]  # BTC/ETH/AVAX/XRP removed: drag on EMA/ADX framework over 5-year data; DOGE/LINK/SOL carry the edge

# ── Risk / sizing ─────────────────────────────────────────
LEVERAGE       = 5      # Default futures leverage
POSITION_USDT_MIN = 5.0   # Minimum USDT per trade
POSITION_USDT_MAX = 10.0  # Maximum USDT per trade (used for high-confidence setups)
POSITION_USDT = POSITION_USDT_MIN  # Backward-compatible base size
CONFIDENCE_SIZING_CAP = 0.95  # Confidence mapped to max size at/above this value
MAX_OPEN       = 3      # Max simultaneous open positions
DEFAULT_SL_PCT = 0.03   # 3% stop loss from entry
DEFAULT_TP_PCT = 0.08   # 8% take profit from entry
MIN_CONFIDENCE  = 0.80  # Skip trade if agent confidence < this
MIN_RSI_SHORT   = 42.0  # Don't short if RSI already approaching oversold
MAX_RSI_LONG    = 58.0  # Don't long if RSI already approaching overbought
MIN_ADX_ENTRY   = 32.0  # Require stronger trend for entries (raised from 25: grid search showed PF 1.93 vs 1.20, DD $7 vs $15)
BORDERLINE_ADX_PENALTY = 0.08  # Confidence score penalty in borderline ADX regime
PARTIAL_MIN_ADX = 32.0  # Allow mixed/partial entries only in stronger trends
PARTIAL_MIN_CONFIDENCE = 0.80  # Require extra conviction for partial entries
ENABLE_PARTIAL_ENTRIES = False  # v2.1: disable partial entries for quality-first filtering
REQUIRE_DI_ALIGNMENT = True  # v2.2: require directional DI alignment at entry
EST_FEE_BPS = 4.0  # Estimated exchange fee per side (bps) for entry filtering
EST_SLIPPAGE_BPS = 2.0  # Estimated adverse slippage per side (bps) for entry filtering
MIN_TP_TO_COST_MULT = 3.0  # Require TP to be at least this multiple of round-trip costs
MIN_NET_TP_PCT = 0.004  # Require TP - est round-trip costs >= 0.4%
SHORT_EXIT_RSI_FLOOR = 32.0       # Exit short only if RSI gets very deeply oversold
LONG_EXIT_RSI_CEIL = 68.0         # Exit long only if RSI gets very deeply overbought
MACD_DIV_EXIT_RSI_SHORT = 32.0   # MACD divergence exit for shorts: RSI must be this low — lowered from 38, grid search showed 32 prevents premature exits on healthy shorts
MACD_DIV_EXIT_RSI_LONG = 68.0    # MACD divergence exit for longs: RSI must be this high (raised from 62: 62 fires on consolidation, 68 aligns with deep-overbought threshold)
SOFT_EXIT_MAX_LOSS_PCT = 0.020   # Delay soft exits while unrealized loss is small (<2.0%)

# ── Loop ──────────────────────────────────────────────────
CHECK_INTERVAL    = 3600  # Seconds between scans (1 hour)
LOSS_COOLDOWN_HRS = 4     # Hours to skip a coin after a losing trade
