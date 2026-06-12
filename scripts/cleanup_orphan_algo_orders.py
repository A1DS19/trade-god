"""One-off: list/cancel orphaned Algo-service conditional orders.

An algo SL/TP with closePosition="true" left armed after its position is gone
will market-close any FUTURE position in that symbol when the stale trigger
hits. Dry-run by default; pass --execute to actually cancel.

Usage (needs BINANCE_API_KEY_FUTURES / BINANCE_SECRET_KEY_FUTURES in env or .env):
    python scripts/cleanup_orphan_algo_orders.py            # report only
    python scripts/cleanup_orphan_algo_orders.py --execute  # cancel orphans
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from binance.client import Client  # noqa: E402

from app.swing import config  # noqa: E402
from app.swing.exchange import get_open_positions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="actually cancel (default: dry run)")
    args = parser.parse_args()

    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
    positions = get_open_positions(client)
    print(f"Open positions: {sorted(positions) or 'none'}")

    resp = client._request_futures_api("get", "openAlgoOrders", True, data={})
    orders = resp.get("orders", resp) if isinstance(resp, dict) else resp
    if not orders:
        print("No open algo orders. Nothing to do.")
        return

    orphans: dict[str, list] = {}
    for o in orders:
        coin = o["symbol"][:-4] if o["symbol"].endswith("USDT") else o["symbol"]
        status = "HELD" if coin in positions else "ORPHAN"
        print(f"[{status}] {o['symbol']} {o.get('orderType', o.get('type'))} "
              f"trigger={o.get('triggerPrice')} algoId={o.get('algoId')}")
        if status == "ORPHAN":
            orphans.setdefault(o["symbol"], []).append(o)

    if not orphans:
        print("No orphans found.")
        return
    if not args.execute:
        print(f"\nDRY RUN — would cancel all algo orders on: {sorted(orphans)}. Re-run with --execute.")
        return
    for symbol in sorted(orphans):
        client._request_futures_api("delete", "algoOpenOrders", True, data={"symbol": symbol})
        print(f"Cancelled all algo orders on {symbol}")


if __name__ == "__main__":
    main()
