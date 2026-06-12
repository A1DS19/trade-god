"""Golden tests for siglib.event_study on hand-computable panels."""

import numpy as np
import pandas as pd
import pytest

HOUR = 3_600_000
BASE = 1_704_067_200_000

from research.siglib.events import event_study


def test_event_study_hand_computed_two_symbols():
    times = [BASE + i * HOUR for i in range(4)]
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0, 133.1], "B": [100.0, 120.0, 144.0, 172.8]},
        index=pd.Index(times, name="open_time"),
    )
    # Single bucket "x" observed at t0 for both symbols; NaN elsewhere (excluded).
    sig = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)
    sig.loc[times[0], "A"] = "x"
    sig.loc[times[0], "B"] = "x"

    out = event_study(close, sig, horizons_hours=[1, 2])

    h1 = out[(out["horizon_hours"] == 1) & (out["bucket"] == "x")].iloc[0]
    fwd1 = np.array([110.0 / 100.0 - 1.0, 120.0 / 100.0 - 1.0])  # [0.1, 0.2]
    assert h1["count"] == 2
    assert h1["mean"] == pytest.approx(fwd1.mean(), abs=1e-15)
    assert h1["median"] == pytest.approx(np.median(fwd1), abs=1e-15)
    assert h1["std"] == pytest.approx(fwd1.std(ddof=1), abs=1e-15)
    expected_t = fwd1.mean() / (fwd1.std(ddof=1) / np.sqrt(2))
    assert h1["t_stat"] == pytest.approx(expected_t, rel=1e-12)  # = 3.0

    h2 = out[(out["horizon_hours"] == 2) & (out["bucket"] == "x")].iloc[0]
    fwd2 = np.array([121.0 / 100.0 - 1.0, 144.0 / 100.0 - 1.0])
    assert h2["count"] == 2
    assert h2["mean"] == pytest.approx(fwd2.mean(), abs=1e-15)


def test_event_study_drops_nan_signal_and_missing_forward():
    times = [BASE + i * HOUR for i in range(3)]
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0]}, index=pd.Index(times, name="open_time")
    )
    sig = pd.DataFrame(
        {"A": [0, 0, 0]}, index=close.index
    )  # signal at every bar, but t2 has no 1h-forward return
    out = event_study(close, sig, horizons_hours=[1])
    assert out.iloc[0]["count"] == 2  # t2 excluded: close[t+1] unavailable
