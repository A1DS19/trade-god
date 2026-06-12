"""Signal-research library: warehouse loading, cost model, event studies, backtest engine.

All signal work imports this; nothing else computes PnL.
"""

from research.siglib.backtest import BacktestResult, run_backtest
from research.siglib.costs import CostModel
from research.siglib.data import (
    eligible_mask,
    load_funding,
    load_klines,
    load_premium,
    to_panel,
)
from research.siglib.events import event_study

__all__ = [
    "BacktestResult",
    "CostModel",
    "eligible_mask",
    "event_study",
    "load_funding",
    "load_klines",
    "load_premium",
    "run_backtest",
    "to_panel",
]
