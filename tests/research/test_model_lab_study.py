"""The validation study (spec §2.4, §3.4): four trials logged, the higher validation Sharpe kept
(ties to S1), the stop rule applied, every constant frozen, and nothing read from the sealed
windows."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from research.signals.model_lab import study

SEALED = pd.Timestamp(study.VALIDATION_END, tz="UTC").value // 1_000_000


@pytest.fixture
def fast_trees(monkeypatch):
    small = {name: {**s, "n_estimators": 10} for name, s in study.models.SETTINGS.items()}
    monkeypatch.setattr(study.models, "SETTINGS", small)


@pytest.fixture
def market(warehouse, spot_market, monkeypatch, tmp_path):
    """A synthetic spot warehouse running a year into the sealed windows, and a scratch output."""
    daily, hourly = spot_market(4, end="2024-07-01")
    monkeypatch.setattr(study, "OUTPUT", tmp_path / "output")

    def write(frames):
        for interval, by_symbol in frames.items():
            folder = warehouse / f"archive_spot_klines_{interval}"
            folder.mkdir(parents=True, exist_ok=True)
            for symbol, bars in by_symbol.items():
                bars.to_parquet(folder / f"{symbol}.parquet", index=False)

    write({"1d": daily, "1h": hourly})
    return write, daily, hourly


def test_the_study_logs_four_trials_and_freezes_both_arms(market, fast_trees):
    study.main()
    log = pd.read_csv(study.OUTPUT / "combo_log.csv")
    assert list(zip(log["arm"], log["setting"])) == [("btc", "S1"), ("btc", "S2"),
                                                    ("eth", "S1"), ("eth", "S2")]
    assert log["weeks"].tolist() == [103] * 4  # complete Monday weeks in the validation period
    for arm, asset in (("btc", "BTCUSDT"), ("eth", "ETHUSDT")):
        frozen = json.loads((study.OUTPUT / arm / "frozen_params.json").read_text())
        assert frozen["asset"] == asset
        assert frozen["setting"] == study.choose(log[log["arm"] == arm])
        assert frozen["status"] == ("frozen" if frozen["validation"]["G1"]
                                    and frozen["validation"]["G2"] else "failed_on_validation")
        assert frozen["lightgbm_params"]["random_state"] == 20261002
        assert len(frozen["features"]) == 21
        assert frozen["data"] == {"source": "archive_spot_klines", "daily": "1d", "hourly": "1h"}
        assert frozen["constants"]["har_windows"] == {"rv_d": 1, "rv_w": 7, "rv_m": 30}


def test_the_study_never_reads_the_sealed_windows(market, fast_trees):  # spec §2.4
    write, daily, hourly = market
    study.main()
    first = (study.OUTPUT / "combo_log.csv").read_text()
    for frames in (daily, hourly):
        for bars in frames.values():
            bars.loc[bars["open_time"] >= SEALED, ["close", "quote_volume"]] *= 3.0
    write({"1d": daily, "1h": hourly})
    study.main()
    assert (study.OUTPUT / "combo_log.csv").read_text() == first


def test_a_sealed_bar_stops_the_study(monkeypatch):
    late = pd.DataFrame({"open_time": [SEALED]})
    monkeypatch.setattr(study, "load_klines", lambda *args, **kwargs: late)
    with pytest.raises(RuntimeError, match="sealed"):
        study.load_spot()


@pytest.mark.parametrize("s1, s2, kept", [
    (0.5, 0.5, "S1"),         # a tie goes to S1
    (0.4, 0.5, "S2"),
    (math.nan, 0.1, "S2"),    # a missing Sharpe ranks below any number
    (math.nan, math.nan, "S1"),
])
def test_the_higher_validation_sharpe_is_kept(s1, s2, kept):
    rows = pd.DataFrame({"setting": ["S1", "S2"], "sharpe": [s1, s2]})
    assert study.choose(rows) == kept
