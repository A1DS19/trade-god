"""Transaction-cost model. Baseline: taker 5 bps + slippage 5 bps per side."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    taker_bps: float = 5.0
    slippage_bps: float = 5.0

    @property
    def cost_per_side(self) -> float:
        """Fraction of notional charged per side (per unit of turnover)."""
        return (self.taker_bps + self.slippage_bps) / 10_000.0


# Pre-registered stress variant: slippage doubled to 10 bps/side.
STRESS = CostModel(taker_bps=5.0, slippage_bps=10.0)
