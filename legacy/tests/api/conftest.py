"""API test fixtures: in-memory SQLite behind the real app + TestClient.

StaticPool + check_same_thread=False are load-bearing: TestClient runs sync
endpoints in a worker thread, and without a shared single connection each
thread would see its own EMPTY in-memory database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import models


@pytest.fixture
def mem_db(monkeypatch):
    eng = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(models, "engine", eng)
    models.Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(mem_db):
    from app.api.main import app

    return TestClient(app)


@pytest.fixture
def seed(mem_db):
    """Factory: seed(model_attr, **fields) inserts a row, returns its PK id (or None)."""

    def _seed(model_attr: str, **fields):
        with Session(mem_db) as s:
            row = getattr(models, model_attr)(**fields)
            s.add(row)
            s.commit()
            return getattr(row, "id", None)

    return _seed


CLOSED_TRADE = dict(
    symbol="DOGEUSDT", mode="paper", limit_price=0.10, entry_price=0.10,
    exit_price=0.11, slot_usd=10.0,
    entry_time="2026-07-16T17:00:22+00:00", exit_time="2026-07-17T00:45:22+00:00",
    hold_bars=32, pnl_pct=0.0892, pnl_usd=0.8811, fill_type="trade_through",
    exit_reason="horizon", status="closed",
)
