"""archive_backfill: every published month is fetched once, verified and stored; reruns resume;
a bad month is reported and retried, never stored."""

from __future__ import annotations

import threading
import time
from datetime import date
import urllib.error
import urllib.parse

import pytest

from research import archive_backfill as backfill
from research import store

UM = "data/futures/um/monthly/klines/"
AUGUST = "1785542400000,1,1,1,1,1,1785628799999,1,1,1,1,0\n"
SEPTEMBER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
    "taker_buy_quote_volume,ignore\n"
    "1788220800000,78549.60,79196.00,76368.00,77400.10,151357.832,1788307199999,"
    "11776717838.40160,3622828,72544.811,5646145648.39730,0\n"
)
FUNDING = "calc_time,funding_interval_hours,last_funding_rate\n1788220800000,8,0.00010000\n"
KLINES = {"archive_um_klines_1d": ["BTCUSDT"]}
DAY = 86_400_000
SEP1 = 1_788_220_800_000  # 2026-09-01 00:00 UTC


def _publish(archive, symbol, month, text, corrupt=False):
    archive.publish(f"{UM}{symbol}/1d/{symbol}-1d-{month}.zip", text, corrupt=corrupt)


def _publish_day(archive, symbol, day, text, corrupt=False):
    archive.publish(f"data/futures/um/daily/klines/{symbol}/1d/{symbol}-1d-{day}.zip", text,
                    corrupt=corrupt)


def _bars(*days):
    """Kline CSV rows for the given days of September 2026."""
    return "".join(f"{SEP1 + (d - 1) * DAY},1,1,1,1,1,{SEP1 + d * DAY - 1},1,1,1,1,0\n"
                   for d in days)


def test_first_run_stores_every_published_month(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == []
    assert summary.new_rows[("archive_um_klines_1d", "BTCUSDT")] == 2
    stored = store.load("archive_um_klines_1d", "BTCUSDT")
    assert list(stored["open_time"]) == [1785542400000, 1788220800000]


def test_rerun_downloads_only_what_is_missing(warehouse, archive):
    # August's bar is its last day, so no day is missing between it and September's.
    _publish(archive, "BTCUSDT", "2026-08", f"{SEP1 - DAY},1,1,1,1,1,{SEP1 - 1},1,1,1,1,0\n")
    backfill.run(KLINES, get=archive, delay=0)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)  # a month published later
    archive.urls.clear()
    backfill.run(KLINES, get=archive, delay=0)
    downloads = [u for u in archive.urls if u.startswith(backfill.src.ARCHIVE_URL)]
    assert len(downloads) == 2 and all("2026-09" in u for u in downloads)  # zip + checksum


def test_corrupt_month_is_reported_never_stored_and_retried(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST, corrupt=True)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == [("archive_um_klines_1d", "BTCUSDT", "2026-08")]
    assert list(store.load("archive_um_klines_1d", "BTCUSDT")["open_time"]) == [1788220800000]
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)  # republished intact
    assert backfill.run(KLINES, get=archive, delay=0).failures == []
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 2


@pytest.mark.parametrize("workers", [1, 4])
def test_a_listing_failure_stays_with_its_symbol(warehouse, archive, workers):
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)

    def flaky(url):
        if "BADUSDT" in urllib.parse.unquote(url):
            raise urllib.error.URLError("timed out")
        return archive(url)

    summary = backfill.run({"archive_um_klines_1d": ["BADUSDT", "BTCUSDT"]}, get=flaky, delay=0,
                           workers=workers)
    assert summary.failures == [("archive_um_klines_1d", "BADUSDT", None)]
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 1


def test_symbols_of_a_dataset_download_side_by_side(warehouse, archive):
    symbols = ["AUSDT", "BUSDT", "CUSDT", "DUSDT"]
    for symbol in symbols:
        _publish(archive, symbol, "2026-09", SEPTEMBER)
    # Each symbol's first request is its listing. One symbol at a time never has four listings
    # in flight, so the barrier times out and every listing fails.
    together = threading.Barrier(len(symbols), timeout=5)

    def get(url):
        if url.startswith(backfill.src.LISTING_URL):
            together.wait()
        return archive(url)

    summary = backfill.run({"archive_um_klines_1d": symbols}, get=get, delay=0, workers=4)
    assert summary.failures == []
    assert [len(store.load("archive_um_klines_1d", s)) for s in symbols] == [1, 1, 1, 1]


def test_a_dataset_finishes_before_the_next_one_starts(warehouse, archive):
    _publish(archive, "AUSDT", "2026-09", SEPTEMBER)
    _publish(archive, "BUSDT", "2026-09", SEPTEMBER)
    archive.publish("data/futures/um/monthly/fundingRate/AUSDT/AUSDT-fundingRate-2026-09.zip",
                    FUNDING)
    finished = []

    def get(url):
        if "BUSDT" in url:
            time.sleep(0.2)  # BUSDT's klines lag, so AUSDT's funding could overtake them
        data = archive(url)
        finished.append(url)
        return data

    work = {"archive_um_klines_1d": ["AUSDT", "BUSDT"], "archive_um_funding": ["AUSDT"]}
    assert backfill.run(work, get=get, delay=0, workers=4).failures == []
    last_klines = max(i for i, u in enumerate(finished) if "fundingRate" not in u)
    first_funding = min(i for i, u in enumerate(finished) if "fundingRate" in u)
    assert last_klines < first_funding


