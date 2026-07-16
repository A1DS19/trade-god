"""The re-homed strategy core: z math identical to research, constants pinned,
research modules re-export from app (import direction: research -> app)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.intraday import strategy

BAR_MS = 900_000


def _panels(n=300, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.Index(np.arange(n) * BAR_MS, name="open_time")
    close = pd.DataFrame({"AAAUSDT": 100.0 + rng.normal(0, 0.05, n)}, index=idx)
    close.columns.name = "symbol"
    volume = pd.DataFrame({"AAAUSDT": np.full(n, 10.0)}, index=idx)
    volume.columns.name = "symbol"
    qv = close * volume
    qv.columns.name = "symbol"
    return close, volume, qv


def test_constants_frozen():
    assert strategy.Z_ENTRY == -3.0
    assert strategy.Z_RECOVER == -1.0
    assert strategy.Z_WINDOW == 96


def test_zscore_matches_research_mr_vwap_z():
    close, volume, qv = _panels()
    z_app = strategy.zscore(close, volume, qv)

    n = len(close)
    df = pd.DataFrame({
        "symbol": "AAAUSDT", "open_time": np.arange(n) * BAR_MS,
        "open": close["AAAUSDT"].to_numpy(), "high": close["AAAUSDT"].to_numpy(),
        "low": close["AAAUSDT"].to_numpy(), "close": close["AAAUSDT"].to_numpy(),
        "volume": 10.0, "quote_volume": (close["AAAUSDT"] * 10.0).to_numpy(),
        "taker_buy_volume": 5.0, "trades": 1,
    })
    from research.signals.intraday.families import mr_vwap_z
    z_research = mr_vwap_z({"klines_15m": df})
    pd.testing.assert_frame_equal(z_app, z_research, check_dtype=False)


def test_research_reexports_are_the_same_objects():
    from research.signals.intraday import mr_vwap_strategy as rs
    assert rs.build_weights is strategy.build_weights
    assert rs.Z_ENTRY is strategy.Z_ENTRY
