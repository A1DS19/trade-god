"""Call Claude to get a trading decision for a given snapshot."""

import json
import logging
import anthropic
from app.swing import config

log = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a quantitative crypto swing trader. Given a market snapshot, return a JSON trading decision.

## Regime gate
If market_regime == "ranging": action=hold. If "borderline": require 3+ confirming signals.

## Allowed direction (daily bias)
daily_ema_alignment "bearish" → short only, close any open long.
daily_ema_alignment "bullish" → long only, close any open short.
daily_ema_alignment "mixed" → no new entries; close if 4h is also mixed.

## New entry (all 5 required)
SHORT: market_regime trending + daily bearish + 4h ema_alignment bearish + macd_hist < 0 + adx14 > 25
LONG:  market_regime trending + daily bullish  + 4h ema_alignment bullish + macd_hist > 0 + adx14 > 25

## Confidence bands (after all 5 entry conditions met)
0.85–0.94: 3+ net confirming signals
0.75–0.84: 2 net confirming signals
0.70–0.74: 1 net confirming signal
< 0.70: hold

Confirming (+0.03–0.05 each): vol_ratio > 1.5, funding aligns, oi_change_4h_pct > 1% with price moving in direction, RSI 40–60, price_vs_ema200 confirms, minus_di > plus_di for short (or reverse for long).
Contradicting (−0.04–0.06 each): RSI < 35 for short or > 65 for long, funding opposes, oi_change < −2%, macd_hist moving against position.

Use precise decimals (0.73, 0.82) — never exactly 0.70, 0.75, 0.80, 0.85, 0.90.

## Close an open position if ANY exit condition is met
Short exit: 4h alignment bullish/mixed OR daily bullish OR RSI < 38 OR (macd_hist > macd_hist_prev AND RSI < 45) OR oi_change_4h_pct < −3 while price falling OR adx14 < 20.
Long exit:  4h alignment bearish/mixed OR daily bearish OR RSI > 62 OR (macd_hist < macd_hist_prev AND RSI > 55) OR oi_change_4h_pct < −3 while price rising OR adx14 < 20.

## Hold open position only if
Direction agrees with both 4h and daily alignment AND no exit condition triggered AND adx14 >= 20 AND macd_hist confirms direction.

## SL/TP
Use suggested_sl_pct and suggested_tp_pct (ATR-based). Min R:R = 2.0. sl_pct min 0.01, tp_pct min 0.02. Set both to 0 for hold/close.

## Flip
Only flip (long↔short on existing position) if confidence >= 0.85 and both alignments have clearly reversed."""


def _extract_json(text: str) -> str:
    """Return the first JSON object from text, stripping fences or preamble."""
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    # Skip any preamble before the opening brace
    brace = text.find("{")
    if brace == -1:
        return ""
    return text[brace:]


def decide(snapshot: dict) -> dict:
    user_msg = json.dumps(snapshot, indent=2) + "\n\nRespond with only the JSON object, no other text."
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            temperature=0.1,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        if not raw:
            log.error("Agent empty response for %s (stop=%s)", snapshot["coin"], response.stop_reason)
            return _hold("empty response")
        raw = _extract_json(raw)
        if not raw:
            log.error("Agent no JSON found for %s — raw: %r", snapshot["coin"], response.content[0].text[:300])
            return _hold("no JSON in response")
        decision, _ = json.JSONDecoder().raw_decode(raw)
        # Normalise field aliases
        if "reason" in decision and "reasoning" not in decision:
            decision["reasoning"] = decision.pop("reason")
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
