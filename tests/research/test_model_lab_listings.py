"""Listings (spec §1.2, as amended): settled folders fill only missing days, zero-trade days
are dropped, and a ticker splits wherever a contract ends or a day is missing.

Every fixture mirrors a real archive case from 2026-10-05, named in its test."""

from __future__ import annotations

import pandas as pd

from research.signals.model_lab import listings

DAY = 86_400_000
BASE = 1_704_067_200_000  # 2024-01-01 00:00 UTC


def _bars(symbol, first_day, n, close=1.0, trades=10):
    return [{"symbol": symbol, "open_time": BASE + (first_day + i) * DAY, "close": close,
             "trades": trades, "quote_volume": 100.0} for i in range(n)]


def _split(*groups):
    return listings.split_listings(pd.DataFrame([row for g in groups for row in g]))


def _days(out, name):
    return sorted((out.loc[out["symbol"] == name, "open_time"] - BASE) // DAY)


def test_a_relisting_after_a_zero_trade_halt_is_a_new_listing():  # PUMP, 2025
    out = _split(_bars("PUMPUSDT", 0, 10, close=0.0471),
                 _bars("PUMPUSDT", 10, 26, close=0.0471, trades=0),
                 _bars("PUMPUSDT", 36, 5, close=0.0052))
    assert sorted(out["symbol"].unique()) == ["PUMPUSDT", "PUMPUSDT@2024-01-01"]
    assert _days(out, "PUMPUSDT@2024-01-01") == list(range(10))
    assert _days(out, "PUMPUSDT") == list(range(36, 41))
    assert (out["ticker"] == "PUMPUSDT").all()


def test_a_settled_folder_fills_only_the_days_its_live_folder_lacks():  # BNX, 2022-23
    live_old = [r for r in _bars("BNXUSDT", 0, 10, close=120.0) if r["open_time"] != BASE + 4 * DAY]
    folder = (_bars("BNXUSDTSETTLED", 0, 10, close=999.0)  # duplicates the live days...
              + _bars("BNXUSDTSETTLED", 10, 3, close=119.9, trades=0))  # ...then halt and settle
    out = _split(live_old, folder, _bars("BNXUSDT", 12, 9, close=1.6))
    old = out[out["symbol"] == "BNXUSDT@2024-01-01"]
    assert _days(out, "BNXUSDT@2024-01-01") == list(range(10))
    assert old.loc[old["open_time"] == BASE + 4 * DAY, "close"].item() == 999.0  # the gap, filled
    assert set(old.loc[old["open_time"] != BASE + 4 * DAY, "close"]) == {120.0}  # live wins
    assert _days(out, "BNXUSDT") == list(range(12, 21))


def test_a_settled_folders_last_bar_separates_contracts_without_a_gap():  # MINA, 2023-02
    out = _split(_bars("MINAUSDT", 0, 9, close=0.80),
                 _bars("MINAUSDTSETTLED", 9, 1, close=0.78),  # old contract's last traded day
                 _bars("MINAUSDTSETTLED", 10, 1, close=0.78, trades=0),  # its settlement bar
                 _bars("MINAUSDT", 10, 11, close=0.86))  # the new contract, the very next day
    assert _days(out, "MINAUSDT@2024-01-01") == list(range(10))
    assert _days(out, "MINAUSDT") == list(range(10, 21))


def test_two_settled_folders_make_three_contracts():  # AERGO, 2025 and 2026
    out = _split(_bars("AERGOUSDT", 0, 5),
                 _bars("AERGOUSDTSETTLED", 8, 1, trades=0),
                 _bars("AERGOUSDT", 8, 8),
                 _bars("AERGOUSDTSETTLEDSETTLED", 20, 1))
    assert _days(out, "AERGOUSDT@2024-01-01") == list(range(5))
    assert _days(out, "AERGOUSDT@2024-01-09") == list(range(8, 16))
    assert _days(out, "AERGOUSDT") == [20]  # the old contract's last day, after a gap


def test_a_settled_contract_ends_at_its_last_traded_bar():  # BLZ: flat at 0.06836 since 2024-12
    out = _split(_bars("BLZUSDT", 0, 10, close=0.07), _bars("BLZUSDT", 10, 90, close=0.06836, trades=0))
    assert out["symbol"].unique().tolist() == ["BLZUSDT"]
    assert _days(out, "BLZUSDT") == list(range(10))


def test_a_continuous_ticker_is_one_listing_under_its_own_name():
    out = _split(_bars("BTCUSDT", 0, 30))
    assert out["symbol"].unique().tolist() == ["BTCUSDT"] and len(out) == 30


def test_a_missing_day_without_a_settled_folder_still_splits():  # conservative for data holes
    out = _split(_bars("XUSDT", 0, 5), _bars("XUSDT", 6, 5))
    assert sorted(out["symbol"].unique()) == ["XUSDT", "XUSDT@2024-01-01"]


def test_a_ticker_that_only_ever_halted_has_no_listing():
    assert _split(_bars("DEADUSDT", 0, 5, trades=0)).empty


def test_the_last_traded_close_is_the_halt_price():  # spec §1.2 delisting
    daily = pd.DataFrame(_bars("PUMPUSDT", 0, 3, close=0.0471) + _bars("PUMPUSDT", 3, 2, close=0.0471, trades=0))
    assert listings.settlement_mismatches(daily).empty
    planted = pd.DataFrame(_bars("XUSDT", 0, 3, close=2.0) + _bars("XUSDT", 3, 2, close=1.5, trades=0))
    [row] = listings.settlement_mismatches(planted).itertuples()
    assert row.close == 2.0 and row.halt_close == 1.5
