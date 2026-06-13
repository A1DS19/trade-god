"""Faithful walk-forward OOS evaluation of the v2 swing strategy.

Reuses the parity-tested strategy VERBATIM:
  - app/swing/backtest_replay/strategy.py::decide_v2  (the live strategy)
  - app/swing/backtest_replay/engine.py::ReplayEngine (_precompute_coin / _run_coin
    inner loop / _handle_intrabar_sl_tp / ATR SL-TP sizing / fee+slippage model)

What this runner ADDS on top of the engine (without re-implementing strategy logic):
  1. Klines come from the local research warehouse (parquet) instead of the
     network — `_fetch_klines` is overridden to serve warehouse rows in the
     EXACT [open_time, open, high, low, close, volume, close_time, ...] list shape
     the engine already consumes (verified against parquet schema).
  2. REAL funding is fed into the confidence score: `_precompute_coin` is wrapped
     to stamp each 4h snapshot with `funding_rate_pct` = (funding fraction in
     effect at that bar) * 100 — matching live snapshot["funding_rate_pct"].
     OI / L-S / taker stay neutralized (0.0 / 1.0 / 1.0) — no point-in-time history.
  3. Funding ACCRUAL on PnL: after the engine produces trades, each trade is
     charged the sum of funding events inside [entry_time, exit_time) on its
     notional (longs pay positive funding). This is the cost-model funding leg.
  4. LONG-ONLY mode: a thin wrapper turns any `short` action from decide_v2 into
     a `hold`, mirroring the live `_direction_enabled` kill-switch (ENABLE_SHORTS
     =False). Exits are never gated (decide_v2 returns `close` regardless of side).

Two funding variants are run (real vs zero) so funding's total contribution
(confidence effect + accrual) is the difference between them.

APPROXIMATIONS (be honest):
  - OI / L-S / taker confidence bonuses are neutralized (no history) -> confidence
    runs slightly LOW vs live, so trade count is a conservative lower bound.
  - Per-coin isolation: MAX_OPEN=3 portfolio cap is NOT modeled (each coin trades
    independently); pooled returns assume every signal is takeable.
  - Confidence-scaled sizing ($5-$10 notional) is preserved per-trade, but with no
    portfolio cap the pooled "return %" is computed on summed per-trade notional
    (capital-at-risk weighting), not a fixed bankroll.
"""

from __future__ import annotations

import json
import os
import sys
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any

import duckdb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import app.swing.backtest_replay as bt_pkg  # noqa: E402
from app.swing.backtest_replay import engine as bt_engine  # noqa: E402
from app.swing.backtest_replay.engine import (  # noqa: E402
    ReplayEngine,
    Trade,
    _max_drawdown,
)
from app.swing.backtest_replay.strategy import (  # noqa: E402
    LEVERAGE,
    _position_size_usdt_v2,
)
from app.swing.backtest_replay import strategy as bt_strategy  # noqa: E402

WAREHOUSE = os.path.join(ROOT, "research", "warehouse")
OUT_JSON = os.path.join(ROOT, "research", "v2_eval", "results.json")

COINS = ["DOGE", "1000SHIB", "RUNE", "RENDER", "1000FLOKI", "TURBO", "IP",
         "BSV", "IOTA", "FET", "ENS", "TON", "HYPE"]

# Walk-forward OOS windows (UTC), [start, end)
WINDOWS = {
    "W1": ("2023-07-01", "2024-07-01"),
    "W2": ("2024-07-01", "2025-07-01"),
    "W3": ("2025-07-01", "2026-06-01"),
}
ELIGIBILITY_DAYS = 60  # need >=60d history before a window's OOS start to trade it

FEE_BPS = 5.0       # taker, per side
SLIP_BPS = 5.0      # slippage, per side (base)
STRESS_SLIP_BPS = 10.0

# Full replay span: pull from earliest warehouse data so EMA200/ADX are warm well
# before W1, then slice trades by entry_time into windows.
REPLAY_START = "2020-01-01"
REPLAY_END = "2026-06-01"


