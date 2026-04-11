"""Unit tests for app.swing.agent.decide() HOLD gates.

Pins behavior observed in the 2026-04-10 logs where every coin held because
ADX < 32, daily EMA was mixed/bearish, or +DI dominated (blocking shorts).
If any gate is loosened, these tests fail loudly so the change is intentional.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Agent transitively imports app.config which requires these env vars at import
# time. Set them before the import so tests run without a real .env.
os.environ.setdefault("BINANCE_API_KEY", "test")
os.environ.setdefault("BINANCE_SECRET_KEY", "test")
os.environ.setdefault("BINANCE_API_KEY_FUTURES", "test")
os.environ.setdefault("BINANCE_SECRET_KEY_FUTURES", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.swing import agent, config  # noqa: E402


def _snap(
    *,
    coin: str = "DOGE",
    price: float = 0.30,
    regime: str = "trending",
    ema_alignment: str = "mixed",
    daily_ema_alignment: str = "mixed",
    adx: float = 25.5,
    plus_di: float = 29.0,
    minus_di: float = 11.4,
    macd_hist: float = 0.0001,
    macd_hist_prev: float = 0.0,
    rsi: float = 50.0,
) -> dict:
    """Minimal snapshot good enough for decide() with a no-position coin.

    Defaults mirror the DOGE row from the 22:38 cycle in the logs."""
    return {
        "coin": coin,
        "price": price,
        "market_regime": regime,
        "indicators": {
            "ema_alignment": ema_alignment,
            "daily_ema_alignment": daily_ema_alignment,
            "ema9": price,
            "ema21": price,
            "ema50": price,
            "ema200_daily": price,
            "rsi14_4h": rsi,
            "vol_ratio": 1.0,
            "price_vs_ema9": 0.0,
            "price_vs_ema21": 0.0,
            "price_vs_ema200": 0.0,
            "adx14": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "macd_hist": macd_hist,
            "macd_hist_prev": macd_hist_prev,
            "oi_change_4h_pct": 0.0,
            "stoch_rsi_k": 50.0,
            "stoch_rsi_d": 50.0,
            "atr_pct_rank": 50.0,
            "vwap": price,
            "price_vs_vwap": 0.0,
            "ls_ratio": 1.0,
            "taker_ratio": 1.0,
        },
        "funding_rate_pct": 0.0,
        "suggested_sl_pct": 0.015,
        "suggested_tp_pct": 0.030,
        "open_position": None,
    }


# ── Gate tests ─────────────────────────────────────────────────────────────


def test_adx_below_20_returns_ranging_hold() -> None:
    """1000SHIB-style row: regime=ranging short-circuits before entry checks."""
    result = agent.decide(_snap(coin="1000SHIB", regime="ranging", adx=18.0))

    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    assert result["reasoning"] == "ADX < 20 — ranging market, no entry"


def test_adx_below_min_entry_blocks_short_with_bearish_daily() -> None:
    """RUNE-style row: daily bearish + MACD>=0 + ADX<32 + +DI>-DI.

    Long blocked by daily=bearish. Short blocked by MACD>=0 + ADX + DI.
    """
    result = agent.decide(
        _snap(
            coin="RUNE",
            daily_ema_alignment="bearish",
            adx=22.1,
            plus_di=24.2,
            minus_di=11.5,
            macd_hist=0.0004,
        )
    )

    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    assert "No entry" in result["reasoning"]
    assert f"ADX=22.1<{int(config.MIN_ADX_ENTRY)}" in result["reasoning"]
    assert "-DI=11.5<=+DI=24.2" in result["reasoning"]
    assert "long: daily=bearish" in result["reasoning"]


def test_adx_gate_blocks_short_when_daily_mixed() -> None:
    """DOGE row from the 22:38 cycle — exact fingerprint from the logs."""
    result = agent.decide(
        _snap(
            coin="DOGE",
            daily_ema_alignment="mixed",
            adx=25.5,
            plus_di=29.0,
            minus_di=11.4,
            macd_hist=0.0001,
        )
    )

    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    reason = result["reasoning"]
    assert "short: daily=mixed" in reason
    assert "MACD hist=0.0001>=0" in reason
    assert f"ADX=25.5<{int(config.MIN_ADX_ENTRY)}" in reason
    assert "-DI=11.4<=+DI=29.0" in reason
    assert "long: daily=mixed" in reason


def test_daily_bearish_blocks_long_even_when_4h_bullish() -> None:
    """Even with a clean bullish 4h stack + +DI>−DI + MACD>0, a bearish daily
    must block longs. Guards against accidentally dropping the daily filter."""
    result = agent.decide(
        _snap(
            coin="DOT",
            ema_alignment="bullish",
            daily_ema_alignment="bearish",
            adx=34.0,  # above MIN_ADX_ENTRY so ADX isn't the blocker
            plus_di=30.0,
            minus_di=12.0,
            macd_hist=0.005,
            macd_hist_prev=0.002,
        )
    )

    assert result["action"] == "hold"
    assert "long: daily=bearish" in result["reasoning"]


def test_di_alignment_blocks_short_when_plus_di_dominates() -> None:
    """+DI dominant must block shorts even when daily is bearish and ADX is
    above the gate. This is the RUNE-during-recovery trap."""
    result = agent.decide(
        _snap(
            coin="RUNE",
            ema_alignment="bearish",
            daily_ema_alignment="bearish",
            adx=34.0,
            plus_di=28.0,
            minus_di=12.0,
            macd_hist=-0.001,
            macd_hist_prev=0.0,
        )
    )

    assert result["action"] == "hold"
    assert "-DI=12.0<=+DI=28.0" in result["reasoning"]


# ── Inverse / unlock test ──────────────────────────────────────────────────


def test_entry_gate_passes_when_all_blockers_removed() -> None:
    """Same DOGE snapshot but bearish daily + bearish 4h + MACD<0 + ADX>=32 +
    -DI>+DI. The hard entry gate should no longer block. Confidence may still
    be below threshold — we only assert the gate passed (no 'No entry' text)."""
    result = agent.decide(
        _snap(
            coin="DOGE",
            ema_alignment="bearish",
            daily_ema_alignment="bearish",
            adx=33.0,
            plus_di=12.0,
            minus_di=28.0,
            macd_hist=-0.0005,
            macd_hist_prev=0.0,
            rsi=45.0,
        )
    )

    # Either the entry fired, or confidence gated it — but NOT the hard gates.
    reasoning = result["reasoning"]
    assert "No entry" not in reasoning
    assert "ADX < 20" not in reasoning
    if result["action"] == "hold":
        # Must be confidence-based, not hard-gated
        assert "Confidence" in reasoning
    else:
        assert result["action"] == "short"
