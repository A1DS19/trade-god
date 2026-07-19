"""GET / — self-contained HTML status page."""

from __future__ import annotations

from app.api import queries
from app.api.status_page import render_sparkline
from tests.api.conftest import CLOSED_TRADE

KS = {"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": False,
      "day": "2026-07-18", "day_anchor": 100.0, "peak": 102.0}


def _seed_full(seed, halted=False):
    seed("IntradayState", key="paper_book",
         value={"equity": 101.94, "slot_usd": 10.0, "pending": {},
                "positions": {"WLDUSDT": {"entry": 0.3599}}},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="killswitch", value={**KS, "halted": halted},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="universe",
         value={"symbols": ["WLDUSDT"], "refreshed_ms": 1784219517039},
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    seed("IntradayTrade", **{**CLOSED_TRADE, "symbol": "WLDUSDT", "pnl_usd": -0.25,
                             "exit_time": "2026-07-18T08:00:00+00:00"})


def test_realized_equity_curve(mem_db, seed):
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": 1.0})
    seed("IntradayTrade", **{**CLOSED_TRADE, "pnl_usd": -0.25,
                             "exit_time": "2026-07-18T08:00:00+00:00"})
    assert queries.realized_equity_curve() == [100.0, 101.0, 100.75]


def test_sparkline_svg():
    svg = render_sparkline([100.0, 101.0, 100.75])
    assert svg.startswith("<svg") and "polyline" in svg


def test_sparkline_needs_two_points():
    assert render_sparkline([100.0]) == ""


def test_page_renders_seeded_data(client, seed):
    _seed_full(seed)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "101.94" in body            # equity headline
    assert "WLDUSDT" in body           # open position + trade row
    assert "<svg" in body              # sparkline (3-point curve)
    assert "HALTED" not in body
    assert "realized basis" in body


def test_halted_badge(client, seed):
    _seed_full(seed, halted=True)
    assert "HALTED" in client.get("/").text


def test_empty_db_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "no data yet" in r.text.lower()
    assert "<svg" not in r.text