def test_work_list_routes_each_dataset():
    work = backfill.work_list(["BTCUSDT", "TLMUSDT"], ["TLMUSDTSETTLED"])
    assert work["archive_spot_klines_1d"] == work["archive_spot_klines_1h"] == ["BTCUSDT", "ETHUSDT"]
    assert work["archive_um_klines_1d"] == ["BTCUSDT", "TLMUSDT", "TLMUSDTSETTLED"]
    assert work["archive_um_funding"] == work["archive_um_premium_1d"] == ["BTCUSDT", "TLMUSDT"]


def test_a_non_ascii_ticker_is_stored_under_its_own_name(warehouse, archive):
    _publish(archive, "币安人生USDT", "2026-09", SEPTEMBER)
    backfill.run({"archive_um_klines_1d": ["币安人生USDT"]}, get=archive, delay=0)
    assert len(store.load("archive_um_klines_1d", "币安人生USDT")) == 1


def test_stored_months_come_from_the_time_column(warehouse):
    rows = [{"funding_time": 1785542400001, "funding_rate": 0.0},   # 2026-08-01
            {"funding_time": 1788220800001, "funding_rate": 0.0}]   # 2026-09-01
    store.upsert("archive_um_funding", "BTCUSDT", rows, "funding_time")
    assert backfill.stored_months("archive_um_funding", "BTCUSDT") == {"2026-08", "2026-09"}
    assert backfill.stored_months("archive_um_funding", "ETHUSDT") == set()


def test_missing_days_are_the_gaps_inside_the_stored_history(warehouse):
    rows = [{"open_time": SEP1 + d * DAY, "close": 1.0} for d in (0, 1, 4)]  # Sep 1, 2 and 5
    store.upsert("archive_um_klines_1d", "BTCUSDT", rows, "open_time")
    assert backfill.missing_days("archive_um_klines_1d", "BTCUSDT") == ["2026-09-03", "2026-09-04"]
    assert backfill.missing_days("archive_um_klines_1d", "ETHUSDT") == []


def test_a_day_the_monthly_file_skips_is_filled_from_the_daily_file(warehouse, archive):
    # Binance's 2022-02 monthly files for 49 perps end on the 25th; its daily files hold the rest.
    _publish(archive, "BTCUSDT", "2026-09", _bars(1, 3))
    _publish_day(archive, "BTCUSDT", "2026-09-02", _bars(2))
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == []
    assert summary.new_rows[("archive_um_klines_1d", "BTCUSDT")] == 3
    stored = store.load("archive_um_klines_1d", "BTCUSDT")
    assert list(stored["open_time"]) == [SEP1, SEP1 + DAY, SEP1 + 2 * DAY]


def test_a_day_with_no_daily_file_stays_a_hole(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", _bars(1, 3))
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == []
    assert list(store.load("archive_um_klines_1d", "BTCUSDT")["open_time"]) == [SEP1, SEP1 + 2 * DAY]


def test_a_corrupt_daily_file_is_reported_and_never_stored(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", _bars(1, 3))
    _publish_day(archive, "BTCUSDT", "2026-09-02", _bars(2), corrupt=True)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == [("archive_um_klines_1d", "BTCUSDT", "2026-09-02")]
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 2


def test_days_after_the_last_monthly_file_come_from_the_daily_files(warehouse, archive):
    # AERGOUSDT settled on 2026-07-24, and its live folder never got a monthly file for July.
    _publish(archive, "BTCUSDT", "2026-09", _bars(1))
    _publish_day(archive, "BTCUSDT", "2026-09-02", _bars(2))
    _publish_day(archive, "BTCUSDT", "2026-09-03", _bars(3))
    summary = backfill.run(KLINES, get=archive, delay=0, tail_before="2026-10-01")
    assert summary.failures == []
    assert summary.new_rows[("archive_um_klines_1d", "BTCUSDT")] == 3
    stored = store.load("archive_um_klines_1d", "BTCUSDT")
    assert list(stored["open_time"]) == [SEP1, SEP1 + DAY, SEP1 + 2 * DAY]


def test_days_from_the_cutoff_on_wait_for_their_monthly_file(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", _bars(1))
    _publish_day(archive, "BTCUSDT", "2026-09-02", _bars(2))
    _publish_day(archive, "BTCUSDT", "2026-09-03", _bars(3))
    backfill.run(KLINES, get=archive, delay=0, tail_before="2026-09-03")
    assert list(store.load("archive_um_klines_1d", "BTCUSDT")["open_time"]) == [SEP1, SEP1 + DAY]


def test_a_symbol_stored_up_to_the_cutoff_lists_no_daily_files(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", _bars(1))
    backfill.run(KLINES, get=archive, delay=0, tail_before="2026-09-02")
    assert not any("/daily/" in urllib.parse.unquote(u) for u in archive.urls)


def test_a_daily_listing_failure_is_reported_and_keeps_the_months(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-09", _bars(1))

    def flaky(url):
        if "/daily/" in urllib.parse.unquote(url):
            raise urllib.error.URLError("timed out")
        return archive(url)

    summary = backfill.run(KLINES, get=flaky, delay=0, tail_before="2026-10-01")
    assert summary.failures == [("archive_um_klines_1d", "BTCUSDT", None)]
    assert len(store.load("archive_um_klines_1d", "BTCUSDT")) == 1


def test_the_cutoff_is_the_first_of_last_month():
    assert backfill.first_of_last_month(date(2026, 10, 12)) == "2026-09-01"
    assert backfill.first_of_last_month(date(2026, 10, 1)) == "2026-09-01"
    assert backfill.first_of_last_month(date(2026, 1, 31)) == "2025-12-01"
