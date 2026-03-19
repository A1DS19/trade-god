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


class DailySpend(Base):
    __tablename__ = "daily_spend"

    date = Column(String(10), primary_key=True)
    amount = Column(Float, nullable=False, default=0.0)


class CoinList(Base):
    __tablename__ = "coin_list"

    date = Column(String(10), primary_key=True)
    coins = Column(JSON, nullable=False)


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
