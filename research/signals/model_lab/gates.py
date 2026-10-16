"""The verdict's gates (spec 2026-10-02 §3.3–3.4). Phase 3 needs only the stop rule.

Every input is a book's daily net returns, indexed by bar open_time like BacktestResult.returns."""

from __future__ import annotations

import pandas as pd

from research.siglib.stats import max_drawdown, sharpe, weekly_returns


def stop_rule(arm: pd.Series, btc: pd.Series) -> dict[str, bool]:
    """G1 and G2 on the validation period (§3.4): a higher Sharpe of weekly returns than BTC's,
    and a daily drawdown no deeper. A book with no Sharpe ratio fails G1."""
    return {"G1": sharpe(weekly_returns(arm)) > sharpe(weekly_returns(btc)),
            "G2": max_drawdown(arm) <= max_drawdown(btc)}
