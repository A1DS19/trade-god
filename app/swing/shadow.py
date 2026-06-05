"""Shadow tracker for RSI-gate-blocked would-be trades (observe-only diagnostic).

When the hard RSI entry gate blocks a setup that WOULD have cleared confidence
(would_be_conf >= MIN_CONFIDENCE), we record a counterfactual "would-be" trade and
follow its price forward, logging the would-be PnL each cycle:

  positive  -> the blocked trade would have PROFITED (the gate forwent a winner)
  negative  -> the blocked trade would have LOST    (the gate avoided a loser)

This NEVER touches a real position — it only emits log lines. State is in-memory and
resets on restart; the emitted SHADOW / SHADOW-CLOSE log lines are the durable record.
Grep `SHADOW-CLOSE` and sum the percentages to see whether the gate is net helping.
"""

from __future__ import annotations


def would_be_pnl_pct(direction: str, entry_price: float, current_price: float) -> float:
    """Counterfactual PnL fraction of a would-be trade. A short profits as price falls."""
    if direction == "short":
        return (entry_price - current_price) / entry_price
    return (current_price - entry_price) / entry_price


class ShadowTracker:
    """In-memory tracker of gate-blocked would-be trades, keyed by coin.

    Call observe(coin, price, gate_block, min_conf) once per coin per cycle. It opens a
    shadow when the gate blocks a would-be trade, updates it while the block persists,
    and closes it (logging the final would-be PnL) when the coin is no longer gate-blocked
    or after max_cycles. Returns the log lines to emit.
    """

    def __init__(self, max_cycles: int = 8) -> None:
        self.max_cycles = max_cycles
        self._open: dict[str, dict] = {}

    def observe(self, coin: str, price: float, gate_block: dict | None, min_conf: float) -> list[str]:
        is_block = gate_block is not None and gate_block.get("would_be_conf", 0.0) >= min_conf
        rec = self._open.get(coin)

        if rec is not None:
            rec["cycles"] += 1
            pnl = would_be_pnl_pct(rec["direction"], rec["entry_price"], price)
            same_block = is_block and gate_block["direction"] == rec["direction"]
            if not same_block or rec["cycles"] >= self.max_cycles:
                del self._open[coin]
                why = "max age" if same_block else "un-gated"
                return [
                    f"SHADOW-CLOSE {coin} {rec['direction']} would-be {pnl * 100:+.2f}% "
                    f"over {rec['cycles']}h ({why}; entry@{rec['entry_price']:.6g} -> {price:.6g})"
                ]
            return [
                f"SHADOW {coin} {rec['direction']} would-be {pnl * 100:+.2f}% "
                f"({rec['cycles']}h, entry@{rec['entry_price']:.6g})"
            ]

        if is_block:
            self._open[coin] = {
                "direction": gate_block["direction"],
                "entry_price": price,
                "entry_rsi": gate_block.get("rsi"),
                "would_be_conf": gate_block.get("would_be_conf"),
                "cycles": 0,
            }
            return [
                f"SHADOW-OPEN {coin} {gate_block['direction']} would-be entry @ {price:.6g} "
                f"(RSI {gate_block.get('rsi'):.1f}, conf {gate_block.get('would_be_conf'):.2f})"
            ]

        return []
