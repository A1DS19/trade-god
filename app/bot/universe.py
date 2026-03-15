"""Coin universe — fetches top coins by market cap from CoinGecko."""

import logging
import requests
from binance.client import Client
from app.config import TOP_N_COINS, COIN_BLACKLIST

log = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"


def get_top_coins(client: Client) -> list[str]:
    """
    Fetch top coins by market cap from CoinGecko, then cross-check
    against active Binance USDT spot pairs.
    BTC is always included as it doubles as the market filter.
    """
    # Step 1 — top coins by market cap (no API key needed)
    resp = requests.get(
        COINGECKO_URL,
        params={
            "vs_currency": "usd",
            "order":       "market_cap_desc",
            "per_page":    60,
            "page":        1,
            "sparkline":   False,
        },
        timeout=15,
    )
    resp.raise_for_status()
    cg_coins = [row["symbol"].upper() for row in resp.json()]

    # Step 2 — active USDT spot pairs on Binance
    info = client.get_exchange_info()
    binance_spot = {
        s["baseAsset"]
        for s in info["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    }

    # Step 3 — filter and pick top N
    coins = []
    for coin in cg_coins:
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
