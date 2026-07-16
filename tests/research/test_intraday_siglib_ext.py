"""siglib extensions for the intraday edge-hunt: taker columns, abs-mode
event study, spec cost model (5 bps taker + 3 bps slippage per side)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import store
from research.siglib import costs
from research.siglib import data as sdata
from research.siglib.events import event_study


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def test_intraday_cost_model():
    assert costs.INTRADAY.taker_bps == 5.0
    assert costs.INTRADAY.slippage_bps == 3.0
    assert costs.INTRADAY.cost_per_side == pytest.approx(0.0008)


def test_load_klines_returns_taker_columns(warehouse):
    rows = [{
        "open_time": i * 900_000, "open": 1.0, "high": 1.0, "low": 1.0,
        "close": 1.0, "volume": 10.0, "quote_volume": 10.0,
        "taker_buy_volume": 6.0, "trades": 3,
    } for i in range(4)]
    store.upsert("klines_15m", "AAAUSDT", rows, "open_time")

    df = sdata.load_klines("AAAUSDT", interval="15m")

    assert "taker_buy_volume" in df.columns
    assert "trades" in df.columns
    assert df["taker_buy_volume"].iloc[0] == 6.0


def test_event_study_absolute_mode():
    idx = pd.Index(range(0, 10_000, 100), name="open_time")
    up = 1.02 ** np.arange(len(idx))
    down = 0.98 ** np.arange(len(idx))
    close = pd.DataFrame({"UP": up, "DOWN": down}, index=idx)
    buckets = pd.DataFrame("all", index=idx, columns=close.columns)

    signed = event_study(close, buckets, horizons_hours=(1,))
    absolute = event_study(close, buckets, horizons_hours=(1,), absolute=True)

    # signed: +2% and -2% average out near zero; absolute: mean ~2%
    assert abs(signed["mean"].iloc[0]) < 0.005
    assert absolute["mean"].iloc[0] == pytest.approx(0.02, abs=0.001)
