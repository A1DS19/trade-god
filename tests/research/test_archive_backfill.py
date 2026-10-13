"""archive_backfill: every published month is fetched once, verified and stored; reruns resume;
a bad month is reported and retried, never stored."""

from __future__ import annotations

import threading
import time
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


def _publish(archive, symbol, month, text, corrupt=False):
    archive.publish(f"{UM}{symbol}/1d/{symbol}-1d-{month}.zip", text, corrupt=corrupt)


def test_first_run_stores_every_published_month(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)
    _publish(archive, "BTCUSDT", "2026-09", SEPTEMBER)
    summary = backfill.run(KLINES, get=archive, delay=0)
    assert summary.failures == []
    assert summary.new_rows[("archive_um_klines_1d", "BTCUSDT")] == 2
    stored = store.load("archive_um_klines_1d", "BTCUSDT")
    assert list(stored["open_time"]) == [1785542400000, 1788220800000]


def test_rerun_downloads_only_what_is_missing(warehouse, archive):
    _publish(archive, "BTCUSDT", "2026-08", AUGUST)
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
