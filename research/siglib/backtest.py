"""Backtest engine — the ONLY place PnL is computed.

EXACT SEMANTICS (the lookahead contract)
========================================
Index convention: panels are indexed by bar open_time; bar i's close occurs at
wall-clock open_time[i] + 1h (== open_time[i+1] on a contiguous hourly grid).

- Weights w[t] are DECIDED at bar t close and take effect at bar t+1 (next-bar):
      pnl[t+1] = sum_sym w[t] * (close[t+1]/close[t] - 1)
  so pnl[t+1] is recorded at index open_time[t+1] and covers the wall-clock
  interval (close[t], close[t+1]].

- Turnover uses PRE-DRIFT effective weights: w_effective[t-1] is the weight
  decided at t-1 (intra-bar drift of holdings is ignored). The cost of the
  change decided at t is charged at its execution bar t+1:
      cost[t+1] = sum_sym |w[t] - w[t-1]| * cost_model.cost_per_side
  with w[-1] = 0 (the initial entry is charged). A change decided on the FINAL
  bar never executes (no t+1) and incurs no cost, no trade count, no turnover.

- Funding: for each funding event at time F with rate r, the event is assigned
  to the bar whose holding interval (close[t], close[t+1]] contains F, and
      pnl[t+1] -= sum_sym w[t] * r
  i.e. LONGS PAY positive funding, shorts receive it (and vice versa for
  negative rates). Implementation: F is mapped to the bar whose holding
  interval contains it via searchsorted on open_time + bar (ms jitter in real
  funding_time lands events just past the hour, in the interval of the
  position entered at that hour's close; index gaps are owned by the first
  bar after the gap, so a position held into a gap keeps paying funding).

- NaN prices (unlisted / delisted / missing bar) force the decided weight to 0
  at that bar; a NaN return with a live position contributes 0 for that hour.
  An optional boolean `eligibility` panel (e.g. data.eligible_mask) also forces
  weights to 0 where False.

Lookahead pin (tested in tests/research/test_siglib_backtest.py): on a pure
random walk, the same-bar cheat w[t] = sign(ret[t]) earns ~zero through this
engine (it only ever applies to ret[t+1]), while the impossible future signal
w[t] = sign(ret[t+1]) earns hugely — proving the engine shifts exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.siglib.costs import CostModel
from research.siglib.data import to_ms

_TRADE_TOL = 1e-12


@dataclass
class BacktestResult:
    """Per-bar series (all indexed like the price panel) + summary metrics."""

    returns: pd.Series          # hourly portfolio returns NET of costs and funding
    gross_returns: pd.Series    # before costs/funding
    trade_costs: pd.Series      # turnover cost charged per bar
    funding_costs: pd.Series    # funding charged per bar (positive = paid)
    turnover_per_bar: pd.Series  # executed sum |dw| per bar
    trades_per_bar: pd.Series   # executed count of per-symbol weight changes

    @property
    def equity_curve(self) -> pd.Series:
        return (1.0 + self.returns).cumprod()

    @property
    def total_return(self) -> float:
        eq = self.equity_curve
        return float(eq.iloc[-1] - 1.0) if len(eq) else 0.0

    @property
    def profit_factor(self) -> float:
        """Gross wins / gross losses on hourly net pnl."""
        wins = float(self.returns[self.returns > 0].sum())
        losses = float(-self.returns[self.returns < 0].sum())
        if losses == 0.0:
            return float("inf") if wins > 0 else float("nan")
        return wins / losses

    @property
    def max_drawdown(self) -> float:
        """Max peak-to-trough drop on the equity curve, as a positive fraction."""
        eq = self.equity_curve
        if not len(eq):
            return 0.0
        return float((1.0 - eq / eq.cummax()).max())

    @property
    def n_trades(self) -> int:
        return int(self.trades_per_bar.sum())

    @property
    def turnover(self) -> float:
        return float(self.turnover_per_bar.sum())

    def window(self, start=None, end=None) -> "BacktestResult":
        """Slice to [start, end) (epoch ms or datetime-like); metrics recompute on the slice."""
        idx = self.returns.index
        mask = pd.Series(True, index=idx)
        start_ms, end_ms = to_ms(start), to_ms(end)
        if start_ms is not None:
            mask &= idx >= start_ms
        if end_ms is not None:
            mask &= idx < end_ms
        return BacktestResult(
            returns=self.returns[mask],
            gross_returns=self.gross_returns[mask],
            trade_costs=self.trade_costs[mask],
            funding_costs=self.funding_costs[mask],
            turnover_per_bar=self.turnover_per_bar[mask],
            trades_per_bar=self.trades_per_bar[mask],
        )

    def summary(self) -> dict:
        return {
            "total_return": self.total_return,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "n_trades": self.n_trades,
            "turnover": self.turnover,
            "total_trade_cost": float(self.trade_costs.sum()),
            "total_funding": float(self.funding_costs.sum()),
            "n_bars": int(len(self.returns)),
        }


def _assign_funding_bars(index_values: np.ndarray, funding_times: np.ndarray) -> np.ndarray:
    """Map each funding_time F to the bar position s whose holding interval
    (close[s-1], close[s]] contains F, where close[i] = open_time[i] + bar.

    Gap-robust: the first bar after an index gap owns the whole gap (a position
    held into a gap keeps paying funding on its live weight). Events at or
    before the first bar's close map to position 0 (harmless: w_applied[0] is
    always 0); events after the last bar's close get -1 (dropped — the final
    bar's decision never executes, so no weight is ever live there).
    """
    if len(index_values) < 2:
        return np.full(len(funding_times), -1, dtype=np.int64)
    bar_ms = int(np.min(np.diff(index_values)))
    pos = np.searchsorted(index_values, funding_times - bar_ms, side="left")
    pos[funding_times > index_values[-1] + bar_ms] = -1
    return pos


def run_backtest(
    prices_1h_panel: pd.DataFrame,
    target_weights_panel: pd.DataFrame,
    cost_model: CostModel,
    funding_long: pd.DataFrame | None = None,
    eligibility: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run the next-bar backtest. See module docstring for the exact semantics.

    prices_1h_panel: wide close prices (index=open_time ms, columns=symbol).
    target_weights_panel: wide decided weights, same orientation (reindexed and
        NaN-filled to 0 against the price panel). Gross exposure is the
        caller's responsibility (protocol: 1.0 split across open positions).
    funding_long: optional long frame [symbol, funding_time, funding_rate].
    eligibility: optional boolean panel (data.eligible_mask); False forces 0.
    """
    prices = prices_1h_panel
    if not (prices.index.is_monotonic_increasing and prices.index.is_unique):
        raise ValueError(
            "prices_1h_panel index must be strictly increasing open_time ms "
            "(sort_index() and drop duplicates first)"
        )
    w = (
        target_weights_panel.reindex(index=prices.index, columns=prices.columns)
        .astype(float)
        .fillna(0.0)
    )
    if eligibility is not None:
        elig = (
            eligibility.reindex(index=prices.index, columns=prices.columns)
            .fillna(False)
            .astype(bool)
        )
        w = w.where(elig, 0.0)
    w = w.where(prices.notna(), 0.0)  # cannot hold what has no price

    # pnl[t] = sum w[t-1] * (close[t]/close[t-1] - 1)
    ret = prices / prices.shift(1) - 1.0
    w_applied = w.shift(1).fillna(0.0)  # weight in effect during bar t
    gross = (w_applied * ret).fillna(0.0).sum(axis=1)

    # Decided change at t executes at t+1 (final-bar decisions fall off the end).
    dw = w - w.shift(1).fillna(0.0)
    dw_exec = dw.shift(1).fillna(0.0).abs()
    turnover_per_bar = dw_exec.sum(axis=1)
    trades_per_bar = (dw_exec > _TRADE_TOL).sum(axis=1)
    trade_costs = turnover_per_bar * cost_model.cost_per_side

    funding_costs = pd.Series(0.0, index=prices.index)
    if funding_long is not None and len(funding_long):
        f = funding_long[funding_long["symbol"].isin(prices.columns)]
        if len(f):
            idx_vals = prices.index.to_numpy()
            pos = _assign_funding_bars(idx_vals, f["funding_time"].to_numpy())
            col = prices.columns.get_indexer(f["symbol"])
            ok = pos >= 0
            amounts = (
                w_applied.to_numpy()[pos[ok], col[ok]]
                * f["funding_rate"].to_numpy()[ok]
            )
            acc = np.zeros(len(prices.index))
            np.add.at(acc, pos[ok], amounts)
            funding_costs = pd.Series(acc, index=prices.index)

    net = gross - trade_costs - funding_costs
    return BacktestResult(
        returns=net,
        gross_returns=gross,
        trade_costs=trade_costs,
        funding_costs=funding_costs,
        turnover_per_bar=turnover_per_bar,
        trades_per_bar=trades_per_bar,
    )
