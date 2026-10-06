"""The PIT universe (spec §1.2): 60 bars before d, a bar on d - 1, not excluded; ranked by the
30 days of quote volume ending d - 1; top 50; nothing when fewer than 20 are eligible."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.signals.model_lab import universe

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC, a Monday


def _listing(symbol, first_day, n_days, volume=1.0, ticker=None):
    return pd.DataFrame({"symbol": symbol, "ticker": ticker or symbol, "quote_volume": volume,
                         "open_time": [BASE + (first_day + i) * DAY for i in range(n_days)]})


def _at(day, *frames, excluded=frozenset()):
    return universe.build_universe(pd.concat(frames, ignore_index=True), [BASE + day * DAY],
                                   excluded=excluded)


@pytest.fixture
def one_is_enough(monkeypatch):
    monkeypatch.setattr(universe, "MIN_BREADTH", 1)


def test_mondays_are_utc_midnights_inside_the_range():
    assert universe.mondays("2024-01-03", "2024-01-30") == [BASE + d * DAY for d in (7, 14, 21, 28)]
    assert universe.mondays(BASE, BASE + 7 * DAY) == [BASE]


def test_a_listing_enters_with_its_60th_bar(one_is_enough):
    x = _listing("XUSDT", 0, 200)
    assert _at(59, x).empty  # 59 bars before d
    assert _at(60, x)["symbol"].tolist() == ["XUSDT"]


def test_a_listing_leaves_when_its_data_ends(one_is_enough):
    x = _listing("XUSDT", 0, 100)  # last bar on day 99
    assert _at(100, x)["symbol"].tolist() == ["XUSDT"]
    assert _at(101, x).empty  # no bar on d - 1


def test_the_top_n_by_30_day_volume_with_ties_broken_by_name(one_is_enough, monkeypatch):
    monkeypatch.setattr(universe, "TOP_N", 2)
    out = _at(100, _listing("CUSDT", 0, 100, 5.0), _listing("BUSDT", 0, 100, 9.0),
              _listing("AUSDT", 0, 100, 5.0), _listing("DUSDT", 0, 100, 1.0))
    assert out["symbol"].tolist() == ["BUSDT", "AUSDT"] and out["rank"].tolist() == [1, 2]
    assert out["quote_volume_30d"].tolist() == [270.0, 150.0]


def test_volume_outside_the_30_days_does_not_count(one_is_enough, monkeypatch):
    monkeypatch.setattr(universe, "TOP_N", 1)
    early_whale = pd.concat([_listing("WUSDT", 0, 69, 1e9), _listing("WUSDT", 69, 31, 1.0)])
    out = _at(100, early_whale, _listing("SUSDT", 0, 100, 2.0))
    assert out["symbol"].tolist() == ["SUSDT"]


def test_fewer_than_20_eligible_means_no_universe():
    nineteen = [_listing(f"S{i:02d}USDT", 0, 100) for i in range(19)]
    assert _at(100, *nineteen).empty
    assert len(_at(100, *nineteen, _listing("S19USDT", 0, 100))) == 20


def test_excluded_tickers_never_enter(one_is_enough):
    out = _at(100, _listing("USDCUSDT", 0, 100, 1e9), _listing("XUSDT", 0, 100),
              excluded=frozenset({"USDCUSDT"}))
    assert out["symbol"].tolist() == ["XUSDT"]


def test_an_excluded_ticker_stays_out_in_every_listing(one_is_enough):
    old = _listing("PAXGUSDT@2024-01-01", 0, 100, ticker="PAXGUSDT")
    assert _at(100, old, excluded=frozenset({"PAXGUSDT"})).empty


def test_future_bars_never_change_past_membership():  # spec §4.4 look-ahead
    rng = np.random.default_rng(20261002)
    frames = [_listing(f"S{i:02d}USDT", int(rng.integers(0, 60)), 300, float(rng.uniform(1, 100)))
              for i in range(40)]
    dates = [BASE + d * DAY for d in range(70, 300, 7)]
    before = universe.build_universe(pd.concat(frames, ignore_index=True), dates, excluded=frozenset())
    cutoff = BASE + 180 * DAY
    perturbed = []
    for f in frames:
        f = f.copy()
        future = f["open_time"] >= cutoff
        f.loc[future, "quote_volume"] = rng.uniform(1, 1e6, int(future.sum()))
        perturbed.append(f[~future | (rng.random(len(f)) > 0.3)])  # some future bars vanish too
    perturbed.append(_listing("NEWUSDT", 175, 100, 1e9))  # a newcomer, eligible only after cutoff
    after = universe.build_universe(pd.concat(perturbed, ignore_index=True), dates, excluded=frozenset())
    pd.testing.assert_frame_equal(before[before["decision_time"] <= cutoff].reset_index(drop=True),
                                  after[after["decision_time"] <= cutoff].reset_index(drop=True))
