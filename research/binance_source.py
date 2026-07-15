"""Throttled, paginated Binance USDT-M market-data fetchers (all UNSIGNED).

Every fetcher: sleeps `delay` before each request (never hammer from one IP —
see the 2026-06-05 -1003 ban), paginates to exhaustion with a non-advancing
cursor guard, and returns normalized list[dict] rows matching research.config
dataset schemas. The still-forming last candle is dropped (close_time in the
future) so the warehouse only ever holds closed bars.
"""

from __future__ import annotations

import time

from research.config import HOUR_MS, MINUTE_MS, ROLLING_WINDOW_MS

INTERVAL_MS = {"5m": 5 * MINUTE_MS, "15m": 15 * MINUTE_MS,
               "1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": 24 * HOUR_MS}

KLINES_PAGE = 1500
FUNDING_PAGE = 1000
ROLLING_PAGE = 500


def _now_ms() -> int:
    return int(time.time() * 1000)


def _drop_unclosed(rows: list[list], now_ms: int) -> list[list]:
    if rows and int(rows[-1][6]) > now_ms:
        return rows[:-1]
    return rows


def _kline_row(k: list) -> dict:
    return {
        "open_time": int(k[0]),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "close_time": int(k[6]),
        "quote_volume": float(k[7]),
        "trades": int(k[8]),
        "taker_buy_volume": float(k[9]),
        "taker_buy_quote_volume": float(k[10]),
    }


def _paginate(fetch_page, start_ms: int, *, step_ms: int, page_size: int, delay: float,
              row_time) -> list:
    """Generic cursor pagination: fetch_page(cursor) -> raw list; row_time(raw_row) -> ms."""
    out: list = []
    cursor = start_ms
    prev_last = -1
    while True:
        if delay > 0:
            time.sleep(delay)
        batch = fetch_page(cursor)
        if not batch:
            break
        out.extend(batch)
        last = row_time(batch[-1])
        if last <= prev_last:
            break
        prev_last = last
        cursor = last + step_ms
        if len(batch) < page_size:
            break
    return out


def fetch_klines(client, symbol: str, interval: str, start_ms: int, *, delay: float) -> list[dict]:
    step = INTERVAL_MS[interval]
    raw = _paginate(
        lambda c: client.futures_klines(symbol=symbol, interval=interval, startTime=c, limit=KLINES_PAGE),
        start_ms, step_ms=step, page_size=KLINES_PAGE, delay=delay, row_time=lambda k: int(k[0]),
    )
    return [_kline_row(k) for k in _drop_unclosed(raw, _now_ms())]


def fetch_premium_index(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client._request_futures_api(
            "get", "premiumIndexKlines", False,
            data={"symbol": symbol, "interval": "1h", "startTime": c, "limit": KLINES_PAGE},
        ),
        start_ms, step_ms=HOUR_MS, page_size=KLINES_PAGE, delay=delay, row_time=lambda k: int(k[0]),
    )
    # Premium-index klines carry no volume/trades data — keep OHLC + times only.
    return [
        {"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
         "low": float(k[3]), "close": float(k[4]), "close_time": int(k[6])}
        for k in _drop_unclosed(raw, _now_ms())
    ]


def fetch_funding(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _paginate(
        lambda c: client.futures_funding_rate(symbol=symbol, startTime=c, limit=FUNDING_PAGE),
        start_ms, step_ms=1, page_size=FUNDING_PAGE, delay=delay,
        row_time=lambda r: int(r["fundingTime"]),
    )
    return [
        {"funding_time": int(r["fundingTime"]), "funding_rate": float(r["fundingRate"]),
         "mark_price": float(r["markPrice"]) if r.get("markPrice") not in (None, "") else None}
        for r in raw
    ]


def _clamp_rolling(start_ms: int) -> int:
    return max(start_ms, _now_ms() - ROLLING_WINDOW_MS)


def _fetch_rolling(fetch_window, start_ms: int, *, delay: float) -> list:
    """The futures-data endpoints (OI, L/S) anchor to the END of the range:
    startTime-only returns the NEWEST `limit` rows. Walk explicit windows of
    ROLLING_PAGE hours instead so the oldest rows aren't silently dropped."""
    out: list = []
    cursor = _clamp_rolling(start_ms)
    now = _now_ms()
    while cursor < now:
        end = min(cursor + ROLLING_PAGE * HOUR_MS, now)
        if delay > 0:
            time.sleep(delay)
        out.extend(fetch_window(cursor, end))
        cursor = end + 1
    return out


def fetch_open_interest(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _fetch_rolling(
        lambda s, e: client.futures_open_interest_hist(
            symbol=symbol, period="1h", startTime=s, endTime=e, limit=ROLLING_PAGE
        ),
        start_ms, delay=delay,
    )
    return [
        {"timestamp": int(r["timestamp"]), "sum_open_interest": float(r["sumOpenInterest"]),
         "sum_open_interest_value": float(r["sumOpenInterestValue"])}
        for r in raw
    ]


def fetch_long_short(client, symbol: str, start_ms: int, *, delay: float) -> list[dict]:
    raw = _fetch_rolling(
        lambda s, e: client.futures_global_longshort_ratio(
            symbol=symbol, period="1h", startTime=s, endTime=e, limit=ROLLING_PAGE
        ),
        start_ms, delay=delay,
    )
    return [
        {"timestamp": int(r["timestamp"]), "long_short_ratio": float(r["longShortRatio"]),
         "long_account": float(r["longAccount"]), "short_account": float(r["shortAccount"])}
        for r in raw
    ]
