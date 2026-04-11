"""FastAPI application — read-only portfolio and trade data."""

from datetime import datetime, timezone

from fastapi import FastAPI, Query
from sqlalchemy.orm import Session as SASession

from app.db.models import Position, SwingTrade, Trade, engine

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


# ── Swing trades ───────────────────────────────────────────
@app.get("/swing/trades")
def swing_trades(
    limit: int = Query(default=100, le=500),
    coin: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
):
    """Swing futures trade history, newest first.

    Filters (all optional): coin, direction (long|short), status (open|closed),
    since (ISO datetime, matches entry_time lexicographically).
    """
    with SASession(engine) as session:
        q = session.query(SwingTrade)
        if coin:
            q = q.filter(SwingTrade.coin == coin.upper())
        if direction:
            q = q.filter(SwingTrade.direction == direction.lower())
        if status:
            q = q.filter(SwingTrade.status == status.lower())
        if since:
            q = q.filter(SwingTrade.entry_time >= since)
        rows = q.order_by(SwingTrade.entry_time.desc()).limit(limit).all()

    return [
        {
            "id": t.id,
            "coin": t.coin,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "qty": t.qty,
            "leverage": t.leverage,
            "notional_usdt": t.notional_usdt,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "realized_pnl_usd": t.realized_pnl_usd,
            "realized_pnl_pct": (
                round(t.realized_pnl_pct * 100, 4)
                if t.realized_pnl_pct is not None
                else None
            ),
            "entry_sl_pct": t.entry_sl_pct,
            "entry_tp_pct": t.entry_tp_pct,
            "exit_reason": t.exit_reason,
            "agent_confidence": t.agent_confidence,
            "status": t.status,
        }
        for t in rows
    ]


# ── Swing stats ────────────────────────────────────────────
@app.get("/swing/stats")
def swing_stats(since: str | None = Query(default=None)):
    """Aggregate swing performance.

    Field names mirror the backtest_replay output so a reconciliation against
    `python -m app.swing.backtest_replay` output is a direct dict diff.
    Pass `since=<ISO datetime>` to restrict to trades with entry_time >= since.
    """
    with SASession(engine) as session:
        q = session.query(SwingTrade).filter(SwingTrade.status == "closed")
        if since:
            q = q.filter(SwingTrade.entry_time >= since)
        closed = q.order_by(SwingTrade.exit_time.asc()).all()

    if not closed:
        return {"trades": 0, "message": "No closed swing trades in window."}

    pnls = [t.realized_pnl_usd or 0.0 for t in closed]
    wins_pnl = [p for p in pnls if p > 0]
    losses_pnl = [p for p in pnls if p <= 0]
    win_rate = len(wins_pnl) / len(pnls) * 100
    gross_win = sum(wins_pnl)
    gross_loss = abs(sum(losses_pnl))
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = 999.0 if gross_win > 0 else 0.0
    net_pnl = sum(pnls)

    # Max drawdown from running equity curve (ordered by exit_time)
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    # Per-coin
    by_coin: dict[str, dict] = {}
    for t in closed:
        c = by_coin.setdefault(
            t.coin, {"trades": 0, "wins": 0, "net_pnl": 0.0, "sum_conf": 0.0}
        )
        c["trades"] += 1
        if (t.realized_pnl_usd or 0) > 0:
            c["wins"] += 1
        c["net_pnl"] += t.realized_pnl_usd or 0.0
        c["sum_conf"] += t.agent_confidence
    for c in by_coin.values():
        c["win_rate_pct"] = round(c["wins"] / c["trades"] * 100, 2)
        c["net_pnl"] = round(c["net_pnl"], 2)
        c["avg_conf"] = round(c["sum_conf"] / c["trades"], 2)
        del c["sum_conf"]

    # Per-exit-reason
    by_reason: dict[str, dict] = {}
    for t in closed:
        reason = t.exit_reason or "unknown"
        r = by_reason.setdefault(reason, {"count": 0, "wins": 0, "net_pnl": 0.0})
        r["count"] += 1
        if (t.realized_pnl_usd or 0) > 0:
            r["wins"] += 1
        r["net_pnl"] += t.realized_pnl_usd or 0.0
    for r in by_reason.values():
        r["win_rate_pct"] = round(r["wins"] / r["count"] * 100, 2)
        r["net_pnl"] = round(r["net_pnl"], 2)

    avg_conf = sum(t.agent_confidence for t in closed) / len(closed)
    first_entry = min(t.entry_time for t in closed)
    last_exit = max((t.exit_time for t in closed if t.exit_time), default=None)

    return {
        "trades": len(closed),
        "win_rate_pct": round(win_rate, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "gross_win_usd": round(gross_win, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_usd": round(max_dd, 2),
        "avg_confidence": round(avg_conf, 2),
        "period": {
            "first_entry": first_entry,
            "last_exit": last_exit,
        },
        "by_coin": by_coin,
        "by_exit_reason": by_reason,
    }
