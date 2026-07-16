"""Fetch top N coins by market cap that have Binance USDT-M perpetual futures."""

from __future__ import annotations

import logging
import time

import requests
from binance.client import Client

log = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINPAPRIKA_URL = "https://api.coinpaprika.com/v1/tickers"

STABLECOIN_BLACKLIST = {
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "BUSD", "USDP", "PYUSD",
    "USDD", "FRAX", "LUSD", "GUSD", "SUSD", "CUSD", "EUSD",
}

# Safety net if both CoinGecko and CoinPaprika fail.
# Top 50 by market cap (April 2026) that have Binance USDT-M perpetuals.
FALLBACK_TOP_50 = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK",
    "DOT", "TRX", "SHIB", "TON", "NEAR", "UNI", "LTC", "SUI", "APT",
    "ICP", "FIL", "ARB", "OP", "ATOM", "IMX", "RUNE", "INJ", "FTM",
    "AAVE", "RENDER", "TIA", "SEI", "PEPE", "WIF", "FET", "ONDO",
    "JUP", "STX", "PENDLE", "ENA", "WLD", "PYTH", "JTO", "HBAR",
    "BCH", "MKR", "BONK", "ORDI", "ALGO", "THETA", "EOS",
]


def _fetch_coingecko(per_page: int = 250) -> list[str]:
    for attempt in range(3):
        resp = requests.get(
            COINGECKO_URL,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": 1,
                "sparkline": False,
            },
            timeout=15,
        )
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            log.warning("CoinGecko rate limited — retrying in %ds", wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return [row["symbol"].upper() for row in resp.json()]
    raise RuntimeError("CoinGecko rate limited after 3 attempts")


def _fetch_coinpaprika(limit: int = 250) -> list[str]:
    resp = requests.get(COINPAPRIKA_URL, params={"limit": limit}, timeout=15)
    resp.raise_for_status()
    return [row["symbol"].upper() for row in resp.json()]


def _get_binance_futures_symbols() -> set[str]:
    client = Client()
    info = client.futures_exchange_info()
    return {
        s["baseAsset"]
        for s in info["symbols"]
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
        and s.get("status") == "TRADING"
    }


def get_top_futures_coins(n: int = 50) -> list[str]:
    """Return top *n* coins by market cap that have active Binance USDT-M perpetual futures."""
    # Step 1 — ranked coins by market cap
    try:
        ranked = _fetch_coingecko()
        log.info("Coin list sourced from CoinGecko")
    except Exception as e:
        log.warning("CoinGecko failed (%s) — trying CoinPaprika", e)
        try:
            ranked = _fetch_coinpaprika()
            log.info("Coin list sourced from CoinPaprika")
        except Exception as e2:
            log.warning("CoinPaprika also failed (%s) — using fallback list", e2)
            return FALLBACK_TOP_50[:n]

    # Step 2 — active Binance USDT-M perpetuals
    try:
        futures_symbols = _get_binance_futures_symbols()
    except Exception as e:
        log.warning("Binance futures_exchange_info failed (%s) — using fallback list", e)
        return FALLBACK_TOP_50[:n]

    # Step 3 — intersect, excluding stablecoins
    coins: list[str] = []
    for coin in ranked:
        if coin in STABLECOIN_BLACKLIST:
            continue
        if coin not in futures_symbols:
            continue
        coins.append(coin)
        if len(coins) >= n:
            break

    if not coins:
        log.warning("No coins matched — using fallback list")
        return FALLBACK_TOP_50[:n]

    print(f"Resolved top {len(coins)} futures coins: {', '.join(coins)}")
    return coins
