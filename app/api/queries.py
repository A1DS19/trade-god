"""Read-only aggregation helpers shared by the JSON routes and the status page.

Every function returns plain dicts/lists so both consumers share one code path.
Engine access is via the models module attribute (see tests/api/conftest.py).
"""

from __future__ import annotations

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
