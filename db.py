"""
Database module — SQLAlchemy models and state persistence.

Tables:
  positions   — one row per coin, tracks avg_buy / qty / last_buy
  daily_spend — one row per UTC day, tracks total USDT spent
  coin_list   — one row per UTC day, tracks the active watch list

Keeping load/save as a thin dict layer means the bot logic is unchanged
and the same models can be reused directly by a future web app.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import Column, Float, JSON, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

# ── Engine ────────────────────────────────────────────────────────────────────
# Normalise URL scheme:
#   postgres://     → postgresql+psycopg://   (Railway shorthand)
#   postgresql://   → postgresql+psycopg://   (standard)
_url = os.environ["DATABASE_URL"]
_url = _url.replace("postgres://", "postgresql://", 1)
if not _url.startswith("postgresql+"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(_url, pool_pre_ping=True)


# ── Models ────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class Position(Base):
    __tablename__ = "positions"

    coin     = Column(String(20), primary_key=True)
    avg_buy  = Column(Float, nullable=False, default=0.0)
    qty      = Column(Float, nullable=False, default=0.0)
    last_buy = Column(String(50), nullable=True)   # ISO-8601 datetime string


class DailySpend(Base):
    __tablename__ = "daily_spend"

    date   = Column(String(10), primary_key=True)  # YYYY-MM-DD
    amount = Column(Float, nullable=False, default=0.0)


class CoinList(Base):
    __tablename__ = "coin_list"

    date  = Column(String(10), primary_key=True)   # YYYY-MM-DD
    coins = Column(JSON, nullable=False)            # list[str]


# ── Init ──────────────────────────────────────────────────────────────────────
def init_db():
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(engine)


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    """Load full bot state from DB into the working dict format."""
    today = datetime.now(timezone.utc).date().isoformat()

    with Session(engine) as session:
        # Positions
        state: dict = {}
        for pos in session.query(Position).all():
            state[pos.coin] = {
                "avg_buy":  pos.avg_buy,
                "qty":      pos.qty,
                "last_buy": pos.last_buy,
            }

        # Daily spend
        spend = session.get(DailySpend, today)
        state["daily_spend"] = {
            "date":   today,
            "amount": spend.amount if spend else 0.0,
        }

        # Coin list
        coin_list = session.get(CoinList, today)
        state["coin_list"] = {
            "date":  coin_list.date  if coin_list else None,
            "coins": coin_list.coins if coin_list else [],
        }

    return state


def save_state(state: dict):
    """Persist the working dict state back to DB."""
    with Session(engine) as session:
        # Positions
        for key, data in state.items():
            if key in ("daily_spend", "coin_list"):
                continue
            session.merge(Position(
                coin=key,
                avg_buy=data["avg_buy"],
                qty=data["qty"],
                last_buy=data["last_buy"],
            ))

        # Daily spend
        ds = state["daily_spend"]
        if ds["date"]:
            session.merge(DailySpend(date=ds["date"], amount=ds["amount"]))

        # Coin list
        cl = state["coin_list"]
        if cl["date"]:
            session.merge(CoinList(date=cl["date"], coins=cl["coins"]))

        session.commit()
