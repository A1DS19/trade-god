"""Periodic coin list rebalancing — screen top 100, backtest candidates, report via Telegram."""

from __future__ import annotations

import argparse
import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.swing.backtest_replay.engine import ReplayEngine, StrategyState, _summarize
from app.swing.backtest_replay.screener import screen_all, _print_screen_results
from app.swing.backtest_replay.universe import get_top_futures_coins
from app.swing import config

log = logging.getLogger(__name__)

MIN_TP_RATE = 0.25
MIN_ENTRIES = 50
FEE_BPS = 4.0
SLIPPAGE_BPS = 2.0


def _backtest_coins(
    coins: list[str], start: datetime, end: datetime, workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """Run backtest and return per-coin v2 summary dicts."""
    engine = ReplayEngine(coins, start, end, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS)
    results = engine.run_all(workers=workers)
    summaries: dict[str, dict[str, Any]] = {}
    for coin in coins:
        if coin not in results:
            continue
        _, v2, _ = results[coin]
        s = _summarize(v2)
        s["trades_list"] = v2.trades
        summaries[coin] = s
    return summaries


def _compare_results(
    current_coins: list[str],
    current_bt: dict[str, dict[str, Any]],
    candidate_bt: dict[str, dict[str, Any]],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Classify coins into ok/weak/new_candidates."""
    ok: list[dict] = []
    weak: list[dict] = []

    for coin in current_coins:
        s = current_bt.get(coin)
        if not s:
            weak.append({"coin": coin, "reason": "no data"})
            continue
        trades = int(s["trades"])
        wr = s["win_rate"]
        pnl = s["net_pnl"]
        entry = {"coin": coin, "pnl": pnl, "trades": trades, "win_rate": wr}
        if pnl <= 0 or (trades >= 5 and wr < 0.35):
            entry["reason"] = "negative PnL" if pnl <= 0 else f"low win rate ({wr:.0%})"
            weak.append(entry)
        else:
            ok.append(entry)

    # New candidates: profitable coins not in current set
    current_set = set(current_coins)
    candidates: list[dict] = []
    for coin, s in candidate_bt.items():
        if coin in current_set:
            continue
        pnl = s["net_pnl"]
        trades = int(s["trades"])
        wr = s["win_rate"]
        if pnl > 0 and trades >= 1:
            candidates.append({"coin": coin, "pnl": pnl, "trades": trades, "win_rate": wr})

    candidates.sort(key=lambda x: x["pnl"], reverse=True)
    return ok, weak, candidates


def _format_report(
    ok: list[dict],
    weak: list[dict],
    candidates: list[dict],
    start: datetime,
    end: datetime,
) -> str:
    """Format the rebalance report for Telegram (HTML)."""
    lines = [f"<b>REBALANCE CHECK</b>  {end.strftime('%Y-%m-%d')}"]
    lines.append(f"Lookback: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    lines.append(f"Fees: {FEE_BPS}bps + {SLIPPAGE_BPS}bps slippage\n")

    lines.append(f"<b>CURRENT COINS ({len(ok) + len(weak)}):</b>")
    for c in ok:
        lines.append(
            f"  {c['coin']:<10} ${c['pnl']:>+6.2f}  ({c['trades']}t, {c['win_rate']:.0%}wr)  ✅"
        )
    for c in weak:
        reason = c.get("reason", "underperforming")
        pnl = c.get("pnl", 0)
        trades = c.get("trades", 0)
        wr = c.get("win_rate", 0)
        if trades > 0:
            lines.append(
                f"  {c['coin']:<10} ${pnl:>+6.2f}  ({trades}t, {wr:.0%}wr)  ⚠️ {reason}"
            )
        else:
            lines.append(f"  {c['coin']:<10}  ⚠️ {reason}")

    if candidates:
        lines.append(f"\n<b>NEW CANDIDATES (top 10):</b>")
        for c in candidates[:10]:
            lines.append(
                f"  {c['coin']:<10} ${c['pnl']:>+6.2f}  ({c['trades']}t, {c['win_rate']:.0%}wr)"
            )

    # Recommendations
    recs = []
    if weak:
        drops = ", ".join(c["coin"] for c in weak)
        recs.append(f"Consider dropping: {drops}")
    if candidates:
        adds = ", ".join(c["coin"] for c in candidates[:len(weak)] if candidates)
        if adds:
            recs.append(f"Consider adding: {adds}")

    if recs:
        lines.append(f"\n<b>RECOMMENDATIONS:</b>")
        for r in recs:
            lines.append(f"  {r}")
    else:
        lines.append("\nAll coins performing well. No changes recommended.")

    return "\n".join(lines)


def run_rebalance(
    lookback_days: int = 365,
    top_n: int = 100,
    workers: int = 4,
    dry_run: bool = True,
) -> str:
    """Run the full rebalance pipeline. Returns the report text."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    print(f"Rebalance check: {start.date()} → {end.date()}, top {top_n} coins")

    # Step 1: Screen top N
    print("\n[1/4] Screening top coins...")
    top_coins = get_top_futures_coins(top_n)
    screen_results = screen_all(top_coins, start, end, workers=workers)
    _print_screen_results(screen_results)

    # Step 2: Filter candidates
    print("\n[2/4] Filtering candidates (tp_rate >= 25%, entries >= 50)...")
    valid = [
        r for r in screen_results
        if "error" not in r
        and r.get("tp_rate", 0) >= MIN_TP_RATE
        and r.get("entries", 0) >= MIN_ENTRIES
    ]
    candidate_coins = [r["coin"] for r in valid]
    # Always include current coins even if they didn't pass screening
    current_coins = list(config.COINS)
    all_coins = list(dict.fromkeys(candidate_coins + current_coins))
    print(f"  {len(candidate_coins)} candidates passed screening, {len(all_coins)} total to backtest")

    # Step 3: Backtest all
    print(f"\n[3/4] Backtesting {len(all_coins)} coins...")
    bt_results = _backtest_coins(all_coins, start, end, workers=workers)

    current_bt = {c: bt_results[c] for c in current_coins if c in bt_results}
    candidate_bt = {c: bt_results[c] for c in candidate_coins if c in bt_results}

    # Step 4: Compare and report
    print("\n[4/4] Comparing results...")
    ok, weak, candidates = _compare_results(current_coins, current_bt, candidate_bt)

    report = _format_report(ok, weak, candidates, start, end)
    print(f"\n{'=' * 60}")
    # Print plain text version (strip HTML tags for console)
    import re
    print(re.sub(r"<[^>]+>", "", report))
    print(f"{'=' * 60}")

    if not dry_run:
        from app.swing.notifier import send
        send(report)
        print("Telegram report sent.")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebalance coin list: screen, backtest, report")
    parser.add_argument("--lookback-days", type=int, default=365, help="Backtest lookback period in days")
    parser.add_argument("--top", type=int, default=100, help="Screen top N coins by market cap")
    parser.add_argument("--workers", type=int, default=4, help="Parallel threads (default: 4, lower to avoid rate limits)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print report only, don't send Telegram (default)")
    parser.add_argument("--notify", action="store_true", help="Send report via Telegram")
    args = parser.parse_args()

    dry_run = not args.notify
    run_rebalance(
        lookback_days=args.lookback_days,
        top_n=args.top,
        workers=args.workers,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
