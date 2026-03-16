"""Coin universe — fetches top coins by market cap. CoinGecko with CoinPaprika fallback."""

import logging
import time
import requests
from binance.client import Client
from app.config import TOP_N_COINS, COIN_BLACKLIST

log = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINPAPRIKA_URL = "https://api.coinpaprika.com/v1/tickers"


def _fetch_coingecko() -> list[str]:
    """Fetch top coins by market cap from CoinGecko."""
    for attempt in range(3):
        resp = requests.get(
            COINGECKO_URL,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 60,
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


def _fetch_coinpaprika() -> list[str]:
    """Fetch top coins by market cap from CoinPaprika (no API key needed)."""
    resp = requests.get(COINPAPRIKA_URL, params={"limit": 60}, timeout=15)
    resp.raise_for_status()
    return [row["symbol"].upper() for row in resp.json()]


def get_top_coins(client: Client) -> list[str]:
    """
    Fetch top coins by market cap, trying CoinGecko first then CoinPaprika.
    Cross-checks against active Binance USDT spot pairs.
    BTC is always included as it doubles as the market filter.
    """
    # Step 1 — fetch ranked coins with fallback
    try:
        ranked = _fetch_coingecko()
        log.info("Coin list sourced from CoinGecko")
    except Exception as e:
        log.warning("CoinGecko failed (%s) — falling back to CoinPaprika", e)
        ranked = _fetch_coinpaprika()
        log.info("Coin list sourced from CoinPaprika")

    # Step 2 — active USDT spot pairs on Binance
    # Extract the set immediately and discard the large response dict
    symbols = client.get_exchange_info()["symbols"]
    binance_spot = {
        s["baseAsset"]
        for s in symbols
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    }
    del symbols

    # Step 3 — filter and pick top N
    coins = []
    for coin in ranked:
        if coin in COIN_BLACKLIST:
            continue
        if coin not in binance_spot:
            log.debug("Skipping %s — not on Binance Spot", coin)
            continue
        coins.append(coin)
        if len(coins) >= TOP_N_COINS:
            break

    if "BTC" not in coins:
        coins.insert(0, "BTC")

    return coins
