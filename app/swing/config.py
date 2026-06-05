"""Swing agent configuration — strategy constants and swing-specific env vars."""

import os
from app.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  # shared credentials

# ── Swing-specific credentials ────────────────────────────
BINANCE_API_KEY    = os.environ["BINANCE_API_KEY_FUTURES"]
BINANCE_SECRET_KEY = os.environ["BINANCE_SECRET_KEY_FUTURES"]
# ── Coins to watch ────────────────────────────────────────
COINS = ["DOGE", "1000SHIB", "RUNE", "RENDER", "1000FLOKI", "TURBO", "IP", "BSV", "IOTA", "FET", "ENS", "TON", "HYPE"]
# ── Coin selection notes (2026-04-11) ────────────────────────────────────
# DOT removed 2026-04-11: at true live MIN_CONFIDENCE=0.80 it was net-negative
# over 5yr (−$0.89 / 29 trades / 10 SL totaling −$13.73). Was originally picked
# under a stale 0.85 backtest filter — see project_backtest_conf_drift_2026-04-11.md
#
# Walk-forward validation (2026-04-11):
#   - DOGE, IOTA: survived both walk-forward tests (train 21-23/24-26 and 21-24/25-26)
#   - BSV, RENDER: marginally passed or insufficient training data
#   - 1000SHIB, RUNE, 1000FLOKI, TURBO, IP: NOT in today's top-100 by mcap
#     — cannot be reproduced by the current --top --screen pipeline.
#     They were picked via a process we cannot reproduce (either a different
#     universe fetcher in April 2026 or manual selection). Transparency flag,
#     not a removal recommendation.
# See docs/swing_strategy_current.md §12 and project_walk_forward_2026-04-11.md
# for the full walk-forward analysis. Forward-looking ROI estimate: ~15-22%
# annual (NOT the 22.90% / 76.75% in-sample numbers).
#
# 2026-06-05 universe update — walk-forward validated (train 2024-06→2025-06 vs
# OOS test 2025-06→2026-06), from a top-100 re-screen:
#   +FET kept (robust: PF 7.27 / 75% win over 2yr).
#   +ENS, +TON added — the only NEW top-100 candidates positive in BOTH windows
#    (ENS +4.50/+3.98, TON +2.81/+6.13).
#   -ZEC removed — net-negative out-of-sample (+2.54→−0.37, PF 0.97) and the
#    worst drawdown in the top-100 (max_dd 10.90).
#   HYPE: failed walk-forward (no train data, onboarded 2025-05-30; −0.31 OOS)
#    but RE-ADDED by explicit user request 2026-06-05 — weakest coin in the book,
#    watch it / re-evaluate once it has 2yr of history.
#   Rejected despite top 2yr PnL: VET/INJ/TIA/WLD/JASMY — all overfit, NEGATIVE
#    out-of-sample (e.g. VET +15.48 train → −1.08 test). Walk-forward caught them.

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
SHORT_ENTRY_RSI_FLOOR = 32.0  # HARD gate: block shorts when RSI < this — don't short into the exit/bounce zone (mirrors SHORT_EXIT_RSI_FLOOR)
LONG_ENTRY_RSI_CEIL   = 68.0  # HARD gate: block longs when RSI > this (mirrors LONG_EXIT_RSI_CEIL)
MIN_ADX_ENTRY   = 28.0  # Lowered from 32 (2026-04-15): WF grid search validated — OOS PF 1.87-3.52, ROI 73-151% across both splits. adx=28/conf=0.80 beat adx=30/0.85 on total OOS PnL with 2x more trades.
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
