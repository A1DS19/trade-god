"""Call Nemotron to get a trading decision for a given snapshot."""

import json
import logging
from openai import OpenAI
from app.swing import config

log = logging.getLogger(__name__)

_client = OpenAI(
    api_key=config.NVIDIA_API_KEY,
    base_url=config.NVIDIA_BASE_URL,
)

SYSTEM_PROMPT = """You are an expert crypto swing trader focused on USDT-M perpetual futures.
Your job is to analyze market snapshots and return a single trading decision.

Rules:
- Timeframe: 4h charts, swing trades lasting hours to a few days
- You can go long, short, close an existing position, or hold
- Only trade with high conviction — if unsure, return hold
- Consider EMA alignment, RSI, volume, funding rate, and recent candle structure
- High positive funding rate (>0.05%) favors shorts; high negative favors longs
- RSI >70 = overbought (favor short/close long); RSI <30 = oversold (favor long/close short)
- Price above EMA9 > EMA21 > EMA50 = bullish structure; below = bearish

Confidence scoring — be precise, not round:
- 0.90–1.00: Multiple strong signals aligned (e.g. RSI oversold + EMA bullish stack + high volume + negative funding)
- 0.80–0.89: 3 clear signals aligned, no major contradictions
- 0.70–0.79: 2 signals aligned, setup is reasonable but not ideal
- 0.60–0.69: Mixed signals, lean in one direction but weak
- 0.00–0.59: Unclear — return hold
Never return exactly 0.70 unless the setup precisely matches that tier. Use decimals like 0.73, 0.81, 0.94.

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
- "long"/"short" means add or flip (only suggest if very high confidence)
- "close" means exit the current position
- "hold" means keep current position"""


def decide(snapshot: dict) -> dict:
    user_msg = json.dumps(snapshot, indent=2)
    try:
        response = _client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=256,
        )
        raw = response.choices[0].message.content.strip()
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
