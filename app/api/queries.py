"""Read-only aggregation helpers shared by the JSON routes and the status page.

Every function returns plain dicts/lists so both consumers share one code path.
Engine access is via the models module attribute (see tests/api/conftest.py).
"""

from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from app.db import models


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
