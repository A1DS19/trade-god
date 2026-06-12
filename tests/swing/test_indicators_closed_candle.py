"""Indicators must be computed on CLOSED candles only.

Binance returns the still-forming candle as the last kline. Using it makes
every signal repaint intra-bar and structurally deflates vol_ratio (a partial
candle's volume vs 20 full ones). get_indicators must drop it.
"""

from __future__ import annotations

import time

from app.swing.indicators import _drop_unclosed, calc_rsi, get_indicators


def _kline(open_time_ms: int, close: float, vol: float, close_time_ms: int) -> list:
    # Binance kline: [open_time, open, high, low, close, volume, close_time, ...]
    return [open_time_ms, close, close * 1.01, close * 0.99, close, vol, close_time_ms, 0, 0, 0, 0, 0]


def _series(n: int, *, last_unclosed: bool, interval_ms: int = 4 * 3600 * 1000) -> list:
    now_ms = int(time.time() * 1000)
    out = []
    for i in range(n):
        open_t = now_ms - (n - i) * interval_ms
        close_t = open_t + interval_ms - 1
        # Oscillating prices so RSI is non-trivial and warmup window actually matters:
        # the 30-bar tail sees a different avg-gain/avg-loss seed than the full series.
        close = 100.0 + 5.0 * (1 if i % 3 != 2 else -1)
        out.append(_kline(open_t, close, 1000.0, close_t))
    if last_unclosed:
        out[-1][6] = now_ms + interval_ms  # close_time in the future = forming
    return out


def test_drop_unclosed_removes_forming_candle() -> None:
    kl = _series(50, last_unclosed=True)
    assert len(_drop_unclosed(kl)) == 49


def test_drop_unclosed_keeps_closed_series_intact() -> None:
    kl = _series(50, last_unclosed=False)
    assert len(_drop_unclosed(kl)) == 50


def test_drop_unclosed_empty() -> None:
    assert _drop_unclosed([]) == []


class _KlineClient:
    """Fake client for get_indicators: serves controlled klines, benign rest."""

    KLINE_INTERVAL_4HOUR = "4h"
    KLINE_INTERVAL_1DAY = "1d"

    def __init__(self) -> None:
        self.kl4 = _series(200, last_unclosed=True)
        self.kl1d = _series(601, last_unclosed=True, interval_ms=24 * 3600 * 1000)
        self.requested_limits: dict[str, int] = {}

    def futures_klines(self, *, symbol, interval, limit):
        self.requested_limits[interval] = limit
        return list(self.kl4 if interval == "4h" else self.kl1d)

    def futures_open_interest_hist(self, **kw):
        return []

    def futures_global_longshort_ratio(self, **kw):
        return []

    def _request_futures_data_api(self, *a, **kw):
        return []


def test_get_indicators_uses_closed_candles_and_full_rsi_warmup() -> None:
    client = _KlineClient()
    ind = get_indicators(client, "DOGE")

    closed_closes = [float(k[4]) for k in client.kl4[:-1]]
    # price = last CLOSED close, not the forming candle
    assert ind["price"] == closed_closes[-1]
    # RSI computed over the full closed series, not a 30-bar tail
    assert ind["rsi14_4h"] == calc_rsi(closed_closes, 14)
    assert ind["rsi14_4h"] != calc_rsi(closed_closes[-30:], 14) or len(closed_closes) <= 30
    # daily fetch is deep enough for a converged EMA200 after dropping the forming bar
    assert client.requested_limits["1d"] >= 601
