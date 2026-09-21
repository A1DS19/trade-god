"""GET /intraday/fills — outcome distribution over intraday_limits."""

from __future__ import annotations

LIMIT = dict(symbol="DOGEUSDT", limit_price=0.1,
             placed_at="2026-07-16T17:00:00+00:00",
             resolved_at="2026-07-16T17:15:00+00:00")


def test_distribution(client, seed):
    seed("IntradayLimit", **LIMIT, outcome="trade_through", bar_low=0.09, admitted=True)
    seed("IntradayLimit", **LIMIT, outcome="trade_through", bar_low=0.09, admitted=False)
    seed("IntradayLimit", **LIMIT, outcome="touch_only", bar_low=0.1, admitted=False)
    seed("IntradayLimit", **LIMIT, outcome="miss", bar_low=0.11, admitted=False)
    seed("IntradayLimit", symbol="DOGEUSDT", limit_price=0.1,
         placed_at="2026-07-18T20:45:00+00:00")   # unresolved: outcome NULL

    f = client.get("/intraday/fills").json()
    assert f["total_placed"] == 5
    assert f["pending"] == 1
    assert f["admitted"] == 1
    assert f["by_outcome"]["trade_through"] == {"count": 2, "pct": 50.0}
    assert f["by_outcome"]["touch_only"] == {"count": 1, "pct": 25.0}
    assert f["by_outcome"]["miss"] == {"count": 1, "pct": 25.0}
    assert f["by_outcome"]["no_data"] == {"count": 0, "pct": 0.0}


def test_empty_db(client):
    f = client.get("/intraday/fills").json()
    assert f["total_placed"] == 0 and f["pending"] == 0
    assert f["by_outcome"]["trade_through"] == {"count": 0, "pct": 0.0}