def _to_ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Warehouse data loading (cached per process)
# ---------------------------------------------------------------------------

_KLINE_COLS = ("open_time", "open", "high", "low", "close", "volume",
               "close_time", "quote_volume", "trades",
               "taker_buy_volume", "taker_buy_quote_volume")


def _load_klines(coin: str, dataset: str) -> list[list[Any]]:
    """Return warehouse klines in the engine's expected list-of-lists shape."""
    path = os.path.join(WAREHOUSE, dataset, f"{coin}USDT.parquet")
    df = duckdb.sql(
        f"SELECT {', '.join(_KLINE_COLS)} FROM '{path}' ORDER BY open_time"
    ).df()
    return df.values.tolist()


def _load_funding(coin: str) -> list[tuple[int, float]]:
    """Return [(funding_time_ms, funding_rate_fraction), ...] sorted ascending."""
    path = os.path.join(WAREHOUSE, "funding", f"{coin}USDT.parquet")
    df = duckdb.sql(
        f"SELECT funding_time, funding_rate FROM '{path}' ORDER BY funding_time"
    ).df()
    return list(zip(df["funding_time"].astype("int64").tolist(),
                    df["funding_rate"].astype(float).tolist()))


# ---------------------------------------------------------------------------
# Long-only wrapper for decide_v2 (mirrors live _direction_enabled)
# ---------------------------------------------------------------------------

def _make_long_only_decide(orig_decide):
    def _decide(snapshot):
        d = orig_decide(snapshot)
        # Drop SHORT *entries* only; exits ("close") and longs pass through.
        if d.get("action") == "short":
            return {"action": "hold", "confidence": 0.0, "reasoning": "short disabled (ENABLE_SHORTS=False)"}
        return d
    return _decide


# ---------------------------------------------------------------------------
# Warehouse-backed engine: same replay logic, warehouse klines + real funding
# ---------------------------------------------------------------------------

