"""Reconciliation (spec §1.1): shared days must agree within 1e-9 relative, and a REST day the
archive lacks fails too, because a missing day would end a live coin's listing."""

from __future__ import annotations

from research import archive_reconcile as rec
from research import store

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _days(dataset, symbol, closes, first=0):
    rows = [{"open_time": BASE + (first + i) * DAY, "close": c} for i, c in enumerate(closes)]
    store.upsert(dataset, symbol, rows, "open_time")


def test_identical_closes_pass(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0, 102.0])
    report = rec.reconcile()
    assert report["symbols"] == 1 and report["days"] == 3
    assert report["mismatches"] == [] and report["missing"] == []


def test_a_planted_mismatch_is_caught(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0001, 102.0])
    [m] = rec.reconcile()["mismatches"]
    assert m["symbol"] == "BTCUSDT" and m["open_time"] == BASE + DAY


def test_float_noise_inside_the_tolerance_passes(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0 * (1 + 1e-12)])
    assert rec.reconcile()["mismatches"] == []


def test_a_rest_day_the_archive_lacks_is_caught(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0])
    _days(rec.ARCHIVE, "BTCUSDT", [100.0])
    _days(rec.ARCHIVE, "BTCUSDT", [102.0], first=2)
    assert rec.reconcile()["missing"] == [("BTCUSDT", BASE + DAY)]


def test_rest_days_after_the_archive_ends_are_not_missing(warehouse):
    _days(rec.REST, "BTCUSDT", [100.0, 101.0, 102.0, 103.0])  # REST runs into the current month
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0])  # the archive stops at the last full month
    report = rec.reconcile()
    assert report["missing"] == [] and report["days"] == 2


def test_rest_days_before_the_archive_starts_are_not_missing(warehouse):
    _days(rec.REST, "BTCUSDT", [99.0, 100.0, 101.0])  # REST's BTC starts 2019-09-09
    _days(rec.ARCHIVE, "BTCUSDT", [100.0, 101.0], first=1)  # the UM archive starts 2020-01
    report = rec.reconcile()
    assert report["missing"] == [] and report["days"] == 2


def test_symbols_in_only_one_store_are_skipped(warehouse):
    _days(rec.REST, "ETHUSDT", [1.0])
    _days(rec.ARCHIVE, "DEADUSDT", [1.0])
    assert rec.reconcile()["symbols"] == 0
