"""The quarterly refit schedule, with purged labels and an embargo (spec 2026-10-02 §2.4).

A row is daily bar t, keyed by its open_time. Its decision is made when the bar closes, at t + 1
day, and its 7-day label is known at t + 8 days. A refit at R trains on a row only if that label
window ended at least 7 days before R: the spec's `t + 7d ≤ refit − 7d`, with t the decision
time."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.config import DAY_MS
from research.siglib.data import to_ms
from research.signals.model_lab.labels import HORIZON_DAYS

EMBARGO_DAYS = 7


def quarter_starts(start, end) -> list[int]:
    """Every quarter's first day from the quarter holding `start` up to `end` (exclusive), as
    epoch ms at 00:00 UTC. The first one is the refit in force at `start`."""
    first = pd.Timestamp(to_ms(start), unit="ms").to_period("Q").start_time
    days = pd.date_range(first, pd.Timestamp(to_ms(end), unit="ms"), freq="QS", inclusive="left")
    return [to_ms(day) for day in days]


def trains_refit(open_time, refit: int) -> np.ndarray:
    """Which rows a refit at `refit` may train on: label window over 7 days before it."""
    return np.asarray(open_time) + (1 + HORIZON_DAYS + EMBARGO_DAYS) * DAY_MS <= refit


def model_in_force(open_time, refits: list[int]) -> np.ndarray:
    """Each row's position in `refits` of the latest refit at or before its decision time
    (t + 1 day), or -1 before the first."""
    return np.searchsorted(np.asarray(refits), np.asarray(open_time) + DAY_MS, side="right") - 1