class WarehouseEngine(ReplayEngine):
    def __init__(self, *args, use_funding: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_funding = use_funding
        self._funding_cache: dict[str, list[tuple[int, float]]] = {}

    def _fetch_klines(self, client, symbol, interval, start_ms, end_ms):  # noqa: ARG002
        coin = symbol[:-4]  # strip trailing USDT
        from binance.client import Client as _C
        dataset = "klines_4h" if interval == _C.KLINE_INTERVAL_4HOUR else "klines_1d"
        rows = _load_klines(coin, dataset)
        # Match the engine's network fetch window semantics: keep bars whose
        # open_time is in [start_ms, end_ms]. (Engine passes a pre-padded start
        # for the daily series so EMA200 is warm.)
        return [r for r in rows if start_ms <= int(r[0]) <= end_ms]

    def _funding_for(self, coin: str) -> list[tuple[int, float]]:
        if coin not in self._funding_cache:
            self._funding_cache[coin] = _load_funding(coin)
        return self._funding_cache[coin]

    def _precompute_coin(self, kl4, kl1d):
        snaps = super()._precompute_coin(kl4, kl1d)
        if not self.use_funding:
            return snaps  # zero-funding variant: leave funding_rate_pct = 0.0
        # Stamp each snapshot with the funding rate IN EFFECT at the bar close.
        # _current_coin is set by the wrapped _run_coin below before this call.
        funding = self._funding_for(self._current_coin)
        ftimes = [f[0] for f in funding]
        for snap in snaps:
            if snap is None:
                continue
            ct = snap["close_time_ms"]
            idx = bisect_right(ftimes, ct) - 1  # last funding event with time <= bar close
            if idx >= 0:
                snap["funding_rate_pct"] = round(funding[idx][1] * 100, 4)
        return snaps

    def _run_coin(self, coin: str):
        # _precompute_coin needs to know which coin's funding to align.
        self._current_coin = coin
        return super()._run_coin(coin)


# ---------------------------------------------------------------------------
# Funding accrual on PnL (cost-model funding leg)
# ---------------------------------------------------------------------------

def _accrue_funding(trade: Trade, funding: list[tuple[int, float]],
                    ftimes: list[int]) -> float:
    """Funding paid by the position over its hold. Longs pay positive funding.

    Returns a signed USD adjustment to ADD to net pnl (negative = cost).
    Notional is reconstructed from the confidence-scaled sizing the engine used.
    """
    notional = _position_size_usdt_v2(trade.confidence) * LEVERAGE
    lo = bisect_right(ftimes, trade.entry_time)       # funding strictly after entry
    hi = bisect_right(ftimes, trade.exit_time)        # up to and including exit bar
    total_rate = sum(funding[i][1] for i in range(lo, hi))
    sign = -1.0 if trade.side == "long" else 1.0      # long pays positive funding
    return sign * total_rate * notional


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class TradeRec:
    coin: str
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    notional: float
    net_pnl: float          # engine pnl + funding accrual
    base_pnl: float         # engine pnl (no funding accrual)
    funding_usd: float
    confidence: float
    hold_hours: float


def _build_records(coin: str, trades: list[Trade], use_funding: bool) -> list[TradeRec]:
    funding = _load_funding(coin)
    ftimes = [f[0] for f in funding]
    recs: list[TradeRec] = []
    for t in trades:
        notional = _position_size_usdt_v2(t.confidence) * LEVERAGE
        fund = _accrue_funding(t, funding, ftimes) if use_funding else 0.0
        recs.append(TradeRec(
            coin=coin, side=t.side, entry_time=t.entry_time, exit_time=t.exit_time,
            entry_price=t.entry_price, exit_price=t.exit_price, notional=notional,
            base_pnl=t.pnl, funding_usd=fund, net_pnl=t.pnl + fund,
            confidence=t.confidence,
            hold_hours=(t.exit_time - t.entry_time) / 3_600_000.0,
        ))
    return recs


def _metrics(recs: list[TradeRec]) -> dict[str, Any]:
    if not recs:
        return {"net_return_pct": 0.0, "profit_factor": 0.0, "max_dd_pct": 0.0,
                "n_trades": 0, "win_rate": 0.0, "avg_hold_hours": 0.0,
                "net_pnl_usd": 0.0, "notional_usd": 0.0}
    recs = sorted(recs, key=lambda r: r.exit_time)
    pnls = [r.net_pnl for r in recs]
    notional = sum(r.notional for r in recs)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp, gl = sum(wins), abs(sum(losses))
    # Equity curve in % of summed notional (capital-at-risk weighting).
    eq = [0.0]
    for p in pnls:
        eq.append(eq[-1] + p)
    mdd_usd = _max_drawdown(eq)
    return {
        "net_return_pct": round(sum(pnls) / notional * 100, 3) if notional else 0.0,
        "profit_factor": round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0),
        "max_dd_pct": round(mdd_usd / notional * 100, 3) if notional else 0.0,
        "n_trades": len(recs),
        "win_rate": round(len(wins) / len(recs), 3),
        "avg_hold_hours": round(mean(r.hold_hours for r in recs), 1),
        "net_pnl_usd": round(sum(pnls), 4),
        "notional_usd": round(notional, 2),
    }


def _window_of(entry_ms: int) -> str | None:
    for name, (s, e) in WINDOWS.items():
        if _to_ms(s) <= entry_ms < _to_ms(e):
            return name
    return None


def _eligible(coin: str, window: str, kl4_first_open: dict[str, int]) -> bool:
    """Coin tradable in window only if >=60d history before window OOS start."""
    win_start = _to_ms(WINDOWS[window][0])
    first = kl4_first_open[coin]
    return (win_start - first) >= ELIGIBILITY_DAYS * 86_400_000


# ---------------------------------------------------------------------------
# Replay driver
# ---------------------------------------------------------------------------

