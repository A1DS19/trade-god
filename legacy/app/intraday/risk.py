"""Kill-switches (armed in paper — proving them is part of the phase) and
the consecutive-error tracker."""

from __future__ import annotations


class ErrorTracker:
    def __init__(self, strikes: int = 3):
        self.strikes = strikes
        self._counts: dict[str, int] = {}

    def record(self, symbol: str, ok: bool) -> bool:
        if ok:
            self._counts[symbol] = 0
            return False
        self._counts[symbol] = self._counts.get(symbol, 0) + 1
        return self._counts[symbol] == self.strikes


class KillSwitch:
    def __init__(self, daily_loss_pct: float, max_dd_pct: float):
        self.daily_loss_pct = daily_loss_pct
        self.max_dd_pct = max_dd_pct
        self.halted = False
        self.day = None
        self.day_anchor = None
        self.peak = None

    def check(self, equity_mark: float, utc_date: str) -> str | None:
        if self.day != utc_date:
            self.day = utc_date
            self.day_anchor = equity_mark
        if self.peak is None or equity_mark > self.peak:
            self.peak = equity_mark
        if self.halted:
            return None
        if equity_mark < self.day_anchor * (1.0 - self.daily_loss_pct):
            self.halted = True
            return "daily_loss"
        if equity_mark < self.peak * (1.0 - self.max_dd_pct):
            self.halted = True
            return "drawdown"
        return None

    def resume(self):
        self.halted = False
        self.day = None       # re-anchor on the next check

    def to_dict(self) -> dict:
        return {"daily_loss_pct": self.daily_loss_pct,
                "max_dd_pct": self.max_dd_pct, "halted": self.halted,
                "day": self.day, "day_anchor": self.day_anchor,
                "peak": self.peak}

    @classmethod
    def from_dict(cls, d: dict) -> "KillSwitch":
        ks = cls(d["daily_loss_pct"], d["max_dd_pct"])
        ks.halted = d["halted"]
        ks.day = d["day"]
        ks.day_anchor = d["day_anchor"]
        ks.peak = d["peak"]
        return ks
