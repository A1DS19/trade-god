"""Live (agent.decide) vs backtest (strategy.decide_v2) decision parity.

Both consume the SAME snapshot schema and are meant to encode the SAME v2 strategy
— but they are SEPARATE implementations. That duplication is what let the backtest's
MIN_CONFIDENCE silently drift to 0.85 while live ran 0.80. This differential test
fails the moment the two disagree, so any future drift is caught immediately — and
it's the safety net for the eventual unification into one strategy core (scope C).
"""

from __future__ import annotations

import pytest

from app.swing import agent
from app.swing.backtest_replay import strategy

# No-position snapshots: ranging / blocked / valid-low-conf / strong setups.
ENTRY_SCENARIOS = {
    "ranging":        dict(regime="ranging", adx=18.0),
    "blocked_mixed":  dict(),
    "short_lowconf":  dict(ema_alignment="bearish", daily_ema_alignment="bearish",
                           adx=33.0, plus_di=12.0, minus_di=28.0, macd_hist=-0.0005, rsi=45.0),
    "long_lowconf":   dict(ema_alignment="bullish", daily_ema_alignment="bullish",
                           adx=33.0, plus_di=28.0, minus_di=12.0, macd_hist=0.0005, rsi=50.0),
    "short_strong":   dict(ema_alignment="bearish", daily_ema_alignment="bearish",
                           adx=40.0, plus_di=6.0, minus_di=35.0, macd_hist=-0.002, rsi=45.0),
    "short_rsi_gated": dict(ema_alignment="bearish", daily_ema_alignment="bearish",
                            adx=40.0, plus_di=6.0, minus_di=35.0, macd_hist=-0.002, rsi=18.0),
}


@pytest.mark.parametrize("name", list(ENTRY_SCENARIOS))
def test_entry_decision_parity(snapshot, name):
    s = snapshot(**ENTRY_SCENARIOS[name])
    live, v2 = agent.decide(s), strategy.decide_v2(s)
    assert live["action"] == v2["action"], name
    assert live["confidence"] == pytest.approx(v2["confidence"]), name


# With an open position both run the (duplicated) exit checks. Hold-confidence
# intentionally differs (the backtest returns a fixed 0.7 for a valid hold), so
# only the ACTION must match here.
POSITION_SCENARIOS = {
    "long_overbought_exit": ("long",  dict(ema_alignment="bullish", daily_ema_alignment="bullish", rsi=75.0)),
    "long_healthy_hold":    ("long",  dict(ema_alignment="bullish", daily_ema_alignment="bullish", rsi=55.0)),
    "short_oversold_exit":  ("short", dict(ema_alignment="bearish", daily_ema_alignment="bearish", rsi=25.0)),
    "short_healthy_hold":   ("short", dict(ema_alignment="bearish", daily_ema_alignment="bearish", rsi=50.0)),
}


@pytest.mark.parametrize("name", list(POSITION_SCENARIOS))
def test_exit_decision_parity(snapshot, name):
    side, kw = POSITION_SCENARIOS[name]
    s = snapshot(**kw)
    # Enter in profit so the small-loss soft-exit guard doesn't mask a real exit.
    entry = s["price"] * (0.9 if side == "long" else 1.1)
    s["open_position"] = {"side": side, "entry": entry, "qty": 1.0, "notional": 1.0}
    live, v2 = agent.decide(s), strategy.decide_v2(s)
    assert live["action"] == v2["action"], name
