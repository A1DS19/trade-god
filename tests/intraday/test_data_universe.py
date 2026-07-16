"""REST fetchers: closed-bar discipline, per-symbol isolation, universe rule."""

from __future__ import annotations

import time


from app.intraday import data as idata
from app.intraday import universe as iuni

BAR_MS = 900_000
DAY_MS = 86_400_000


def _kline(open_ms, close=100.0, low=99.0, closed=True):
    close_time = open_ms + BAR_MS - 1 if closed else int(time.time() * 1000) + BAR_MS
    return [open_ms, "100", "101", str(low), str(close), "10",
            close_time, "1000", 5, "5", "500", "0"]


class FakeClient:
    def __init__(self, klines_by_symbol=None, fail=(), funding=None,
                 daily=None, tickers=None, info_symbols=None):
        self.klines_by_symbol = klines_by_symbol or {}
        self.fail = set(fail)
        self.funding = funding or {}
        self.daily = daily or {}
        self.tickers = tickers or []
        self.info_symbols = info_symbols or []

    def futures_klines(self, symbol, interval, limit):
        if symbol in self.fail:
            raise RuntimeError("boom")
        if interval == "1d":
            return self.daily[symbol]
        return self.klines_by_symbol[symbol]

    def futures_funding_rate(self, symbol, startTime, limit):
        return [e for e in self.funding.get(symbol, [])
                if e["fundingTime"] > startTime]

    def futures_exchange_info(self):
        return {"symbols": self.info_symbols}

    def futures_ticker(self):
        return self.tickers


def test_fetch_panels_drops_forming_bar_and_isolates_errors():
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    klines = [_kline(now_open - 2 * BAR_MS), _kline(now_open - BAR_MS),
              _kline(now_open, closed=False)]
    client = FakeClient(klines_by_symbol={"A": klines, "B": klines}, fail=["B"])

    panels, errors = idata.fetch_panels(client, ["A", "B"], bars=10)

    assert list(panels["close"].columns) == ["A"]
    assert len(panels["close"]) == 2            # forming bar dropped
    assert "B" in errors


def test_latest_bars_shape():
    now_open = (int(time.time() * 1000) // BAR_MS) * BAR_MS
    klines = [_kline(now_open - 2 * BAR_MS, close=50.0, low=49.5),
              _kline(now_open - BAR_MS, close=51.0, low=50.5)]
    client = FakeClient(klines_by_symbol={"A": klines})
    panels, _ = idata.fetch_panels(client, ["A"], bars=10)

    bars = idata.latest_bars(panels)

    assert bars["A"].close == 51.0 and bars["A"].low == 50.5
    assert bars["A"].open_time == now_open - BAR_MS


def test_fetch_funding_since_filters_and_isolates():
    client = FakeClient(funding={
        "A": [{"symbol": "A", "fundingTime": 100, "fundingRate": "0.0001"},
              {"symbol": "A", "fundingTime": 200, "fundingRate": "0.0002"}],
    }, fail=["B"])

    events = idata.fetch_funding_since(client, ["A", "B"], since_ms=100)

    assert events == [{"symbol": "A", "funding_time": 200, "funding_rate": 0.0002}]


def test_resolve_top30_rejects_29_closed_days_plus_forming_bar():
    now_ms = int(time.time() * 1000)

    def closed_daily(qv, days):
        start = now_ms - (days + 1) * DAY_MS
        return [[start + d * DAY_MS, "1", "1", "1", "1", "1",
                 start + d * DAY_MS + DAY_MS - 1, str(qv), 1, "0", "0", "0"]
                for d in range(days)]

    def with_forming(rows, qv):
        t = now_ms - (now_ms % DAY_MS)
        return rows + [[t, "1", "1", "1", "1", "1", t + DAY_MS - 1 + DAY_MS,
                        str(qv), 1, "0", "0", "0"]]   # close_time in the future

    info = [{"symbol": s, "contractType": "PERPETUAL", "quoteAsset": "USDT",
             "status": "TRADING"} for s in ("OLDUSDT", "YOUNGUSDT")]
    tickers = [{"symbol": "OLDUSDT", "quoteVolume": "1000"},
               {"symbol": "YOUNGUSDT", "quoteVolume": "9999"}]
    client = FakeClient(info_symbols=info, tickers=tickers, daily={
        "OLDUSDT": with_forming(closed_daily(1000.0, 31), 1.0),
        "YOUNGUSDT": with_forming(closed_daily(9999.0, 29), 5.0),  # 29 closed + forming
    })

    top = iuni.resolve_top30(client)

    assert top == ["OLDUSDT"]


def test_resolve_top30_ranks_by_30d_median():
    def daily(qv, days=31):
        return [[d * DAY_MS, "1", "1", "1", "1", "1",
                 d * DAY_MS + DAY_MS - 1, str(qv), 1, "0", "0", "0"]
                for d in range(days)]
    info = [{"symbol": s, "contractType": "PERPETUAL", "quoteAsset": "USDT",
             "status": "TRADING"} for s in ("BIGUSDT", "MIDUSDT", "FRESHUSDT")]
    tickers = [{"symbol": "BIGUSDT", "quoteVolume": "3000"},
               {"symbol": "MIDUSDT", "quoteVolume": "2000"},
               {"symbol": "FRESHUSDT", "quoteVolume": "9999"}]
    client = FakeClient(info_symbols=info, tickers=tickers, daily={
        "BIGUSDT": daily(3000.0), "MIDUSDT": daily(2000.0),
        "FRESHUSDT": daily(9999.0, days=10),      # too young: <30 full days
    })

    top = iuni.resolve_top30(client)

    assert top == ["BIGUSDT", "MIDUSDT"]
