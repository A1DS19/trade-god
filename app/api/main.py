"""FastAPI application — read-only portfolio and trade data."""

from datetime import datetime, timezone

from fastapi import FastAPI, Query
from sqlalchemy.orm import Session as SASession

from app.db.models import Position, Trade, engine

app = FastAPI(title="Trade-God API", version="1.0.0")


# ── Health ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Portfolio ──────────────────────────────────────────────
@app.get("/portfolio")
def portfolio():
    """Open positions with cost basis and unrealized P&L placeholder."""
    with SASession(engine) as session:
        positions = session.query(Position).filter(Position.qty > 0).all()

    result = []
    for p in positions:
        cost = p.avg_buy * p.qty
        result.append(
            {
                "coin": p.coin,
                "qty": p.qty,
                "avg_buy": p.avg_buy,
                "cost_usd": round(cost, 2),
                "partial_taken": p.partial_taken,
                "last_buy": p.last_buy,
            }
        )

    total_cost = sum(r["cost_usd"] for r in result)
    return {"positions": result, "total_cost_usd": round(total_cost, 2)}


# ── P&L ───────────────────────────────────────────────────
@app.get("/pnl")
def pnl():
    """Realized P&L — today and all-time."""
    today_str = datetime.now(timezone.utc).date().isoformat()

    with SASession(engine) as session:
        today_sells = (
            session.query(Trade)
            .filter(Trade.side == "SELL", Trade.timestamp.startswith(today_str))
            .all()
        )
        all_sells = session.query(Trade).filter(Trade.side == "SELL").all()

    pnl_today = sum(t.realized_pnl_usd or 0.0 for t in today_sells)
    pnl_total = sum(t.realized_pnl_usd or 0.0 for t in all_sells)

    return {
        "today": {
            "realized_pnl_usd": round(pnl_today, 2),
            "trades": len(today_sells),
        },
        "all_time": {
            "realized_pnl_usd": round(pnl_total, 2),
            "trades": len(all_sells),
        },
    }


# ── Trades ─────────────────────────────────────────────────
@app.get("/trades")
def trades(
    limit: int = Query(default=20, le=200),
    coin: str | None = Query(default=None),
    side: str | None = Query(default=None),
):
    """Recent trades, optionally filtered by coin or side (BUY/SELL)."""
    with SASession(engine) as session:
        q = session.query(Trade)
        if coin:
            q = q.filter(Trade.coin == coin.upper())
        if side:
            q = q.filter(Trade.side == side.upper())
        rows = q.order_by(Trade.id.desc()).limit(limit).all()

    return [
        {
            "id": t.id,
            "coin": t.coin,
            "side": t.side,
            "price": t.price,
            "qty": t.qty,
            "cost_usd": round(t.cost_usd, 2),
            "avg_buy": t.avg_buy,
            "realized_pnl_usd": t.realized_pnl_usd,
            "realized_pnl_pct": (
                round(t.realized_pnl_pct * 100, 2)
                if t.realized_pnl_pct is not None
                else None
            ),
            "exit_reason": t.exit_reason,
            "timestamp": t.timestamp,
        }
        for t in rows
    ]


# ── Stats ──────────────────────────────────────────────────
@app.get("/stats")
def stats():
    """Strategy performance stats across all closed trades."""
    with SASession(engine) as session:
        sells = session.query(Trade).filter(Trade.side == "SELL").all()
        buys = session.query(Trade).filter(Trade.side == "BUY").all()

    if not sells:
        return {"message": "No closed trades yet."}

    pnls = [t.realized_pnl_usd or 0.0 for t in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100

    best = max(sells, key=lambda t: t.realized_pnl_usd or 0.0)
    worst = min(sells, key=lambda t: t.realized_pnl_usd or 0.0)

    by_reason: dict[str, dict] = {}
    for t in sells:
        reason = t.exit_reason or "unknown"
        by_reason.setdefault(reason, {"count": 0, "pnl_usd": 0.0})
        by_reason[reason]["count"] += 1
        by_reason[reason]["pnl_usd"] += t.realized_pnl_usd or 0.0

    total_spent = sum(t.cost_usd for t in buys)

    return {
        "total_sells": len(sells),
        "total_buys": len(buys),
        "win_rate_pct": round(win_rate, 1),
        "total_pnl_usd": round(sum(pnls), 2),
        "avg_pnl_usd": round(sum(pnls) / len(pnls), 2),
        "avg_win_usd": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss_usd": round(sum(losses) / len(losses), 2) if losses else 0,
        "total_spent_usd": round(total_spent, 2),
        "best_trade": {
            "coin": best.coin,
            "pnl_usd": round(best.realized_pnl_usd or 0, 2),
            "timestamp": best.timestamp,
        },
        "worst_trade": {
            "coin": worst.coin,
            "pnl_usd": round(worst.realized_pnl_usd or 0, 2),
            "timestamp": worst.timestamp,
        },
        "by_exit_reason": {
            k: {"count": v["count"], "pnl_usd": round(v["pnl_usd"], 2)}
            for k, v in by_reason.items()
        },
    }
