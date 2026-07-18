"""JSON endpoints over the intraday telemetry tables."""

from fastapi import APIRouter, Query

from app.api import queries

router = APIRouter(prefix="/intraday", tags=["intraday"])


@router.get("/trades")
def trades(
    limit: int = Query(default=50, le=500),
    symbol: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
):
    """Intraday paper trades, newest first."""
    return queries.list_trades(limit=limit, symbol=symbol, status=status, since=since)


@router.get("/stats")
def stats(since: str | None = Query(default=None)):
    """Aggregate performance over closed trades (field names mirror /legacy/swing/stats)."""
    return queries.trade_stats(since=since)


@router.get("/fills")
def fills():
    """Cumulative limit-outcome telemetry — the measurement that decides go-live."""
    return queries.fill_stats()


@router.get("/state")
def state():
    """Engine state: equity, open book, kill-switch latch, universe."""
    return queries.engine_state()