def _run_variant(long_only: bool, use_funding: bool, slip_bps: float):
    """Run the warehouse replay for all coins; return per-coin v2 TradeRec lists."""
    # Long-only: wrap decide_v2 in the engine's namespace (the seam _run_coin uses).
    orig = bt_strategy.decide_v2
    if long_only:
        bt_engine.decide_v2 = _make_long_only_decide(orig)
    else:
        bt_engine.decide_v2 = orig

    eng = WarehouseEngine(
        coins=COINS,
        start=datetime.fromisoformat(REPLAY_START).replace(tzinfo=timezone.utc),
        end=datetime.fromisoformat(REPLAY_END).replace(tzinfo=timezone.utc),
        fee_bps=FEE_BPS,
        slippage_bps=slip_bps,
        rate_limit_delay=0.0,
        use_funding=use_funding,
    )

    per_coin: dict[str, list[TradeRec]] = {}
    for coin in COINS:
        _v1, v2, _bars = eng._run_coin(coin)
        per_coin[coin] = _build_records(coin, v2.trades, use_funding)

    bt_engine.decide_v2 = orig  # restore
    return per_coin


def _slice_eligible(per_coin: dict[str, list[TradeRec]],
                    kl4_first: dict[str, int]) -> dict[str, list[TradeRec]]:
    """Keep only trades whose entry falls in a window for which the coin is eligible."""
    out: dict[str, list[TradeRec]] = {c: [] for c in per_coin}
    for coin, recs in per_coin.items():
        for r in recs:
            w = _window_of(r.entry_time)
            if w is None:
                continue
            if _eligible(coin, w, kl4_first):
                out[coin].append(r)
    return out


def _report(per_coin_sliced: dict[str, list[TradeRec]],
            kl4_first: dict[str, int]) -> dict[str, Any]:
    all_recs = [r for recs in per_coin_sliced.values() for r in recs]

    per_window: dict[str, Any] = {}
    for w in WINDOWS:
        wr = [r for r in all_recs if _window_of(r.entry_time) == w]
        m = _metrics(wr)
        eligible_coins = sorted(c for c in COINS if _eligible(c, w, kl4_first))
        m["eligible_coins"] = eligible_coins
        m["n_eligible_coins"] = len(eligible_coins)
        per_window[w] = m
    per_window["pooled"] = _metrics(all_recs)

    per_coin_out = []
    for coin in COINS:
        recs = per_coin_sliced.get(coin, [])
        if not recs:
            continue
        m = _metrics(recs)
        per_coin_out.append({
            "coin": coin,
            "net_pnl_pct": m["net_return_pct"],
            "n_trades": m["n_trades"],
            "win_rate": m["win_rate"],
        })
    return {"per_window": per_window, "per_coin": per_coin_out}


