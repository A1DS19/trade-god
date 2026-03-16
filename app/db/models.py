"""
SQLAlchemy models and state persistence.

Tables:
  positions   — one row per coin: avg_buy, qty, last_buy, peak_price
  daily_spend — one row per UTC day: total USDT spent
  coin_list   — one row per UTC day: active watch list
"""

import os
from datetime import datetime, timezone

from sqlalchemy import Column, Float, JSON, String, create_engine
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
    connect_args={"connect_timeout": 10},
)


# ── Models ────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class Position(Base):
    __tablename__ = "positions"

    coin        = Column(String(20), primary_key=True)
    avg_buy     = Column(Float, nullable=False, default=0.0)
    qty         = Column(Float, nullable=False, default=0.0)
    last_buy    = Column(String(50), nullable=True)
    peak_price  = Column(Float, nullable=True)


class DailySpend(Base):
    __tablename__ = "daily_spend"

    date   = Column(String(10), primary_key=True)
    amount = Column(Float, nullable=False, default=0.0)


class CoinList(Base):
    __tablename__ = "coin_list"

    date  = Column(String(10), primary_key=True)
    coins = Column(JSON, nullable=False)


# ── DB init ───────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(engine)


# ── State helpers ─────────────────────────────────────────
def load_state() -> dict:
    today = datetime.now(timezone.utc).date().isoformat()

    with Session(engine) as session:
        state: dict = {}

        for pos in session.query(Position).all():
            state[pos.coin] = {
                "avg_buy":    pos.avg_buy,
                "qty":        pos.qty,
                "last_buy":   pos.last_buy,
                "peak_price": pos.peak_price,
            }

        spend = session.get(DailySpend, today)
        state["daily_spend"] = {
            "date":   today,
            "amount": spend.amount if spend else 0.0,
        }

        coin_list = session.get(CoinList, today)
        state["coin_list"] = {
            "date":  coin_list.date  if coin_list else None,
            "coins": coin_list.coins if coin_list else [],
        }

    return state


def save_state(state: dict):
    with Session(engine) as session:
        for key, data in state.items():
            if key in ("daily_spend", "coin_list"):
                continue
            if data["qty"] > 0:
                # Active position — upsert
                session.merge(Position(
                    coin=key,
                    avg_buy=data["avg_buy"],
                    qty=data["qty"],
                    last_buy=data["last_buy"],
                    peak_price=data.get("peak_price"),
                ))
            else:
                # Closed or never-bought — remove from DB to keep it clean
                existing = session.get(Position, key)
                if existing:
                    session.delete(existing)

        ds = state["daily_spend"]
        if ds["date"]:
            session.merge(DailySpend(date=ds["date"], amount=ds["amount"]))

        cl = state["coin_list"]
        if cl["date"]:
            session.merge(CoinList(date=cl["date"], coins=cl["coins"]))

        session.commit()
