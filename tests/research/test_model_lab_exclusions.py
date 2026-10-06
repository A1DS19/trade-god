"""The exclusion list (spec §1.1) is a frozen set of tickers reviewed by the owner. These tests
pin its shape and its reviewed size: any edit to the list has to change them, in plain sight."""

from __future__ import annotations

from research.signals.model_lab import exclusions as ex


def test_the_categories_are_disjoint_and_make_up_the_whole():
    groups = [ex.STABLECOINS, ex.PEGGED, ex.INDEXES, ex.TRADFI]
    assert sum(len(g) for g in groups) == len(ex.EXCLUDED)
    assert frozenset().union(*groups) == ex.EXCLUDED


def test_every_entry_is_a_usdt_perp_ticker():
    assert all(t.endswith("USDT") and "_" not in t for t in ex.EXCLUDED)


def test_the_reviewed_sizes():  # a change here is a change the owner reviews again
    assert (len(ex.STABLECOINS), len(ex.PEGGED), len(ex.INDEXES), len(ex.TRADFI)) == (1, 2, 6, 212)