def main():
    # First open per coin for eligibility.
    kl4_first: dict[str, int] = {}
    for coin in COINS:
        path = os.path.join(WAREHOUSE, "klines_4h", f"{coin}USDT.parquet")
        kl4_first[coin] = int(duckdb.sql(f"SELECT min(open_time) FROM '{path}'").fetchone()[0])

    print("=== Running LONG-ONLY, REAL funding ===")
    lo_real = _run_variant(long_only=True, use_funding=True, slip_bps=SLIP_BPS)
    print("=== Running LONG-ONLY, ZERO funding ===")
    lo_zero = _run_variant(long_only=True, use_funding=False, slip_bps=SLIP_BPS)
    print("=== Running LONG+SHORT, REAL funding ===")
    ls_real = _run_variant(long_only=False, use_funding=True, slip_bps=SLIP_BPS)
    print("=== Running LONG-ONLY, REAL funding, STRESS 10bps slip ===")
    lo_stress = _run_variant(long_only=True, use_funding=True, slip_bps=STRESS_SLIP_BPS)

    lo_real_s = _slice_eligible(lo_real, kl4_first)
    lo_zero_s = _slice_eligible(lo_zero, kl4_first)
    ls_real_s = _slice_eligible(ls_real, kl4_first)
    lo_stress_s = _slice_eligible(lo_stress, kl4_first)

    long_only_rep = _report(lo_real_s, kl4_first)
    ls_rep = _report(ls_real_s, kl4_first)

    # Funding contribution: real pooled net % minus zero pooled net %.
    lo_real_pooled = long_only_rep["per_window"]["pooled"]
    lo_zero_pooled = _report(lo_zero_s, kl4_first)["per_window"]["pooled"]
    funding_contrib = round(
        lo_real_pooled["net_return_pct"] - lo_zero_pooled["net_return_pct"], 3
    )

    stress_pooled = _report(lo_stress_s, kl4_first)["per_window"]["pooled"]

    # ---- Sanity: DOGE entry dates + buy&hold comparison ----
    doge = sorted(lo_real_s["DOGE"], key=lambda r: r.entry_time)[:5]
    doge_sample = [
        {"entry": _utc(r.entry_time).strftime("%Y-%m-%d %H:%M"),
         "exit": _utc(r.exit_time).strftime("%Y-%m-%d %H:%M"),
         "entry_px": round(r.entry_price, 6), "exit_px": round(r.exit_price, 6),
         "side": r.side, "net_pnl": round(r.net_pnl, 4)}
        for r in doge
    ]
    bh = _equal_weight_buy_hold(kl4_first)

    result = {
        "method": "warehouse klines + decide_v2/ReplayEngine reuse; real funding",
        "windows": WINDOWS,
        "cost_model": {"fee_bps_per_side": FEE_BPS, "slip_bps_per_side": SLIP_BPS,
                       "stress_slip_bps": STRESS_SLIP_BPS,
                       "funding": "accrued on notional over hold; long pays positive"},
        "long_only": {
            "per_window": long_only_rep["per_window"],
            "per_coin": long_only_rep["per_coin"],
            "funding_contribution_pct": funding_contrib,
            "zero_funding_pooled_net_pct": lo_zero_pooled["net_return_pct"],
            "stress_pooled": stress_pooled,
        },
        "long_and_short": {
            "per_window": ls_rep["per_window"],
            "per_coin": ls_rep["per_coin"],
        },
        "sanity": {
            "doge_first_5_trades": doge_sample,
            "buy_hold_equal_weight": bh,
        },
    }
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nWrote {OUT_JSON}")
    print(json.dumps({
        "long_only_pooled": lo_real_pooled,
        "funding_contribution_pct": funding_contrib,
        "long_short_pooled": ls_rep["per_window"]["pooled"],
        "stress_pooled": stress_pooled,
    }, indent=2, default=str))
    return result


def _equal_weight_buy_hold(kl4_first: dict[str, int]) -> dict[str, Any]:
    """Equal-weight buy&hold of the 13 coins over the full OOS span (W1 start ->
    W3 end), each coin entered at the later of (W1 start, its first bar)."""
    span_start = _to_ms(WINDOWS["W1"][0])
    span_end = _to_ms(WINDOWS["W3"][1])
    rets = []
    detail = {}
    for coin in COINS:
        rows = _load_klines(coin, "klines_4h")
        c_start = max(span_start, kl4_first[coin])
        entry = next((float(r[4]) for r in rows if int(r[6]) >= c_start), None)
        exit_px = next((float(r[4]) for r in reversed(rows) if int(r[0]) < span_end), None)
        if entry and exit_px and entry > 0:
            r = (exit_px / entry - 1) * 100
            rets.append(r)
            detail[coin] = round(r, 1)
    return {"equal_weight_net_pct": round(mean(rets), 2) if rets else 0.0,
            "per_coin_pct": detail,
            "note": "spot buy&hold, no leverage; strategy is 5x leveraged so % are not directly comparable"}


if __name__ == "__main__":
    main()
