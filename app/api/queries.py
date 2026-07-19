"""Read-only aggregation helpers shared by the JSON routes and the status page.

Every function returns plain dicts/lists so both consumers share one code path.
Engine access is via the models module attribute (see tests/api/conftest.py).
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.intraday.config import PAPER_EQUITY


def list_trades(limit: int = 50, symbol: str | None = None,
                status: str | None = None, since: str | None = None) -> list[dict]:
    with Session(models.engine) as session:
        q = session.query(models.IntradayTrade)
        if symbol:
            q = q.filter(models.IntradayTrade.symbol == symbol.upper())
        if status:
            q = q.filter(models.IntradayTrade.status == status.lower())
        if since:
            q = q.filter(models.IntradayTrade.entry_time >= since)
        rows = q.order_by(models.IntradayTrade.id.desc()).limit(limit).all()
    return [_trade_dict(t) for t in rows]


def _trade_dict(t: models.IntradayTrade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "limit_price": t.limit_price,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "slot_usd": t.slot_usd,
        "entry_time": t.entry_time,
        "exit_time": t.exit_time,
        "hold_bars": t.hold_bars,
        "pnl_pct": round(t.pnl_pct * 100, 4) if t.pnl_pct is not None else None,
        "pnl_usd": t.pnl_usd,
        "fill_type": t.fill_type,
        "exit_reason": t.exit_reason,
        "status": t.status,
    }


def trade_stats(since: str | None = None) -> dict:
    with Session(models.engine) as session:
        q = session.query(models.IntradayTrade).filter(
            models.IntradayTrade.status == "closed")
        if since:
            q = q.filter(models.IntradayTrade.entry_time >= since)
        closed = q.order_by(models.IntradayTrade.exit_time.asc()).all()

    if not closed:
        return {"trades": 0, "message": "No closed intraday trades in window."}

    pnls = [t.pnl_usd or 0.0 for t in closed]
    pcts = [(t.pnl_pct or 0.0) * 100 for t in closed]
    wins = [p for p in pnls if p > 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    else:
        profit_factor = 999.0 if gross_win > 0 else 0.0

    best = max(closed, key=lambda t: t.pnl_usd or 0.0)
    worst = min(closed, key=lambda t: t.pnl_usd or 0.0)

    by_symbol: dict[str, dict] = {}
    for t in closed:
        s = by_symbol.setdefault(t.symbol, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        s["trades"] += 1
        if (t.pnl_usd or 0) > 0:
            s["wins"] += 1
        s["net_pnl"] += t.pnl_usd or 0.0
    for s in by_symbol.values():
        s["win_rate_pct"] = round(s["wins"] / s["trades"] * 100, 2)
        s["net_pnl"] = round(s["net_pnl"], 4)

    return {
        "trades": len(closed),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 2),
        "net_pnl_usd": round(sum(pnls), 4),
        "gross_win_usd": round(gross_win, 4),
        "gross_loss_usd": round(gross_loss, 4),
        "profit_factor": profit_factor,
        "avg_pnl_pct": round(sum(pcts) / len(pcts), 4),
        "median_pnl_pct": round(statistics.median(pcts), 4),
        "best_trade": {"symbol": best.symbol, "pnl_usd": round(best.pnl_usd or 0, 4),
                       "exit_time": best.exit_time},
        "worst_trade": {"symbol": worst.symbol, "pnl_usd": round(worst.pnl_usd or 0, 4),
                        "exit_time": worst.exit_time},
        "period": {"first_entry": min(t.entry_time for t in closed),
                   "last_exit": max((t.exit_time for t in closed if t.exit_time),
                                    default=None)},
        "by_symbol": by_symbol,
    }


OUTCOMES = ("trade_through", "touch_only", "miss", "no_data")


def fill_stats() -> dict:
    with Session(models.engine) as session:
        rows = session.query(models.IntradayLimit).all()

    resolved = [r for r in rows if r.outcome is not None]
    by_outcome = {}
    for name in OUTCOMES:
        count = sum(1 for r in resolved if r.outcome == name)
        by_outcome[name] = {
            "count": count,
            "pct": round(count / len(resolved) * 100, 2) if resolved else 0.0,
        }
    return {
        "total_placed": len(rows),
        "pending": len(rows) - len(resolved),
        "admitted": sum(1 for r in resolved if r.admitted),
        "by_outcome": by_outcome,
    }


_STATE_KEYS = ("paper_book", "killswitch", "universe")


def engine_state(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    raw: dict[str, dict | None] = {}
    updated: dict[str, str] = {}
    warnings: list[str] = []
    with Session(models.engine) as session:
        for key in _STATE_KEYS:
            row = session.get(models.IntradayState, key)
            if row is None:
                raw[key] = None
                continue
            updated[key] = row.updated
            try:
                raw[key] = dict(row.value)
            except (TypeError, ValueError):
                raw[key] = None
                warnings.append(f"state row '{key}' unreadable")

    book = raw["paper_book"] or {}
    ks = raw["killswitch"] or {}
    uni = raw["universe"] or {}
    equity = book.get("equity")

    out = {
        "equity": equity,
        "slot_usd": book.get("slot_usd"),
        "positions": book.get("positions", {}),
        "pending": book.get("pending", {}),
        "killswitch": {
            "halted": ks.get("halted"),
            "day": ks.get("day"),
            "day_anchor": ks.get("day_anchor"),
            "peak": ks.get("peak"),
            "daily_loss_pct": ks.get("daily_loss_pct"),
            "max_dd_pct": ks.get("max_dd_pct"),
            "day_pnl_pct": _pct_change(equity, ks.get("day_anchor")),
            "drawdown_from_peak_pct": _pct_change(equity, ks.get("peak")),
        },
        "universe": {
            "symbols": uni.get("symbols", []),
            "refreshed_ms": uni.get("refreshed_ms"),
            "age_days": _age_days(uni.get("refreshed_ms"), now),
        },
        "updated": updated,
    }
    if warnings:
        out["warning"] = "; ".join(warnings)
    return out


def _pct_change(value: float | None, base: float | None) -> float | None:
    if value is None or not base:
        return None
    return round((value / base - 1) * 100, 4)


def _age_days(refreshed_ms: int | None, now: datetime) -> float | None:
    if refreshed_ms is None:
        return None
    then = datetime.fromtimestamp(refreshed_ms / 1000, tz=timezone.utc)
    return round((now - then).total_seconds() / 86400, 1)


# 4-week telemetry window — docs/intraday_operations.md "Go-live gate (manual only)".
GATE_START = date(2026, 7, 16)
GATE_END = date(2026, 8, 13)


def gate_progress(today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    stats = trade_stats()
    ks = engine_state()["killswitch"]
    fills = fill_stats()

    net_pnl = stats["net_pnl_usd"] if stats["trades"] else 0.0
    resolved = fills["total_placed"] - fills["pending"]
    tt_pct = fills["by_outcome"]["trade_through"]["pct"] if resolved else None
    halted = bool(ks["halted"])
    window_days = (GATE_END - GATE_START).days

    return {
        "window": {
            "start": GATE_START.isoformat(),
            "end": GATE_END.isoformat(),
            "days_elapsed": min(max((today - GATE_START).days, 0), window_days),
            "days_remaining": max((GATE_END - today).days, 0),
        },
        "criteria": {
            "cumulative_pnl": {"value_usd": net_pnl, "pass": net_pnl >= 0},
            "kill_switch": {
                "halted_now": halted,
                "day_pnl_pct": ks["day_pnl_pct"],
                "daily_halt_at_pct": _halt_threshold_pct(ks["daily_loss_pct"]),
                "drawdown_from_peak_pct": ks["drawdown_from_peak_pct"],
                "drawdown_halt_at_pct": _halt_threshold_pct(ks["max_dd_pct"]),
                "note": "current latch only; trip history lives in Telegram",
            },
            "trade_through_rate_pct": tt_pct,
        },
        "on_track": net_pnl >= 0 and not halted,
    }


def _halt_threshold_pct(fraction: float | None) -> float | None:
    return None if fraction is None else -round(fraction * 100, 2)


def realized_equity_curve() -> list[float]:
    """Equity after each closed trade (realized only — blind to open-position drift)."""
    with Session(models.engine) as session:
        closed = (
            session.query(models.IntradayTrade)
            .filter(models.IntradayTrade.status == "closed")
            .order_by(models.IntradayTrade.exit_time.asc())
            .all()
        )
    points = [PAPER_EQUITY]
    for t in closed:
        points.append(round(points[-1] + (t.pnl_usd or 0.0), 4))
    return points
