"""GET /intraday/state — deserialized engine state with derived percentages."""

from __future__ import annotations

BOOK = {"equity": 101.9396, "max_k": 10, "horizon_bars": 32, "entry_cost": 0.0002,
        "exit_cost": 0.0008, "slot_usd": 10.0, "pending": {},
        "positions": {"WLDUSDT": {"entry": 0.3599, "bars": 5}}}
KS = {"daily_loss_pct": 0.05, "max_dd_pct": 0.2, "halted": False,
      "day": "2026-07-18", "day_anchor": 100.2878, "peak": 102.0052}
UNI = {"symbols": ["BTCUSDT", "ETHUSDT"], "refreshed_ms": 1784219517039}


def _seed_state(seed, book=BOOK, ks=KS, uni=UNI):
    seed("IntradayState", key="paper_book", value=book,
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="killswitch", value=ks,
         updated="2026-07-18T20:30:23+00:00")
    seed("IntradayState", key="universe", value=uni,
         updated="2026-07-18T20:30:23+00:00")


def test_state_deserialized_with_derived_pcts(client, seed):
    _seed_state(seed)
    s = client.get("/intraday/state").json()
    assert s["equity"] == 101.9396
    assert s["slot_usd"] == 10.0
    assert "WLDUSDT" in s["positions"]
    assert s["killswitch"]["halted"] is False
    # 101.9396/100.2878 - 1 = +1.64706% ; 101.9396/102.0052 - 1 = -0.06431%
    assert s["killswitch"]["day_pnl_pct"] == 1.6471
    assert s["killswitch"]["drawdown_from_peak_pct"] == -0.0643
    assert s["universe"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert s["universe"]["age_days"] is not None
    assert s["updated"]["paper_book"] == "2026-07-18T20:30:23+00:00"
    assert "warning" not in s


def test_missing_rows_yield_nulls_not_500(client):
    s_resp = client.get("/intraday/state")
    assert s_resp.status_code == 200
    s = s_resp.json()
    assert s["equity"] is None
    assert s["positions"] == {} and s["pending"] == {}
    assert s["killswitch"]["halted"] is None
    assert s["universe"]["symbols"] == []


def test_unreadable_state_row_warns_not_500(client, seed):
    seed("IntradayState", key="paper_book", value=["not", "a", "dict"],
         updated="2026-07-18T20:30:23+00:00")
    s = client.get("/intraday/state").json()
    assert s["equity"] is None
    assert "paper_book" in s["warning"]
