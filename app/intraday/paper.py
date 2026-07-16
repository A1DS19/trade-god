"""Paper book: the incremental live twin of strategy.build_weights
(fill="maker_limit", exit="horizon"). The transition rules map 1:1 to the
batch builder and are pinned by the replay-parity test; change them only
with that test in front of you. Slot allocation matches the batch builder's
SIGNAL-bar semantics: each limit carries free_at_placement and admissions
are capped by it, so a slot freed after the signal never admits a fill the
batch would have blocked.

Known intentional limitations: horizon_bars == 1 diverges from batch slot
timing (fill and exit share a cycle; the frozen strategy uses 32), and
universe drops do NOT force-exit live positions (spec: run to exit) whereas
the batch eligibility mask exits immediately.
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field

import math

from app.intraday.strategy import Z_ENTRY

Bar = namedtuple("Bar", "open_time close low")


@dataclass
class CycleResult:
    placements: list = field(default_factory=list)
    resolutions: list = field(default_factory=list)
    exits: list = field(default_factory=list)
    entries: list = field(default_factory=list)


class PaperBook:
    def __init__(self, equity: float, max_k: int, horizon_bars: int,
                 entry_cost: float = 0.0002, exit_cost: float = 0.0008):
        self.equity = equity
        self.max_k = max_k
        self.horizon_bars = horizon_bars
        self.entry_cost = entry_cost
        self.exit_cost = exit_cost
        self.slot_usd = equity / max_k
        self.pending: dict[str, dict] = {}    # symbol -> {limit, z, placed_ms}
        self.positions: dict[str, dict] = {}  # symbol -> {entry, bars_held, funding_usd, entry_ms}

    # ── transitions ─────────────────────────────────────────
    def on_bar(self, bars: dict, z: dict, universe: set) -> CycleResult:
        res = CycleResult()

        # 1. resolve limits placed on the previous bar
        fills = []
        for sym, lim in list(self.pending.items()):
            bar = bars.get(sym)
            if bar is None:
                outcome, bar_low = "no_data", None
            elif bar.low < lim["limit"]:
                outcome, bar_low = "trade_through", bar.low
            elif bar.low == lim["limit"]:
                outcome, bar_low = "touch_only", bar.low
            else:
                outcome, bar_low = "miss", bar.low
            rec = {"symbol": sym, "limit_price": lim["limit"], "outcome": outcome,
                   "bar_low": bar_low, "admitted": False, "z": lim["z"],
                   "placed_ms": lim["placed_ms"],
                   "free_at_placement": lim["free_at_placement"]}
            res.resolutions.append(rec)
            if outcome == "trade_through":
                fills.append(rec)
            del self.pending[sym]

        # 2. age positions that existed before this bar
        for pos in self.positions.values():
            pos["bars_held"] += 1

        # 3. exits at horizon
        for sym in list(self.positions):
            pos = self.positions[sym]
            if pos["bars_held"] >= self.horizon_bars:
                bar = bars.get(sym)
                if bar is None:
                    continue   # no price this bar; exit on the next bar we see one
                gross = self.slot_usd * (bar.close / pos["entry"] - 1.0)
                pnl = (gross - self.slot_usd * (self.entry_cost + self.exit_cost)
                       + pos["funding_usd"])
                self.equity += pnl
                res.exits.append({
                    "symbol": sym, "entry_price": pos["entry"],
                    "exit_price": bar.close, "hold_bars": pos["bars_held"],
                    "pnl_usd": pnl,
                    "pnl_pct": bar.close / pos["entry"] - 1.0,
                })
                del self.positions[sym]

        # 4. admissions: lowest signal z first, capped by the SIGNAL-bar slot
        # count (batch builder allocates at the signal bar — see docstring)
        fills.sort(key=lambda r: r["z"])
        free = 0
        if fills:
            free = min(fills[0]["free_at_placement"],
                       self.max_k - len(self.positions))
        for rec in fills[:free]:
            rec["admitted"] = True
            self.positions[rec["symbol"]] = {
                "entry": rec["limit_price"], "bars_held": 1,
                "funding_usd": 0.0, "entry_ms": rec["placed_ms"],
            }
            res.entries.append({"symbol": rec["symbol"],
                                "entry_price": rec["limit_price"], "z": rec["z"]})

        # 5. new placements at this bar's close (record the signal-bar slot
        # count — admissions next bar are capped by it)
        free_now = self.max_k - len(self.positions)
        for sym in sorted(universe):
            zv = z.get(sym)
            bar = bars.get(sym)
            if (bar is None or zv is None or not math.isfinite(zv)
                    or zv >= Z_ENTRY or sym in self.positions
                    or sym in self.pending):
                continue
            self.pending[sym] = {"limit": bar.close, "z": zv,
                                 "placed_ms": bar.open_time,
                                 "free_at_placement": free_now}
            res.placements.append({"symbol": sym, "limit_price": bar.close,
                                   "z": zv, "placed_ms": bar.open_time})
        return res

    # ── accounting ──────────────────────────────────────────
    def apply_funding(self, symbol: str, rate: float):
        pos = self.positions.get(symbol)
        if pos is not None:
            pos["funding_usd"] -= self.slot_usd * rate

    def mark_equity(self, closes: dict) -> float:
        unrealized = 0.0
        for sym, pos in self.positions.items():
            px = closes.get(sym)
            if px is not None:
                unrealized += (self.slot_usd * (px / pos["entry"] - 1.0)
                               + pos["funding_usd"])
        return self.equity + unrealized

    # ── persistence ─────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "equity": self.equity, "max_k": self.max_k,
            "horizon_bars": self.horizon_bars,
            "entry_cost": self.entry_cost, "exit_cost": self.exit_cost,
            "pending": self.pending, "positions": self.positions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperBook":
        book = cls(d["equity"], d["max_k"], d["horizon_bars"],
                   d["entry_cost"], d["exit_cost"])
        book.pending = {k: dict(v) for k, v in d["pending"].items()}
        book.positions = {k: dict(v) for k, v in d["positions"].items()}
        return book
