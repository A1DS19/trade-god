"""Fetchers must paginate to exhaustion, throttle, normalize rows, drop the
still-forming last candle, and clamp rolling datasets to the 30-day window."""

from __future__ import annotations

import time

from research import binance_source as src


def _kline(open_ms, close_ms):
    return [open_ms, "1.0", "2.0", "0.5", "1.5", "100", close_ms, "150", 7, "60", "90", "0"]


class FakePagedClient:
    """Serves canned pages; records request kwargs."""

    def __init__(self, kline_pages=None, funding_pages=None, oi_pages=None):
        self.kline_pages = list(kline_pages or [])
        self.funding_pages = list(funding_pages or [])
        self.oi_pages = list(oi_pages or [])
        self.kline_calls: list[dict] = []
        self.funding_calls: list[dict] = []
        self.oi_calls: list[dict] = []
        self.premium_calls: list[dict] = []

    def futures_klines(self, **kw):
        self.kline_calls.append(kw)
        return self.kline_pages.pop(0) if self.kline_pages else []

    def futures_funding_rate(self, **kw):
        self.funding_calls.append(kw)
        return self.funding_pages.pop(0) if self.funding_pages else []

    def futures_open_interest_hist(self, **kw):
        self.oi_calls.append(kw)
        return self.oi_pages.pop(0) if self.oi_pages else []

    def futures_global_longshort_ratio(self, **kw):
        self.oi_calls.append(kw)
        return self.oi_pages.pop(0) if self.oi_pages else []

    def _request_futures_api(self, method, path, signed=False, data=None):
        self.premium_calls.append({"method": method, "path": path, "signed": signed, "data": data})
        return self.kline_pages.pop(0) if self.kline_pages else []


def test_klines_paginate_and_normalize():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    base = now - 3000 * h  # all closed
    page1 = [_kline(base + i * h, base + (i + 1) * h - 1) for i in range(1500)]
    page2 = [_kline(base + (1500 + i) * h, base + (1501 + i) * h - 1) for i in range(10)]
    client = FakePagedClient(kline_pages=[page1, page2])

    rows = src.fetch_klines(client, "DOGEUSDT", "1h", base, delay=0)

    assert len(rows) == 1510
    assert client.kline_calls[0]["startTime"] == base
    assert client.kline_calls[0]["limit"] == 1500
    # cursor advanced past page1's last open_time
    assert client.kline_calls[1]["startTime"] == page1[-1][0] + h
    r = rows[0]
    assert r["open_time"] == base and r["close"] == 1.5 and r["volume"] == 100.0
    assert r["quote_volume"] == 150.0 and r["trades"] == 7


def test_klines_drop_forming_last_candle():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    closed = _kline(now - 2 * h, now - h - 1)
    forming = _kline(now - h, now + h)  # close_time in the future
    client = FakePagedClient(kline_pages=[[closed, forming]])

    rows = src.fetch_klines(client, "DOGEUSDT", "1h", now - 2 * h, delay=0)

    assert [r["open_time"] for r in rows] == [now - 2 * h]


def test_funding_pagination_and_normalization():
    pages = [
        [{"fundingTime": 1000 + i, "fundingRate": "0.0001", "markPrice": "1.0"} for i in range(1000)],
        [{"fundingTime": 3000, "fundingRate": "-0.0002", "markPrice": "1.1"}],
    ]
    client = FakePagedClient(funding_pages=pages)

    rows = src.fetch_funding(client, "DOGEUSDT", 1000, delay=0)

    assert len(rows) == 1001
    assert client.funding_calls[0]["limit"] == 1000
    assert client.funding_calls[1]["startTime"] == 1999 + 1  # last fundingTime + 1
    assert rows[-1] == {"funding_time": 3000, "funding_rate": -0.0002, "mark_price": 1.1}


def test_premium_index_uses_unsigned_raw_endpoint():
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    client = FakePagedClient(kline_pages=[[_kline(now - 2 * h, now - h - 1)]])

    rows = src.fetch_premium_index(client, "DOGEUSDT", now - 2 * h, delay=0)

    call = client.premium_calls[0]
    assert call["path"] == "premiumIndexKlines" and call["signed"] is False
    assert call["data"]["interval"] == "1h" and call["data"]["symbol"] == "DOGEUSDT"
    assert rows[0]["close"] == 1.5 and "volume" not in rows[0]


def test_open_interest_clamps_to_rolling_window():
    now = int(time.time() * 1000)
    client = FakePagedClient(oi_pages=[[{"timestamp": now - 1000, "sumOpenInterest": "5", "sumOpenInterestValue": "10"}]])

    rows = src.fetch_open_interest(client, "DOGEUSDT", 0, delay=0)  # asks from epoch 0

    requested = client.oi_calls[0]["startTime"]
    assert requested >= now - 30 * 24 * src.HOUR_MS  # clamped
    assert rows == [{"timestamp": now - 1000, "sum_open_interest": 5.0, "sum_open_interest_value": 10.0}]


def test_long_short_normalization():
    now = int(time.time() * 1000)
    client = FakePagedClient(oi_pages=[[{"timestamp": now - 1000, "longShortRatio": "2.5", "longAccount": "0.71", "shortAccount": "0.29"}]])

    rows = src.fetch_long_short(client, "DOGEUSDT", now - 2000, delay=0)

    assert rows == [{"timestamp": now - 1000, "long_short_ratio": 2.5, "long_account": 0.71, "short_account": 0.29}]
