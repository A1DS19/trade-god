"""App assembly: /health frozen, legacy endpoints relocated, old paths gone."""

from __future__ import annotations

from tests.api.conftest import CLOSED_TRADE


def test_health_unchanged(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_legacy_dca_portfolio_relocated(client, seed):
    seed("Position", coin="BTC", avg_buy=50000.0, qty=0.01)
    r = client.get("/legacy/dca/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["positions"][0]["coin"] == "BTC"
    assert body["total_cost_usd"] == 500.0


def test_legacy_swing_stats_relocated(client):
    r = client.get("/legacy/swing/stats")
    assert r.status_code == 200
    assert r.json()["trades"] == 0


def test_all_six_legacy_paths_respond(client):
    for path in (
        "/legacy/dca/portfolio", "/legacy/dca/pnl", "/legacy/dca/trades",
        "/legacy/dca/stats", "/legacy/swing/trades", "/legacy/swing/stats",
    ):
        assert client.get(path).status_code == 200, path


def test_old_paths_are_gone(client):
    for path in ("/portfolio", "/pnl", "/trades", "/stats", "/swing/trades", "/swing/stats"):
        assert client.get(path).status_code == 404, path
