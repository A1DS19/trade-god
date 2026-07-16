"""Pre-registered survivor rule: planted edges pass, null noise fails,
split-half sign flips fail, thin buckets fail."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.intraday import harness
from research.signals.intraday.harness import FamilySpec

N_BARS = 3000
BAR_MS = 900_000
IDX = pd.Index(np.arange(N_BARS) * BAR_MS, name="open_time")
SYMS = ["AAAUSDT", "BBBUSDT"]


def _spec(extreme_sign=1, middle=("M",), abs_mode=False):
    return FamilySpec(
        name="synthetic", build=lambda data: None,
        extreme={"X": extreme_sign}, middle=list(middle),
        horizons_bars=(4,), abs_mode=abs_mode,
    )


def _panels(drift_after_x: float, flip_second_half: bool = False, n_x: int = 300):
    """Close panel + bucket panel: bucket X fires n_x times per symbol (spaced
    ~10 bars so 4-bar drift windows never overlap adjacent events); each firing
    is followed by `drift_after_x` return over the next 4 bars."""
    rng = np.random.default_rng(7)
    close = pd.DataFrame(100.0, index=IDX, columns=SYMS)
    buckets = pd.DataFrame("M", index=IDX, columns=SYMS)
    x_bars = np.linspace(10, N_BARS - 10, n_x, dtype=int)
    for sym in SYMS:
        prices = np.full(N_BARS, 100.0)
        noise = rng.normal(0, 1e-5, N_BARS)
        step = np.zeros(N_BARS)
        for t in x_bars:
            d = drift_after_x
            if flip_second_half and t > N_BARS // 2:
                d = -drift_after_x
            step[t + 1: t + 5] += d / 4.0
        prices = 100.0 * np.cumprod(1.0 + step + noise)
        close[sym] = prices
        buckets.loc[IDX[x_bars], sym] = "X"
    return close, buckets


def test_planted_edge_survives():
    close, buckets = _panels(drift_after_x=0.01)
    stats, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "SURVIVOR"
    row = checks.iloc[0]
    assert row["passes"]
    assert row["edge"] > harness.ROUND_TRIP
    assert row["count"] >= harness.MIN_COUNT


def test_null_noise_rejected():
    close, buckets = _panels(drift_after_x=0.0)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"
    assert not checks["passes"].any()


def test_split_half_sign_flip_rejected():
    close, buckets = _panels(drift_after_x=0.02, flip_second_half=True)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"


def test_thin_bucket_rejected():
    close, buckets = _panels(drift_after_x=0.01, n_x=100)
    _, checks, verdict = harness.evaluate_family(_spec(), close, buckets)
    assert verdict == "REJECTED"
    assert (checks["count"] < harness.MIN_COUNT).all()


def test_wrong_direction_rejected():
    close, buckets = _panels(drift_after_x=0.01)
    _, _, verdict = harness.evaluate_family(_spec(extreme_sign=-1), close, buckets)
    assert verdict == "REJECTED"


def test_data_determined_sign_passes_either_direction():
    close, buckets = _panels(drift_after_x=-0.01)
    _, checks, verdict = harness.evaluate_family(_spec(extreme_sign=0), close, buckets)
    assert verdict == "SURVIVOR"
    assert checks.iloc[0]["direction"] == -1


def test_abs_mode_detects_movement_without_direction():
    close, buckets = _panels(drift_after_x=0.01, flip_second_half=True)
    _, _, verdict = harness.evaluate_family(
        _spec(abs_mode=True), close, buckets
    )
    assert verdict == "SURVIVOR"


def test_none_middle_uses_all_other_buckets():
    close, buckets = _panels(drift_after_x=0.01)
    spec = FamilySpec(
        name="synthetic", build=lambda data: None,
        extreme={"X": 1}, middle=None, horizons_bars=(4,),
    )
    _, checks, verdict = harness.evaluate_family(spec, close, buckets)
    assert verdict == "SURVIVOR"


def test_absent_declared_bucket_still_reported():
    close, buckets = _panels(drift_after_x=0.01)
    spec = FamilySpec(
        name="synthetic", build=lambda data: None,
        extreme={"NEVER": 1}, middle=["M"], horizons_bars=(4,),
    )
    _, checks, verdict = harness.evaluate_family(spec, close, buckets)
    assert verdict == "REJECTED"
    assert len(checks) == 1
    row = checks.iloc[0]
    assert row["bucket"] == "NEVER" and not row["passes"] and row["count"] == 0


def test_cut_panel_labels_and_shape():
    panel = pd.DataFrame({"AAAUSDT": [0.05, 0.5, 0.95, np.nan]},
                         index=pd.Index([0, 1, 2, 3], name="open_time"))
    out = harness.cut_panel(panel, [0.0, 0.1, 0.9, 1.0001], ["lo", "mid", "hi"])
    assert list(out["AAAUSDT"][:3]) == ["lo", "mid", "hi"]
    assert pd.isna(out["AAAUSDT"].iloc[3])
    assert out.shape == panel.shape
