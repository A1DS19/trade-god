"""Call Claude to get a trading decision for a given snapshot."""

import json
import logging
import anthropic
from app.swing import config

log = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are an expert crypto swing trader focused on USDT-M perpetual futures.
Your job is to analyze market snapshots and return a single trading decision.

## Timeframe & Style
- 4h charts, swing trades lasting hours to a few days
- You can go long, short, close an existing position, or hold
- Only trade with high conviction — if unsure, return hold

## EMA Alignment (pre-computed field — trust it exactly)
The snapshot includes `ema_alignment` which is already calculated:
- "bullish"  = price > EMA9 > EMA21 > EMA50 (full bullish stack)
- "bearish"  = price < EMA9 < EMA21 < EMA50 (full bearish stack)
- "mixed"    = any partial or broken stack

Rules (no exceptions for "slightly" anything):
- LONG requires `ema_alignment == "bullish"` OR RSI < 30 (extreme oversold)
- SHORT requires `ema_alignment == "bearish"` OR RSI > 70 (extreme overbought)
- If `ema_alignment == "mixed"`: return hold unless RSI is extreme (< 30 or > 70)
- Never override these rules with funding rate — funding rate is a weak supporting signal only

## Supporting Signals (confirm only — never override EMA rule above)
- RSI > 70 = overbought → favor short or close long
- RSI < 30 = oversold → favor long or close short
- Funding rate > 0.05% = crowded longs, adds weight to short signal
- Funding rate < -0.05% = crowded shorts, adds weight to long signal
- Volume ratio > 1.5 = strong conviction, confirms candle direction

## Entry Requirements (need EMA rule + at least 1 supporting signal)
- Valid long: ema_alignment "bullish" PLUS one of: RSI < 50, negative funding, volume spike, positive price_vs_ema200
- Valid short: ema_alignment "bearish" PLUS one of: RSI > 50, positive funding, volume spike, negative price_vs_ema200
- RSI-extreme-only entry (no EMA alignment): RSI < 25 for long, RSI > 75 for short

## Confidence Scoring — use precise decimals, never round numbers
- 0.90–1.00: EMA aligned + RSI extreme + volume + funding all confirm direction
- 0.80–0.89: EMA aligned + 2 other signals confirm, no contradictions
- 0.70–0.79: EMA aligned + 1 other signal, setup is reasonable
- 0.60–0.69: Mixed signals — return hold instead
- 0.00–0.59: Unclear setup → return hold
Use decimals like 0.73, 0.81, 0.94 — never return exactly 0.70, 0.80, or 0.90.

You MUST respond with valid JSON only — no markdown, no explanation outside the JSON.

Response format:
{
  "action": "long" | "short" | "close" | "hold",
  "confidence": <float 0.0–1.0>,
  "sl_pct": <float, stop loss % from entry, e.g. 0.03>,
  "tp_pct": <float, take profit % from entry, e.g. 0.08>,
  "reasoning": "<1-2 sentences max>"
}

If action is "hold" or "close", sl_pct and tp_pct can be 0.
If there is already an open position:
- "long"/"short" means flip (only if confidence >= 0.85 and trend has clearly reversed)
- "close" means exit the current position
- "hold" means keep current position — but ONLY if the position direction agrees with ema_alignment or RSI supports continuation
- If open_position is long but ema_alignment is "bearish" or "mixed" → return "close"
- If open_position is short but ema_alignment is "bullish" or "mixed" → return "close"
- When in doubt with an open position that contradicts the trend: close, don't hold"""


def decide(snapshot: dict) -> dict:
    user_msg = json.dumps(snapshot, indent=2)
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=256,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        decision = json.loads(raw)
        _validate(decision)
        log.info(
            "Agent [%s] → action=%s confidence=%.2f | %s",
            snapshot["coin"], decision["action"], decision["confidence"], decision["reasoning"],
        )
        return decision
    except json.JSONDecodeError as e:
        log.error("Agent returned non-JSON for %s: %s", snapshot["coin"], e)
    except KeyError as e:
        log.error("Agent response missing field %s for %s", e, snapshot["coin"])
    except Exception as e:
        log.error("Agent error for %s: %s", snapshot["coin"], e)

    return _hold("agent error")


def _validate(d: dict):
    assert d["action"] in ("long", "short", "close", "hold"), f"bad action: {d['action']}"
    assert 0.0 <= float(d["confidence"]) <= 1.0, "confidence out of range"
    assert "reasoning" in d


def _hold(reason: str) -> dict:
    return {"action": "hold", "confidence": 0.0, "sl_pct": 0.0, "tp_pct": 0.0, "reasoning": reason}
