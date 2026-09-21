"""
SQLAlchemy models and state persistence.

Tables:
  positions   — one row per coin: avg_buy, qty, last_buy, peak_price
  daily_spend — one row per UTC day: total USDT spent
  coin_list   — one row per UTC day: active watch list
  trades      — append-only log of every buy and sell
"""

import os
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Integer, JSON, String, Boolean, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

# ── Engine ────────────────────────────────────────────────
_url = os.environ["DATABASE_URL"]
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)
if not _url.startswith("postgresql+"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
    connect_args={"connect_timeout": 10},
)


# ── Models ────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class Position(Base):
    __tablename__ = "positions"

    coin = Column(String(20), primary_key=True)
    avg_buy = Column(Float, nullable=False, default=0.0)
    qty = Column(Float, nullable=False, default=0.0)
    last_buy = Column(String(50), nullable=True)
    peak_price = Column(Float, nullable=True)
    partial_taken = Column(Boolean, nullable=False, default=False)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coin = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)        # BUY or SELL
    price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    cost_usd = Column(Float, nullable=False)        # spent (buy) or received (sell)
    avg_buy = Column(Float, nullable=True)          # position avg_buy at trade time
    realized_pnl_usd = Column(Float, nullable=True) # sells only
    realized_pnl_pct = Column(Float, nullable=True) # sells only
    exit_reason = Column(String(30), nullable=True) # sells only
    timestamp = Column(String(30), nullable=False)


class SwingTrade(Base):
    __tablename__ = "swing_trades"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    coin             = Column(String(20), nullable=False)
    direction        = Column(String(5), nullable=False)   # long | short
    entry_price      = Column(Float, nullable=False)
    exit_price       = Column(Float, nullable=True)
    qty              = Column(Float, nullable=False)
    leverage         = Column(Integer, nullable=False)
    notional_usdt    = Column(Float, nullable=False)
    entry_time       = Column(String(50), nullable=False)
    exit_time        = Column(String(50), nullable=True)
    realized_pnl_usd = Column(Float, nullable=True)
    realized_pnl_pct = Column(Float, nullable=True)
    exit_reason      = Column(String(100), nullable=True)
    entry_sl_pct     = Column(Float, nullable=True)   # ATR-based SL % at entry
    entry_tp_pct     = Column(Float, nullable=True)   # ATR-based TP % at entry
    agent_confidence = Column(Float, nullable=False)
    agent_reasoning  = Column(String(500), nullable=True)
    status           = Column(String(6), nullable=False, default="open")  # open | closed


class DailySpend(Base):
    __tablename__ = "daily_spend"

    date = Column(String(10), primary_key=True)
    amount = Column(Float, nullable=False, default=0.0)


class CoinList(Base):
    __tablename__ = "coin_list"

    date = Column(String(10), primary_key=True)
    coins = Column(JSON, nullable=False)


class IntradayTrade(Base):
    __tablename__ = "intraday_trades"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    direction   = Column(String(5), nullable=False, default="long")
    mode        = Column(String(5), nullable=False)          # paper | live
    limit_price = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price  = Column(Float, nullable=True)
    slot_usd    = Column(Float, nullable=False)
    entry_time  = Column(String(50), nullable=False)
    exit_time   = Column(String(50), nullable=True)
    hold_bars   = Column(Integer, nullable=True)
    pnl_pct     = Column(Float, nullable=True)
    pnl_usd     = Column(Float, nullable=True)
    fill_type   = Column(String(15), nullable=False)         # trade_through
    exit_reason = Column(String(30), nullable=True)
    status      = Column(String(6), nullable=False, default="open")


class IntradayLimit(Base):
    __tablename__ = "intraday_limits"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    limit_price = Column(Float, nullable=False)
    placed_at   = Column(String(50), nullable=False)
    resolved_at = Column(String(50), nullable=True)
    outcome     = Column(String(15), nullable=True)   # trade_through|touch_only|miss|no_data
    bar_low     = Column(Float, nullable=True)
    admitted    = Column(Boolean, nullable=True)


class IntradayState(Base):
    __tablename__ = "intraday_state"

    key     = Column(String(40), primary_key=True)
    value   = Column(JSON, nullable=False)
    updated = Column(String(50), nullable=False)


# ── DB init ───────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(engine)


# ── State helpers ─────────────────────────────────────────
def load_state() -> dict:
    today = datetime.now(timezone.utc).date().isoformat()

    with Session(engine) as session:
        state: dict = {}

        for pos in session.query(Position).filter(Position.qty > 0).all():
            state[pos.coin] = {
                "avg_buy": pos.avg_buy,
                "qty": pos.qty,
                "last_buy": pos.last_buy,
                "peak_price": pos.peak_price,
                "partial_taken": pos.partial_taken or False,
            }

        spend = session.get(DailySpend, today)
        state["daily_spend"] = {
            "date": today,
            "amount": spend.amount if spend else 0.0,
        }

        coin_list = session.get(CoinList, today)
        state["coin_list"] = {
            "date": coin_list.date if coin_list else None,
            "coins": coin_list.coins if coin_list else [],
        }

    return state


