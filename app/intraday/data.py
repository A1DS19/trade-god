"""Unsigned REST market data -> pandas panels. Closed bars only; one symbol's
failure never breaks the cycle (per-symbol isolation is a hard requirement —
see the TON/IP silent-crash postmortem in CLAUDE.md)."""

from __future__ import annotations

import time

import pandas as pd

from app.intraday.paper import Bar

COLS = {"close": 4, "low": 3, "volume": 5, "quote_volume": 7}


def fetch_panels(client, symbols: list[str], bars: int = 200):
    now_ms = int(time.time() * 1000)
    frames = {name: {} for name in COLS}
    errors: dict[str, str] = {}
    for sym in symbols:
        try:
            raw = client.futures_klines(symbol=sym, interval="15m", limit=bars)
            closed = [k for k in raw if int(k[6]) <= now_ms]
            if not closed:
                continue
            idx = [int(k[0]) for k in closed]
            for name, col in COLS.items():
                frames[name][sym] = pd.Series(
                    [float(k[col]) for k in closed], index=idx)
        except Exception as e:
            errors[sym] = str(e)
    panels = {
        name: pd.DataFrame(series).sort_index().rename_axis("open_time")
        for name, series in frames.items()
    }
    return panels, errors


def latest_bars(panels: dict) -> dict[str, Bar]:
    close, low = panels["close"], panels["low"]
    out: dict[str, Bar] = {}
    for sym in close.columns:
        c = close[sym].dropna()
        if c.empty:
            continue
        t = c.index[-1]
        out[sym] = Bar(open_time=int(t), close=float(c.loc[t]),
                       low=float(low[sym].loc[t]))
    return out


def fetch_funding_since(client, symbols: list[str], since_ms: int) -> list[dict]:
    events: list[dict] = []
    for sym in symbols:
        try:
            raw = client.futures_funding_rate(symbol=sym, startTime=since_ms + 1,
                                              limit=100)
            for r in raw:
                if int(r["fundingTime"]) > since_ms:
                    events.append({"symbol": sym,
                                   "funding_time": int(r["fundingTime"]),
                                   "funding_rate": float(r["fundingRate"])})
        except Exception:
            continue
    return events
