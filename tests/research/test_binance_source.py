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


def test_open_interest_windowed_pagination():
    """Replacing the single-page test: _fetch_rolling must walk explicit [s,e] windows,
    clamp the start to now-30d, pass endTime on every call, and collect all windows.

    ROLLING_WINDOW_MS = 29 days = 696h; ROLLING_PAGE = 500h → exactly 2 windows fit.
    Window 1: [clamped_start, clamped_start+500h]
    Window 2: [clamped_start+500h+1, now]
    Both carry real data; the empty-window advance is covered by a separate test below.
    """
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    # 696h window → window1 spans [now-696h, now-196h], window2 spans [now-196h+1, now]
    window1_ts = now - 500 * h + 100   # sits in window 1
    window2_ts = now - 100 * h + 100   # sits in window 2
    pages = [
        [{"timestamp": window1_ts, "sumOpenInterest": "5", "sumOpenInterestValue": "10"}],
        [{"timestamp": window2_ts, "sumOpenInterest": "7", "sumOpenInterestValue": "14"}],
    ]
    client = FakePagedClient(oi_pages=pages)

    rows = src.fetch_open_interest(client, "DOGEUSDT", 0, delay=0)  # asks from epoch 0

    # Clamp: first startTime must be >= now-30d
    first_start = client.oi_calls[0]["startTime"]
    assert first_start >= now - 30 * 24 * h, "start was not clamped to rolling window"

    # Every request carries an endTime
    for call in client.oi_calls:
        assert "endTime" in call, f"request missing endTime: {call}"

    # endTime on first request = startTime + ROLLING_PAGE hours (clamped to now)
    expected_end = min(first_start + src.ROLLING_PAGE * h, now)
    # Allow ±2 seconds for time() drift
    assert abs(client.oi_calls[0]["endTime"] - expected_end) < 2000

    # Both windows land in the result
    assert len(rows) == 2
    assert rows[0] == {"timestamp": window1_ts, "sum_open_interest": 5.0, "sum_open_interest_value": 10.0}
    assert rows[1] == {"timestamp": window2_ts, "sum_open_interest": 7.0, "sum_open_interest_value": 14.0}


def test_fetch_rolling_empty_window_advances():
    """An empty API response for a window must advance the cursor, not stall."""
    h = src.HOUR_MS
    # Use a small synthetic start that produces 3 windows; inject an empty middle window.
    now_approx = int(time.time() * 1000)
    start = now_approx - 3 * src.ROLLING_PAGE * h - 1  # will be clamped to now-29d

    call_args: list[tuple] = []

    def fake_fetch(s, e):
        call_args.append((s, e))
        # first call: return data; second (middle): empty; third: data
        if len(call_args) == 2:
            return []
        return [{"timestamp": s + 1, "sumOpenInterest": "1", "sumOpenInterestValue": "2"}]

    out = src._fetch_rolling(fake_fetch, start, delay=0)

    # Must have called at least twice (empty window did not re-issue the same cursor)
    assert len(call_args) >= 2
    # Cursors must be strictly increasing
    starts = [a[0] for a in call_args]
    assert starts == sorted(starts) and len(set(starts)) == len(starts), "cursor did not advance"


def test_long_short_windowed_and_normalization():
    """L/S uses the same _fetch_rolling path: both windows collected, endTime present."""
    h = src.HOUR_MS
    now = int(time.time() * 1000)
    window1_ts = now - 3 * src.ROLLING_PAGE * h + 200
    window2_ts = now - src.ROLLING_PAGE * h + 200
    pages = [
        [{"timestamp": window1_ts, "longShortRatio": "2.5", "longAccount": "0.71", "shortAccount": "0.29"}],
        [{"timestamp": window2_ts, "longShortRatio": "1.1", "longAccount": "0.52", "shortAccount": "0.48"}],
    ]
    client = FakePagedClient(oi_pages=pages)

    rows = src.fetch_long_short(client, "DOGEUSDT", 0, delay=0)

    for call in client.oi_calls:
        assert "endTime" in call

    assert len(rows) == 2
    assert rows[0] == {"timestamp": window1_ts, "long_short_ratio": 2.5, "long_account": 0.71, "short_account": 0.29}
    assert rows[1] == {"timestamp": window2_ts, "long_short_ratio": 1.1, "long_account": 0.52, "short_account": 0.48}
