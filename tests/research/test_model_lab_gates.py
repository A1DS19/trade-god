"""The stop rule (spec §3.4): on the validation period, G1 needs a strictly higher weekly Sharpe
than BTC's and G2 a daily drawdown no deeper than BTC's."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.signals.model_lab import gates

DAY = 86_400_000
MONDAY = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _daily(values):
    return pd.Series(values, index=MONDAY + np.arange(len(values)) * DAY, dtype=float)


BTC = _daily(np.tile([0.02, -0.01, 0.0, 0.0, 0.01, -0.02, 0.0], 8)[:-1] + 0.001 * np.arange(55))


def test_the_same_book_passes_g2_but_not_g1():
    assert gates.stop_rule(BTC, BTC) == {"G1": False, "G2": True}  # ties: > fails, ≤ holds


def test_a_flat_book_has_no_sharpe_and_fails_g1():
    assert gates.stop_rule(_daily(np.zeros(55)), BTC) == {"G1": False, "G2": True}


def test_a_better_book_passes_both():
    assert gates.stop_rule(BTC + 0.002, BTC) == {"G1": True, "G2": True}


def test_a_deeper_drawdown_fails_g2():
    worse = BTC.copy()
    worse.iloc[3] = -0.30
    assert gates.stop_rule(worse, BTC)["G2"] is False
