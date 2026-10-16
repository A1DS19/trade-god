"""Labels and the walk-forward schedule (spec §2.2, §2.4): a row is daily bar t, decided at
t + 1 day; its label is known at t + 8 days; a refit at R trains on it only if t + 8 days ≤ R − 7
days, so no training label overlaps the 7 days before a refit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.signals.model_lab import walkforward as wf
from research.signals.model_lab.labels import up_label

DAY = 86_400_000
Q3 = 1_782_864_000_000  # 2026-07-01 00:00 UTC


def test_the_label_is_whether_the_close_seven_days_on_is_higher():
    close = pd.Series([10.0, 11, 9, 10, 10, 10, 10, 10, 12, 9, 10])
    # close[7] = 10 vs close[0] = 10 is not higher; close[8] = 12 > 11; close[9] = 9 = 9
    assert up_label(close).tolist()[:4] == [0.0, 1.0, 0.0, 0.0]
    assert up_label(close).iloc[4:].isna().all()  # close[t+7] not known yet


def test_quarter_starts_begin_with_the_quarter_in_force():
    days = wf.quarter_starts("2026-05-15", "2027-01-01")
    assert days == [Q3 - 91 * DAY, Q3, Q3 + 92 * DAY]  # 2026-04-01, 07-01, 10-01


def test_quarter_starts_exclude_the_end():
    assert wf.quarter_starts("2026-07-01", "2026-10-01") == [Q3]


def test_a_refit_trains_on_rows_whose_label_ended_seven_days_before_it():
    t = np.array([Q3 - 15 * DAY, Q3 - 14 * DAY])  # labels known on Q3 - 7 and Q3 - 6 days
    assert wf.trains_refit(t, Q3).tolist() == [True, False]


def test_no_training_label_overlaps_the_seven_days_before_a_refit():  # spec §4.4
    t = Q3 + np.arange(-400, 400) * DAY
    for refit in wf.quarter_starts(Q3 - 300 * DAY, Q3 + 300 * DAY):
        trained = t[wf.trains_refit(t, refit)]
        label_ends = trained + 8 * DAY
        assert (label_ends <= refit - 7 * DAY).all()
        assert trained.max() == refit - 15 * DAY  # and nothing older is lost


def test_a_decision_uses_the_refit_in_force_at_its_close():
    refits = [Q3 - 91 * DAY, Q3]
    t = np.array([Q3 - 93 * DAY, Q3 - 2 * DAY, Q3 - DAY, Q3 + 50 * DAY])
    # bar Q3 - 1 day closes at Q3, when the Q3 refit is in force
    assert wf.model_in_force(t, refits).tolist() == [-1, 0, 1, 1]
