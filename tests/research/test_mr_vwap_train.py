"""Train-runner smoke test on a synthetic warehouse + unit test of the
mechanical selection rule (eligibility, Sharpe ranking, plateau guard)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from research import store
from research.signals.intraday import mr_vwap_train as train

BAR_MS = 900_000
DAY_MS = 86_400_000
N = 4000


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _seed(symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT")):
    rng = np.random.default_rng(9)
    for sym in symbols:
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.004, N))
        vol = rng.uniform(5, 50, N)
        rows = [{
            "open_time": i * BAR_MS, "open": float(closes[i]),
            "high": float(closes[i] * 1.001), "low": float(closes[i] * 0.999),
            "close": float(closes[i]), "volume": float(vol[i]),
            "close_time": i * BAR_MS + BAR_MS - 1,
            "quote_volume": float(closes[i] * vol[i]), "trades": 5,
            "taker_buy_volume": float(vol[i] * 0.5), "taker_buy_quote_volume": 0.0,
        } for i in range(N)]
        store.upsert("klines_15m", sym, rows, "open_time")
        days = N * BAR_MS // DAY_MS + 1
        drows = [{"open_time": d * DAY_MS, "close": 100.0,
                  "quote_volume": 1e6} for d in range(days)]
        store.upsert("klines_1d", sym, drows, "open_time")
        frows = [{"funding_time": t, "funding_rate": 0.0001, "mark_price": 100.0}
                 for t in range(0, N * BAR_MS, 32 * BAR_MS)]
        store.upsert("funding", sym, frows, "funding_time")


def test_select_frozen_params_mechanical_rule():
    log = pd.DataFrame([
        {"fill": "next_bar", "horizon_bars": 8, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.10, "sharpe": 2.0},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.20, "sharpe": 3.0},
        {"fill": "next_bar", "horizon_bars": 32, "exit": "horizon", "max_k": 3,
         "n_trades": 200, "total_return": 0.05, "sharpe": 1.0},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 5,
         "n_trades": 200, "total_return": 0.15, "sharpe": 2.5},
        {"fill": "next_bar", "horizon_bars": 16, "exit": "horizon", "max_k": 10,
         "n_trades": 50, "total_return": 0.30, "sharpe": 9.9},  # ineligible: trades
    ])
    chosen, cliff = train.select_frozen(log[log.fill == "next_bar"])
    assert chosen["horizon_bars"] == 16 and chosen["max_k"] == 3
    assert not cliff

    none_eligible = log.assign(total_return=-1.0)
    assert train.select_frozen(none_eligible) == (None, False)


def test_train_cli_end_to_end(warehouse, tmp_path, monkeypatch):
    _seed()
    out = tmp_path / "2b"
    monkeypatch.setattr(train.sdata, "ELIGIBILITY_DAYS", 0)
    monkeypatch.setattr(train, "GRID_H", [4])
    monkeypatch.setattr(train, "GRID_K", [2])
    monkeypatch.setattr(train, "MIN_TRAIN_TRADES", 1)
    monkeypatch.setattr("sys.argv", ["train", "--out", str(out)])

    train.main()

    log = pd.read_csv(out / "combo_log.csv")
    assert len(log) == 4                      # 1 H x 2 exits x 1 K x 2 variants
    frozen = json.loads((out / "frozen_params.json").read_text())
    assert set(frozen) == {"next_bar", "maker_limit"}
    assert (out / "diag_summary.json").exists()
