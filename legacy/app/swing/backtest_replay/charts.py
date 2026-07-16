"""Matplotlib chart generation for backtest results."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import StrategyState, Trade


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _build_equity_series(trades: list["Trade"]) -> tuple[list[datetime], list[float]]:
    """Build (timestamps, cumulative_pnl) from sorted trades."""
    sorted_trades = sorted(trades, key=lambda t: t.exit_time)
    times = [_ms_to_dt(t.exit_time) for t in sorted_trades]
    cum = 0.0
    values = []
    for t in sorted_trades:
        cum += t.pnl
        values.append(cum)
    return times, values


def _build_drawdown_series(times: list[datetime], values: list[float]) -> list[float]:
    """Drawdown depth below running peak."""
    peak = 0.0
    dd = []
    for v in values:
        peak = max(peak, v)
        dd.append(v - peak)
    return dd


def plot_results(
    coin_results: dict[str, tuple],
    agg_v1: "StrategyState",
    agg_v2: "StrategyState",
    out_dir: str,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    os.makedirs(out_dir, exist_ok=True)

    _plot_equity_curve(plt, mdates, coin_results, agg_v1, agg_v2, out_dir)
    _plot_drawdown(plt, mdates, agg_v1, agg_v2, out_dir)
    _plot_pnl_distribution(plt, agg_v1, agg_v2, out_dir)
    _plot_exit_reasons(plt, agg_v2, out_dir)
    _plot_monthly_heatmap(plt, coin_results, out_dir)
    _plot_per_coin_bar(plt, coin_results, out_dir)

    print(f"Charts saved to {out_dir}/")


def _plot_equity_curve(plt, mdates, coin_results, agg_v1, agg_v2, out_dir):
    fig, axes = plt.subplots(
        len(coin_results) + 1, 1,
        figsize=(14, 4 * (len(coin_results) + 1)),
        sharex=False,
    )
    if len(coin_results) == 0:
        axes = [axes]

    ax_agg = axes[0]
    t1, v1 = _build_equity_series(agg_v1.trades)
    t2, v2 = _build_equity_series(agg_v2.trades)
    if t1:
        ax_agg.plot(t1, v1, label="v1", color="#888", linewidth=1, linestyle="--")
    if t2:
        ax_agg.plot(t2, v2, label="v2", color="#1f77b4", linewidth=1.5)
    ax_agg.axhline(0, color="black", linewidth=0.5)
    ax_agg.set_title("Aggregate equity curve")
    ax_agg.set_ylabel("Cumulative net PnL ($)")
    ax_agg.legend()
    ax_agg.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_agg.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_agg.xaxis.get_majorticklabels(), rotation=45)

    for i, (coin, (sv1, sv2, _)) in enumerate(coin_results.items()):
        ax = axes[i + 1]
        ct1, cv1 = _build_equity_series(sv1.trades)
        ct2, cv2 = _build_equity_series(sv2.trades)
        if ct1:
            ax.plot(ct1, cv1, label="v1", color="#888", linewidth=1, linestyle="--")
        if ct2:
            ax.plot(ct2, cv2, label="v2", color="#1f77b4", linewidth=1.5)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(f"{coin} equity curve")
        ax.set_ylabel("Cum. PnL ($)")
        ax.legend(fontsize=7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "equity_curve.png"), dpi=120)
    plt.close(fig)


def _plot_drawdown(plt, mdates, agg_v1, agg_v2, out_dir):
    fig, ax = plt.subplots(figsize=(14, 4))

    t1, v1 = _build_equity_series(agg_v1.trades)
    t2, v2 = _build_equity_series(agg_v2.trades)
    if t1:
        dd1 = _build_drawdown_series(t1, v1)
        ax.fill_between(t1, dd1, 0, alpha=0.3, color="#888", label="v1 drawdown")
        ax.plot(t1, dd1, color="#888", linewidth=0.8, linestyle="--")
    if t2:
        dd2 = _build_drawdown_series(t2, v2)
        ax.fill_between(t2, dd2, 0, alpha=0.4, color="#d62728", label="v2 drawdown")
        ax.plot(t2, dd2, color="#d62728", linewidth=1)

    ax.set_title("Aggregate drawdown (depth below equity peak)")
    ax.set_ylabel("Drawdown ($)")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "drawdown.png"), dpi=120)
    plt.close(fig)


def _plot_pnl_distribution(plt, agg_v1, agg_v2, out_dir):
    fig, ax = plt.subplots(figsize=(10, 5))

    v1_pnls = [t.pnl for t in agg_v1.trades]
    v2_pnls = [t.pnl for t in agg_v2.trades]

    if v1_pnls or v2_pnls:
        all_vals = v1_pnls + v2_pnls
        lo, hi = min(all_vals), max(all_vals)
        bins = 40
        if v1_pnls:
            ax.hist(v1_pnls, bins=bins, range=(lo, hi), alpha=0.5, color="#888", label=f"v1 (n={len(v1_pnls)})", density=True)
        if v2_pnls:
            ax.hist(v2_pnls, bins=bins, range=(lo, hi), alpha=0.6, color="#1f77b4", label=f"v2 (n={len(v2_pnls)})", density=True)

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Per-trade net PnL distribution")
    ax.set_xlabel("Net PnL ($)")
    ax.set_ylabel("Density")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "pnl_distribution.png"), dpi=120)
    plt.close(fig)


def _plot_exit_reasons(plt, agg_v2, out_dir):
    from collections import Counter
    fig, (ax_count, ax_pnl) = plt.subplots(1, 2, figsize=(14, 6))

    buckets: dict[str, list[float]] = defaultdict(list)
    for t in agg_v2.trades:
        buckets[t.exit_reason].append(t.pnl)

    if not buckets:
        plt.close(fig)
        return

    reasons = sorted(buckets, key=lambda r: -len(buckets[r]))
    counts = [len(buckets[r]) for r in reasons]
    net_pnls = [sum(buckets[r]) for r in reasons]
    colors_pnl = ["#2ca02c" if p >= 0 else "#d62728" for p in net_pnls]

    y = range(len(reasons))
    ax_count.barh(list(y), counts, color="#1f77b4")
    ax_count.set_yticks(list(y))
    ax_count.set_yticklabels(reasons, fontsize=8)
    ax_count.set_title("Exit reason — trade count (v2)")
    ax_count.set_xlabel("Count")

    ax_pnl.barh(list(y), net_pnls, color=colors_pnl)
    ax_pnl.set_yticks(list(y))
    ax_pnl.set_yticklabels(reasons, fontsize=8)
    ax_pnl.axvline(0, color="black", linewidth=0.8)
    ax_pnl.set_title("Exit reason — net PnL (v2)")
    ax_pnl.set_xlabel("Net PnL ($)")

    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "exit_reasons.png"), dpi=120)
    plt.close(fig)


def _plot_monthly_heatmap(plt, coin_results, out_dir):
    """Coin × year-month grid, colored by v2 net PnL."""
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_months: set[str] = set()

    for coin, (_, sv2, _) in coin_results.items():
        for t in sv2.trades:
            month_key = _ms_to_dt(t.exit_time).strftime("%Y-%m")
            monthly[coin][month_key] += t.pnl
            all_months.add(month_key)

    if not all_months:
        return

    months = sorted(all_months)
    coins = list(coin_results.keys())
    data = [[monthly[coin].get(m, 0.0) for m in months] for coin in coins]

    if not data:
        return

    fig, ax = plt.subplots(figsize=(max(12, len(months) * 0.5), max(4, len(coins) * 0.6)))

    # Symmetric color scale
    flat = [v for row in data for v in row]
    vmax = max(abs(min(flat)), abs(max(flat))) if flat else 1.0
    vmax = max(vmax, 0.01)

    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=90, fontsize=7)
    ax.set_yticks(range(len(coins)))
    ax.set_yticklabels(coins)
    ax.set_title("Monthly PnL heatmap (v2, $ per coin)")
    fig.colorbar(im, ax=ax, label="Net PnL ($)")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "monthly_heatmap.png"), dpi=120)
    plt.close(fig)


def _plot_per_coin_bar(plt, coin_results, out_dir):
    from .engine import _summarize

    coins = list(coin_results.keys())
    v1_pnl = [_summarize(coin_results[c][0])["net_pnl"] for c in coins]
    v2_pnl = [_summarize(coin_results[c][1])["net_pnl"] for c in coins]

    x = range(len(coins))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(8, len(coins) * 1.2), 5))
    bars1 = ax.bar([i - width / 2 for i in x], v1_pnl, width, label="v1", color="#888", alpha=0.8)
    bars2 = ax.bar([i + width / 2 for i in x], v2_pnl, width, label="v2", color="#1f77b4", alpha=0.9)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(coins)
    ax.set_title("Per-coin net PnL: v1 vs v2")
    ax.set_ylabel("Net PnL ($)")
    ax.legend()

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + (0.05 if h >= 0 else -0.1),
                f"{h:.1f}", ha="center", va="bottom" if h >= 0 else "top", fontsize=7)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + (0.05 if h >= 0 else -0.1),
                f"{h:.1f}", ha="center", va="bottom" if h >= 0 else "top", fontsize=7)

    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "per_coin_bar.png"), dpi=120)
    plt.close(fig)
