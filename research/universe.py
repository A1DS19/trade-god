"""Resolve the research universe: top-N TRADING USDT perpetuals by 24h quote volume."""

from __future__ import annotations

from research import store


def resolve_top(client, n: int) -> list[dict]:
    info = client.futures_exchange_info()
    perps = {
        s["symbol"]: s
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }
    tickers = [t for t in client.futures_ticker() if t["symbol"] in perps]
    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    rows = []
    for rank, t in enumerate(tickers[:n], start=1):
        s = perps[t["symbol"]]
        rows.append({
            "symbol": s["symbol"],
            "coin": s["symbol"][:-4],
            "rank": rank,
            "quote_volume_24h": float(t["quoteVolume"]),
            "onboard_date_ms": int(s.get("onboardDate", 0)),
            "status": s["status"],
        })
    return rows


def save_snapshot(rows: list[dict], snapshot_ms: int) -> int:
    keyed = [
        {**r, "snapshot_ms": snapshot_ms, "snapshot_key": f"{snapshot_ms}:{r['symbol']}"}
        for r in rows
    ]
    return store.upsert("universe", "ALL", keyed, "snapshot_key")
