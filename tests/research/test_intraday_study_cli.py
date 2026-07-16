"""End-to-end smoke test on a tiny synthetic warehouse: the CLI runs all six
families, writes per-family stats, one checks.csv, and verdicts.json."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research import store
from research.signals.intraday import study

BAR_MS = 900_000
N = 1200


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _seed_warehouse():
    rng = np.random.default_rng(21)
    for sym in ("AAAUSDT", "BBBUSDT", "CCCUSDT"):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.004, N))
        vol = rng.uniform(5, 50, N)
        rows = [{
            "open_time": i * BAR_MS, "open": float(closes[i]),
            "high": float(closes[i]), "low": float(closes[i]),
            "close": float(closes[i]), "volume": float(vol[i]),
            "close_time": i * BAR_MS + BAR_MS - 1,
            "quote_volume": float(closes[i] * vol[i]), "trades": 5,
            "taker_buy_volume": float(vol[i] * rng.uniform(0.3, 0.7)),
            "taker_buy_quote_volume": 0.0,
        } for i in range(N)]
        store.upsert("klines_15m", sym, rows, "open_time")
        frows = [{"funding_time": t, "funding_rate": float(rng.normal(0, 2e-4)),
                  "mark_price": 100.0}
                 for t in range(0, N * BAR_MS, 32 * BAR_MS)]
        store.upsert("funding", sym, frows, "funding_time")


def test_study_cli_end_to_end(warehouse, tmp_path, monkeypatch):
    _seed_warehouse()
    out = tmp_path / "out"
    monkeypatch.setattr(study.sdata, "ELIGIBILITY_DAYS", 0)
    monkeypatch.setattr("sys.argv", ["study", "--out", str(out)])

    study.main()

    verdicts = json.loads((out / "verdicts.json").read_text())
    assert set(verdicts) == {
        "breakout", "mr_vwap", "squeeze", "funding_window",
        "vol_impulse", "time_of_day",
    }
    assert set(verdicts.values()) <= {"SURVIVOR", "REJECTED"}
    checks = pd.read_csv(out / "checks.csv")
    # extreme buckets may simply never fire in a small random panel, so a
    # family can legitimately contribute zero check rows — subset, not equality
    assert set(checks["family"]) <= set(verdicts)
    assert len(checks) > 0          # time_of_day alone guarantees rows
    for fam in verdicts:
        assert (out / f"{fam}_event_study.csv").exists()
