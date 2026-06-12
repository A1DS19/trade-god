"""Golden tests for siglib.data: loading, panels, 60-day eligibility."""

import numpy as np
import pandas as pd
import pytest

from research import config
from research.siglib import data

HOUR = config.HOUR_MS
DAY = config.DAY_MS
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


@pytest.fixture
def tmp_warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


def _write(tmp_warehouse, dataset, symbol, df):
    d = tmp_warehouse / dataset
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{symbol}.parquet", index=False)


def _klines(times, closes):
    return pd.DataFrame(
        {
            "open_time": times,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(times),
            "close_time": [t + HOUR - 1 for t in times],  # extra col, must be dropped
            "quote_volume": [2.0] * len(times),
            "trades": [3] * len(times),
        }
    )


def test_load_klines_columns_filtering_and_all(tmp_warehouse):
    times = [BASE, BASE + HOUR, BASE + 2 * HOUR]
    _write(tmp_warehouse, "klines_1h", "AAAUSDT", _klines(times, [1.0, 2.0, 3.0]))
    _write(tmp_warehouse, "klines_1h", "BBBUSDT", _klines(times, [10.0, 20.0, 30.0]))

    df = data.load_klines("all", "1h")
    assert sorted(df["symbol"].unique()) == ["AAAUSDT", "BBBUSDT"]
    assert list(df.columns) == ["symbol", *data.KLINE_COLS]

    # start inclusive, end exclusive; datetime-like accepted
    df = data.load_klines("AAAUSDT", "1h", start=BASE + HOUR, end=BASE + 2 * HOUR)
    assert df["open_time"].tolist() == [BASE + HOUR]
    df2 = data.load_klines(
        ["AAAUSDT"], "1h", start="2024-01-01 01:00", end="2024-01-01 02:00"
    )
    assert df2["open_time"].tolist() == [BASE + HOUR]


def test_load_funding_and_premium(tmp_warehouse):
    fund = pd.DataFrame(
        {
            "funding_time": [BASE + 17, BASE + 8 * HOUR + 23],  # ms jitter preserved
            "funding_rate": [0.0001, -0.0002],
            "mark_price": [1.0, 1.1],
        }
    )
    _write(tmp_warehouse, "funding", "AAAUSDT", fund)
    df = data.load_funding("AAAUSDT")
    assert list(df.columns) == ["symbol", *data.FUNDING_COLS]
    assert df["funding_time"].tolist() == [BASE + 17, BASE + 8 * HOUR + 23]

    prem = pd.DataFrame(
        {
            "open_time": [BASE],
            "open": [0.0001],
            "high": [0.0002],
            "low": [0.0],
            "close": [0.0001],
            "close_time": [BASE + HOUR - 1],
        }
    )
    _write(tmp_warehouse, "premium_index_1h", "AAAUSDT", prem)
    df = data.load_premium("AAAUSDT")
    assert list(df.columns) == ["symbol", *data.PREMIUM_COLS]


def test_to_ms_treats_floats_as_epoch_ms():
    """Audit pin: floats arise from numpy arithmetic on ms indices. They used
    to fall through to pd.Timestamp, which reads bare floats as NANOSECONDS ->
    silent 1970 timestamps -> window() slices that include/exclude everything."""
    assert data.to_ms(float(BASE)) == BASE
    assert data.to_ms(np.float64(BASE)) == BASE
    assert data.to_ms(BASE + 0.4) == BASE
    with pytest.raises(ValueError):
        data.to_ms(float("nan"))


def test_to_panel_pivots_wide():
    df = pd.DataFrame(
        {
            "symbol": ["A", "A", "B"],
            "open_time": [BASE, BASE + HOUR, BASE],
            "close": [1.0, 2.0, 10.0],
        }
    )
    panel = data.to_panel(df, "close")
    assert list(panel.columns) == ["A", "B"]
    assert panel.loc[BASE, "A"] == 1.0
    assert panel.loc[BASE + HOUR, "A"] == 2.0
    assert pd.isna(panel.loc[BASE + HOUR, "B"])


def test_eligible_mask_60_day_rule():
    # OLD listed 100d before BASE; NEW listed 10d before BASE.
    rows = []
    for t in [BASE - 100 * DAY, BASE - 40 * DAY, BASE, BASE + HOUR]:
        rows.append({"symbol": "OLD", "open_time": t})
    for t in [BASE - 10 * DAY, BASE, BASE + HOUR, BASE + 50 * DAY]:
        rows.append({"symbol": "NEW", "open_time": t})
    mask = data.eligible_mask(pd.DataFrame(rows))

    # OLD becomes eligible at first_bar + 60d = BASE - 40d, not before.
    assert not mask.loc[BASE - 100 * DAY, "OLD"]
    assert mask.loc[BASE - 40 * DAY, "OLD"]
    assert mask.loc[BASE, "OLD"]
    # NEW (10d of history at BASE) is ineligible until BASE + 50d exactly.
    assert not mask.loc[BASE, "NEW"]
    assert not mask.loc[BASE + HOUR, "NEW"]
    assert mask.loc[BASE + 50 * DAY, "NEW"]
