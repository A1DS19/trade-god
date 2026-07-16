"""The OOS judge is mechanical: pin every gate of the pre-registered pass bar."""

from __future__ import annotations

import pytest

from research.signals.intraday import mr_vwap_oos as oos

GOOD = {"profit_factor": 1.30, "n_trades": 250, "max_drawdown": 0.10}


def test_judge_passes_when_all_gates_pass():
    v = oos.judge(GOOD, [0.05, -0.01, 0.04])
    assert v == {"pf_ok": True, "trades_ok": True, "windows_ok": True,
                 "dd_ok": True, "passes": True}


@pytest.mark.parametrize("patch,expect_fail", [
    ({"profit_factor": 1.14}, "pf_ok"),
    ({"n_trades": 99}, "trades_ok"),
    ({"max_drawdown": 0.21}, "dd_ok"),
])
def test_judge_fails_each_gate(patch, expect_fail):
    v = oos.judge({**GOOD, **patch}, [0.05, -0.01, 0.04])
    assert not v[expect_fail] and not v["passes"]


def test_judge_requires_two_of_three_positive_windows():
    assert not oos.judge(GOOD, [0.05, -0.01, -0.04])["windows_ok"]
    assert oos.judge(GOOD, [0.05, 0.01, -0.04])["windows_ok"]


def test_pass_bar_constants():
    assert oos.MIN_PF == 1.15 and oos.MIN_TRADES == 100
    assert oos.MAX_DD == 0.20 and oos.OOS_START == "2025-07-01"


def test_judge_passes_exactly_at_thresholds():
    at_bar = {"profit_factor": 1.15, "n_trades": 100, "max_drawdown": 0.20}
    v = oos.judge(at_bar, [0.01, 0.01, -0.99])
    assert v["passes"]


def test_judge_windows_zero_return_is_not_positive():
    v = oos.judge(GOOD, [0.05, 0.0, -0.01])
    assert not v["windows_ok"]


def test_oos_window_boundaries_pinned():
    assert oos.OOS_WINDOWS == [("W1", "2025-07-01", "2025-11-01"),
                               ("W2", "2025-11-01", "2026-03-01"),
                               ("W3", "2026-03-01", None)]