def save_state(state: dict):
    with Session(engine) as session:
        for key, data in state.items():
            if key in ("daily_spend", "coin_list"):
                continue
            if data["qty"] > 0:
                session.merge(
                    Position(
                        coin=key,
                        avg_buy=data["avg_buy"],
                        qty=data["qty"],
                        last_buy=data["last_buy"],
                        peak_price=data.get("peak_price"),
                        partial_taken=data.get("partial_taken", False),
                    )
                )

        ds = state["daily_spend"]
        if ds["date"]:
            session.merge(DailySpend(date=ds["date"], amount=ds["amount"]))

        cl = state["coin_list"]
        if cl["date"]:
            session.merge(CoinList(date=cl["date"], coins=cl["coins"]))

        session.commit()


def delete_position(coin: str):
    with Session(engine) as session:
        existing = session.get(Position, coin)
        if existing:
            session.delete(existing)
            session.commit()


def log_swing_open(
    coin: str,
    direction: str,
    entry_price: float,
    qty: float,
    leverage: int,
    notional_usdt: float,
    agent_confidence: float,
    agent_reasoning: str,
    entry_sl_pct: float = 0.0,
    entry_tp_pct: float = 0.0,
) -> int:
    with Session(engine) as session:
        row = SwingTrade(
            coin=coin,
            direction=direction,
            entry_price=entry_price,
            exit_price=None,
            qty=qty,
            leverage=leverage,
            notional_usdt=notional_usdt,
            entry_time=datetime.now(timezone.utc).isoformat(),
            status="open",
            agent_confidence=agent_confidence,
            agent_reasoning=agent_reasoning,
            entry_sl_pct=entry_sl_pct,
            entry_tp_pct=entry_tp_pct,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def log_swing_close(
    trade_id: int,
    exit_price: float,
    realized_pnl_usd: float,
    realized_pnl_pct: float,
    exit_reason: str,
    exit_time: str | None = None,
):
    """exit_time: pass the ACTUAL close time (ISO) when known — e.g. reconciled
    exchange-side fills that happened cycles ago; defaults to now."""
    with Session(engine) as session:
        row = session.get(SwingTrade, trade_id)
        if row:
            row.exit_price       = exit_price
            row.exit_time        = exit_time or datetime.now(timezone.utc).isoformat()
            row.realized_pnl_usd = realized_pnl_usd
            row.realized_pnl_pct = realized_pnl_pct
            row.exit_reason      = exit_reason
            row.status           = "closed"
            session.commit()


def get_open_swing_trade(coin: str) -> SwingTrade | None:
    with Session(engine) as session:
        return (
            session.query(SwingTrade)
            .filter(SwingTrade.coin == coin, SwingTrade.status == "open")
            .order_by(SwingTrade.id.desc())
            .first()
        )


def get_all_open_swing_trades() -> list[SwingTrade]:
    with Session(engine) as session:
        return (
            session.query(SwingTrade)
            .filter(SwingTrade.status == "open")
            .order_by(SwingTrade.id.asc())
            .all()
        )


def get_last_closed_swing_trade(coin: str) -> SwingTrade | None:
    with Session(engine) as session:
        return (
            session.query(SwingTrade)
            .filter(SwingTrade.coin == coin, SwingTrade.status == "closed")
            .order_by(SwingTrade.id.desc())
            .first()
        )


def log_trade(
    coin: str,
    side: str,
    price: float,
    qty: float,
    avg_buy: float | None = None,
    realized_pnl_usd: float | None = None,
    realized_pnl_pct: float | None = None,
    exit_reason: str | None = None,
):
    with Session(engine) as session:
        session.add(Trade(
            coin=coin,
            side=side,
            price=price,
            qty=qty,
            cost_usd=qty * price,
            avg_buy=avg_buy,
            realized_pnl_usd=realized_pnl_usd,
            realized_pnl_pct=realized_pnl_pct,
            exit_reason=exit_reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        session.commit()


# ── Intraday helpers ──────────────────────────────────────
def intraday_state_get(key: str) -> dict | None:
    with Session(engine) as session:
        row = session.get(IntradayState, key)
        return dict(row.value) if row else None


def intraday_state_set(key: str, value: dict):
    with Session(engine) as session:
        session.merge(IntradayState(
            key=key, value=value,
            updated=datetime.now(timezone.utc).isoformat(),
        ))
        session.commit()


def log_intraday_trade(**fields) -> int:
    with Session(engine) as session:
        row = IntradayTrade(**fields)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def close_intraday_trade(trade_id: int, exit_price: float, exit_time: str,
                         hold_bars: int, pnl_pct: float, pnl_usd: float,
                         exit_reason: str):
    with Session(engine) as session:
        row = session.get(IntradayTrade, trade_id)
        if row:
            row.exit_price = exit_price
            row.exit_time = exit_time
            row.hold_bars = hold_bars
            row.pnl_pct = pnl_pct
            row.pnl_usd = pnl_usd
            row.exit_reason = exit_reason
            row.status = "closed"
            session.commit()


def log_intraday_limit(**fields):
    with Session(engine) as session:
        session.add(IntradayLimit(**fields))
        session.commit()
