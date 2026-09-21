"""Intraday persistence helpers against an in-memory SQLite engine."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.db import models


@pytest.fixture
def mem_db(monkeypatch):
    eng = create_engine("sqlite://")
    monkeypatch.setattr(models, "engine", eng)
    models.Base.metadata.create_all(eng)
    return eng


def test_state_roundtrip_and_overwrite(mem_db):
    assert models.intraday_state_get("paper_book") is None
    models.intraday_state_set("paper_book", {"equity": 100.0})
    assert models.intraday_state_get("paper_book") == {"equity": 100.0}
    models.intraday_state_set("paper_book", {"equity": 99.5})
    assert models.intraday_state_get("paper_book") == {"equity": 99.5}


def test_trade_open_close_roundtrip(mem_db):
    tid = models.log_intraday_trade(
        symbol="DOGEUSDT", mode="paper", limit_price=0.1, entry_price=0.1,
        slot_usd=10.0, entry_time="2026-07-16T00:00:00+00:00",
        fill_type="trade_through",
    )
    models.close_intraday_trade(
        tid, exit_price=0.11, exit_time="2026-07-16T08:00:00+00:00",
        hold_bars=32, pnl_pct=0.1, pnl_usd=1.0, exit_reason="horizon",
    )
    from sqlalchemy.orm import Session
    with Session(mem_db) as s:
        row = s.get(models.IntradayTrade, tid)
        assert row.status == "closed" and row.pnl_usd == 1.0
        assert row.direction == "long"


def test_limit_telemetry_row(mem_db):
    models.log_intraday_limit(
        symbol="DOGEUSDT", limit_price=0.1, placed_at="2026-07-16T00:00:00+00:00",
        resolved_at="2026-07-16T00:15:00+00:00", outcome="touch_only",
        bar_low=0.1, admitted=False,
    )
    from sqlalchemy.orm import Session
    with Session(mem_db) as s:
        row = s.query(models.IntradayLimit).one()
        assert row.outcome == "touch_only" and row.admitted is False
