"""Statistics, reporting, and print helpers."""

from __future__ import annotations

from datetime import datetime
from statistics import mean, median

from .engine import StrategyState, Trade, _summarize, _fmt_pct


def _exit_breakdown(trades: list[Trade]) -> dict[str, dict]:
    """Group trades by exit reason; return count/win_rate/avg_pnl/median_pnl per reason."""
    buckets: dict[str, list[float]] = {}
    for t in trades:
        buckets.setdefault(t.exit_reason, []).append(t.pnl)
    result = {}
    for reason, pnls in sorted(buckets.items(), key=lambda x: -len(x[1])):
        wins = sum(1 for p in pnls if p > 0)
        result[reason] = {
            "count": len(pnls),
            "wins": wins,
            "win_rate": wins / len(pnls),
            "net_pnl": sum(pnls),
            "avg_pnl": mean(pnls),
            "median_pnl": median(pnls),
        }
    return result


def _print_exit_breakdown(title: str, v1_trades: list[Trade], v2_trades: list[Trade]) -> None:
    print(f"\n{title}")
    for label, trades in (("v1", v1_trades), ("v2", v2_trades)):
        bd = _exit_breakdown(trades)
        if not bd:
            continue
        print(f"\n  [{label}]  exit_reason | count | win_rate | net_pnl | avg_pnl | median_pnl")
        print(f"  {'─' * 85}")
        for reason, s in bd.items():
            print(
                f"  {reason:<45} | {s['count']:>5} | {_fmt_pct(s['win_rate']):>8} "
                f"| {s['net_pnl']:>8.2f} | {s['avg_pnl']:>8.3f} | {s['median_pnl']:>10.3f}"
            )


def _print_entry_analysis(title: str, v1_trades: list[Trade], v2_trades: list[Trade]) -> None:
    """For each exit reason, show avg entry RSI, ADX, confidence, and long/short split."""
    print(f"\n{title}")
    for label, trades in (("v1", v1_trades), ("v2", v2_trades)):
        if not trades:
            continue
        buckets: dict[str, list[Trade]] = {}
        for t in trades:
            buckets.setdefault(t.exit_reason, []).append(t)
        print(f"\n  [{label}]  exit_reason | n | long% | avg_rsi | avg_adx | avg_conf | trending% | net_pnl")
        print(f"  {'─' * 95}")
        for reason, ts in sorted(buckets.items(), key=lambda x: -len(x[1])):
            long_pct = sum(1 for t in ts if t.side == "long") / len(ts) * 100
            avg_rsi = mean(t.entry_rsi for t in ts)
            avg_adx = mean(t.entry_adx for t in ts)
            avg_conf = mean(t.confidence for t in ts)
            trending_pct = sum(1 for t in ts if t.entry_regime == "trending") / len(ts) * 100
            net_pnl = sum(t.pnl for t in ts)
            print(
                f"  {reason:<45} | {len(ts):>3} | {long_pct:>5.0f}% | {avg_rsi:>7.1f} "
                f"| {avg_adx:>7.1f} | {avg_conf:>8.2f} | {trending_pct:>9.0f}% | {net_pnl:>8.2f}"
            )


def _print_summary(title: str, rows: list[tuple[str, dict[str, float], dict[str, float]]]) -> None:
    print(f"\n{title}")
    print("coin | strat | trades | win_rate | net_pnl | gross_pnl | fees | avg_pnl | pf | max_dd | avg_conf")
    print("-" * 118)
    for coin, a, b in rows:
        print(
            f"{coin} | v1 | {int(a['trades'])} | {_fmt_pct(a['win_rate'])} | {a['net_pnl']:.2f} | "
            f"{a['gross_pnl']:.2f} | {a['total_fees']:.2f} | {a['avg_pnl']:.2f} | "
            f"{a['profit_factor']:.2f} | {a['max_drawdown']:.2f} | {a['avg_conf']:.2f}"
        )
        print(
            f"{coin} | v2 | {int(b['trades'])} | {_fmt_pct(b['win_rate'])} | {b['net_pnl']:.2f} | "
            f"{b['gross_pnl']:.2f} | {b['total_fees']:.2f} | {b['avg_pnl']:.2f} | "
            f"{b['profit_factor']:.2f} | {b['max_drawdown']:.2f} | {b['avg_conf']:.2f}"
        )


def _print_roi_summary(
    agg_v1: StrategyState,
    agg_v2: StrategyState,
    start: datetime,
    end: datetime,
    num_coins: int,
    target_annual_roi: float = 10.0,
) -> None:
    """Print annualized ROI and pass/fail against target."""
    days = (end - start).total_seconds() / 86400.0
    if days <= 0:
        print("\nROI Summary: invalid date range")
        return

    # Capital = coins * base margin per position
    # v1: fixed $5, v2: $5-$10 range midpoint $7.50
    capital_v1 = num_coins * 5.0
    capital_v2 = num_coins * 7.5

    s_v1 = _summarize(agg_v1)
    s_v2 = _summarize(agg_v2)

    print(f"\nROI Summary  ({num_coins} coins, {days:.0f} days, target {target_annual_roi:.1f}% annual)")
    print(f"{'─' * 90}")
    print(f"{'strat':<6} | {'capital':>8} | {'net_pnl':>8} | {'roi%':>7} | {'annual_roi%':>11} | {'target':>7} | result")
    print(f"{'─' * 90}")

    for label, capital, summary in [("v1", capital_v1, s_v1), ("v2", capital_v2, s_v2)]:
        net = summary["net_pnl"]
        roi = (net / capital) * 100.0 if capital > 0 else 0.0
        annual_roi = roi * (365.0 / days)
        passed = annual_roi >= target_annual_roi
        result = "PASS" if passed else "FAIL"
        print(
            f"{label:<6} | ${capital:>7.2f} | ${net:>7.2f} | {roi:>6.2f}% | {annual_roi:>10.2f}% | {target_annual_roi:>6.1f}% | {result}"
        )
