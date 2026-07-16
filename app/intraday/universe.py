"""Weekly universe: top-30 by 30-day median daily quote volume among the
top-100 USDT perps by 24h volume (live twin of the research PIT rule)."""

from __future__ import annotations

import statistics
import time

UNIVERSE_SIZE = 30
POOL_SIZE = 100
MEDIAN_DAYS = 30


def resolve_top30(client) -> list[str]:
    now_ms = int(time.time() * 1000)
    info = client.futures_exchange_info()
    perps = {
        s["symbol"]
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }
    tickers = [t for t in client.futures_ticker() if t["symbol"] in perps]
    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    pool = [t["symbol"] for t in tickers[:POOL_SIZE]]

    ranked = []
    for sym in pool:
        try:
            daily = client.futures_klines(symbol=sym, interval="1d",
                                          limit=MEDIAN_DAYS + 1)
        except Exception:
            continue
        # closed-bar discipline by close_time (same as data.py) — list length
        # can't tell a forming candle apart: 29 closed + today forming is 30 rows
        closed = [k for k in daily if int(k[6]) <= now_ms]
        if len(closed) < MEDIAN_DAYS:
            continue
        qv = [float(k[7]) for k in closed[-MEDIAN_DAYS:]]
        ranked.append((statistics.median(qv), sym))
    ranked.sort(reverse=True)
    return [sym for _, sym in ranked[:UNIVERSE_SIZE]]
