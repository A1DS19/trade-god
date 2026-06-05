"""Unit tests for app.swing.agent.decide() HOLD gates.

Pins behavior observed in the 2026-04-10 logs where every coin held because
ADX < MIN_ADX_ENTRY, daily EMA was mixed/bearish, or +DI dominated (blocking
shorts). If any gate is loosened, these tests fail loudly so the change is
intentional. The `snapshot` factory lives in tests/conftest.py.
"""

from __future__ import annotations

from app.swing import agent, config


def test_adx_below_20_returns_ranging_hold(snapshot) -> None:
    """1000SHIB-style row: regime=ranging short-circuits before entry checks."""
    result = agent.decide(snapshot(coin="1000SHIB", regime="ranging", adx=18.0))

    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    assert result["reasoning"] == "ADX < 20 — ranging market, no entry"


def test_adx_below_min_entry_blocks_short_with_bearish_daily(snapshot) -> None:
    """RUNE-style row: daily bearish + MACD>=0 + ADX<gate + +DI>-DI.

    Long blocked by daily=bearish. Short blocked by MACD>=0 + ADX + DI.
    """
    result = agent.decide(
        snapshot(
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


def test_adx_gate_blocks_short_when_daily_mixed(snapshot) -> None:
    """DOGE row from the 22:38 cycle — exact fingerprint from the logs."""
    result = agent.decide(
        snapshot(
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


def test_daily_bearish_blocks_long_even_when_4h_bullish(snapshot) -> None:
    """Even with a clean bullish 4h stack + +DI>-DI + MACD>0, a bearish daily
    must block longs. Guards against accidentally dropping the daily filter."""
    result = agent.decide(
        snapshot(
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


def test_di_alignment_blocks_short_when_plus_di_dominates(snapshot) -> None:
    """+DI dominant must block shorts even when daily is bearish and ADX is
    above the gate. This is the RUNE-during-recovery trap."""
    result = agent.decide(
        snapshot(
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


def test_entry_gate_passes_when_all_blockers_removed(snapshot) -> None:
    """Same DOGE snapshot but bearish daily + bearish 4h + MACD<0 + ADX>=gate +
    -DI>+DI. The hard entry gate should no longer block. Confidence may still be
    below threshold — we only assert the gate passed (no 'No entry' text)."""
    result = agent.decide(
        snapshot(
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

    reasoning = result["reasoning"]
    assert "No entry" not in reasoning
    assert "ADX < 20" not in reasoning
    if result["action"] == "hold":
        assert "Confidence" in reasoning  # confidence-gated, not hard-gated
    else:
        assert result["action"] == "short"


# ── RSI hard entry gate (added 2026-06-05 after trades 67/68/69) ────────────


def test_rsi_gate_blocks_short_when_deeply_oversold(snapshot):
    """A valid short stack but RSI below SHORT_ENTRY_RSI_FLOOR is hard-blocked —
    don't short into the bounce zone (trades 67/68/69 lost exactly this way)."""
    result = agent.decide(
        snapshot(
            ema_alignment="bearish", daily_ema_alignment="bearish",
            adx=40.0, plus_di=6.0, minus_di=35.0, macd_hist=-0.002, rsi=18.0,
        )
    )
    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    assert "short blocked" in result["reasoning"]


def test_rsi_gate_allows_short_above_floor(snapshot):
    """Same stack at RSI above the floor is NOT blocked by the RSI gate (it may
    still be confidence-gated, but the hard gate must let it through)."""
    result = agent.decide(
        snapshot(
            ema_alignment="bearish", daily_ema_alignment="bearish",
            adx=40.0, plus_di=6.0, minus_di=35.0, macd_hist=-0.002, rsi=40.0,
        )
    )
    assert "short blocked" not in result["reasoning"]


def test_rsi_gate_blocks_long_when_deeply_overbought(snapshot):
    result = agent.decide(
        snapshot(
            ema_alignment="bullish", daily_ema_alignment="bullish",
            adx=40.0, plus_di=35.0, minus_di=6.0, macd_hist=0.002, rsi=80.0,
        )
    )
    assert result["action"] == "hold"
    assert result["confidence"] == 0.0
    assert "long blocked" in result["reasoning"]
