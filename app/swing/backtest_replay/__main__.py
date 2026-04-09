"""CLI entry point: python -m app.swing.backtest_replay"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from . import strategy
from .engine import ReplayEngine, StrategyState, _summarize, _parse_iso_utc
from .stats import _print_summary, _print_exit_breakdown, _print_entry_analysis, _print_roi_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay backtest: compare swing v1 vs v2")
    coin_group = parser.add_mutually_exclusive_group()
    coin_group.add_argument("--coins", default=None, help="Comma-separated coin tickers")
    coin_group.add_argument("--top", type=int, default=None, help="Use top N coins by market cap (fetched from CoinGecko, validated against Binance Futures)")
    parser.add_argument("--start", default=None, help="UTC ISO datetime, e.g. 2025-01-01T00:00:00Z")
    parser.add_argument("--end", default=None, help="UTC ISO datetime, e.g. 2026-01-01T00:00:00Z")
    parser.add_argument("--fee-bps", type=float, default=0.0, help="Fee per side in basis points (e.g. 4 = 0.04%%)")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Adverse slippage per side in basis points")
    parser.add_argument("--exit-breakdown", action="store_true", help="Print exit-reason breakdown with win rate and PnL per reason")
    parser.add_argument("--entry-analysis", action="store_true", help="Print entry condition breakdown by exit reason")
    parser.add_argument("--no-macd-div-exit", action="store_true", help="Disable the MACD divergence exit for both long and short")
    parser.add_argument("--workers", type=int, default=8, help="Parallel threads for coin processing (default: 8)")
    parser.add_argument("--charts", metavar="DIR", default=None, help="Save matplotlib charts to DIR (e.g. charts_out/10yr)")
    parser.add_argument("--target-roi", type=float, default=10.0, help="Target annualized ROI%% for pass/fail check (default: 10)")
    parser.add_argument("--screen", action="store_true", help="Run coin fitness screening instead of backtest")
    args = parser.parse_args()

    strategy._DISABLE_MACD_DIV_EXIT = args.no_macd_div_exit

    end = _parse_iso_utc(args.end) if args.end else datetime.now(timezone.utc)
    start = _parse_iso_utc(args.start) if args.start else (end - timedelta(days=180))

    if args.top:
        from .universe import get_top_futures_coins
        coins = get_top_futures_coins(args.top)
    elif args.coins:
        coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    else:
        coins = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "SUI"]

    if args.screen:
        from .screener import screen_all, _print_screen_results
        print(f"Screening {len(coins)} coins from {start.isoformat()} to {end.isoformat()}")
        results = screen_all(coins, start, end, workers=args.workers)
        _print_screen_results(results)
        return

    engine = ReplayEngine(
        coins,
        start,
        end,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    mixed_note = " [--no-macd-div-exit]" if args.no_macd_div_exit else ""
    print(f"Running replay from {start.isoformat()} to {end.isoformat()} for {', '.join(coins)}{mixed_note}")
    print(f"Cost model: fee={args.fee_bps:.2f} bps/side, slippage={args.slippage_bps:.2f} bps/side  workers={args.workers}")

    coin_results = engine.run_all(workers=args.workers)

    agg_v1 = StrategyState("v1", fee_rate=engine.fee_rate, slippage_rate=engine.slippage_rate)
    agg_v2 = StrategyState("v2", fee_rate=engine.fee_rate, slippage_rate=engine.slippage_rate)

    rows: list[tuple[str, dict, dict]] = []
    for coin in coins:
        if coin not in coin_results:
            continue
        v1, v2, _ = coin_results[coin]
        rows.append((coin, _summarize(v1), _summarize(v2)))
        agg_v1.trades.extend(v1.trades)
        agg_v2.trades.extend(v2.trades)
        agg_v1.entries_conf.extend(v1.entries_conf)
        agg_v2.entries_conf.extend(v2.entries_conf)
        agg_v1.equity_curve.extend(v1.equity_curve[1:])
        agg_v2.equity_curve.extend(v2.equity_curve[1:])

    _print_summary("Per-coin results", rows)
    _print_summary("Aggregate results", [("TOTAL", _summarize(agg_v1), _summarize(agg_v2))])

    if args.exit_breakdown:
        _print_exit_breakdown("Exit reason breakdown (aggregate)", agg_v1.trades, agg_v2.trades)

    if args.entry_analysis:
        _print_entry_analysis("Entry condition analysis by exit reason", agg_v1.trades, agg_v2.trades)

    _print_roi_summary(agg_v1, agg_v2, start, end, len(coins), args.target_roi)

    print("\nNotes:")
    print("- Uses public kline data only; funding/OI/L-S/taker are neutralized to baseline values.")
    print("- Fees/slippage are modeled per side using CLI parameters; latency still not modeled.")
    print("- Intrabar SL/TP tie-break is conservative (SL assumed first if both touch in same candle).")

    if args.charts:
        from .charts import plot_results
        plot_results(coin_results, agg_v1, agg_v2, args.charts)


if __name__ == "__main__":
    main()
