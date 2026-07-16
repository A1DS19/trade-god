"""Grid search over strategy entry/exit parameters.

Precomputes all indicator snapshots once, then sweeps parameter combinations
using ProcessPoolExecutor. Each worker receives the cached snapshots and
runs its batch of combos without re-fetching or re-computing indicators.

Usage:
    python -m app.swing.grid_search [--coins ...] [--start ...] [--end ...]
                                    [--fee-bps 4] [--slippage-bps 2]
                                    [--workers 4] [--top 20] [--min-trades 40]
"""

from __future__ import annotations

import argparse
import itertools
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from typing import Any

from binance.client import Client

from app.swing.backtest_replay import ReplayEngine

LEVERAGE = 5
POSITION_USDT = 5.0
MIXED_EMA_LOSS_GUARD = 0.005  # keep fixed; we tested sweeping this and it hurt

GRID: dict[str, list[float]] = {
    "rsi_short_min":    [42.0, 45.0, 48.0, 50.0, 52.0],   # shorts: RSI must be > this
    "rsi_long_max":     [48.0, 50.0, 52.0, 55.0, 58.0],   # longs:  RSI must be < this
    "adx_min":          [25.0, 28.0, 30.0, 32.0],
    "macd_div_rsi_long":  [58.0, 62.0, 65.0, 68.0],       # exit long when RSI > this + MACD diverging
    "macd_div_rsi_short": [32.0, 35.0, 38.0, 42.0],       # exit short when RSI < this + MACD diverging
}
PARAM_KEYS = list(GRID.keys())

# Worker-process globals (set once via initializer, read-only during tasks)
_SNAPSHOTS: dict[str, list[dict[str, Any] | None]] = {}
_FEE_RATE: float = 0.0
_SLIPPAGE_RATE: float = 0.0


def _init_worker(snapshots: dict, fee_rate: float, slippage_rate: float) -> None:
    global _SNAPSHOTS, _FEE_RATE, _SLIPPAGE_RATE
    _SNAPSHOTS = snapshots
    _FEE_RATE = fee_rate
    _SLIPPAGE_RATE = slippage_rate


# ---------------------------------------------------------------------------
# Parameterized strategy logic (no confidence scoring — shown to be useless)
# ---------------------------------------------------------------------------

def _can_enter(direction: str, snap: dict, rsi_short_min: float, rsi_long_max: float, adx_min: float) -> bool:
    if snap["market_regime"] == "ranging":
        return False
    ind = snap["indicators"]
    req = "bearish" if direction == "short" else "bullish"
    if ind["daily_ema_alignment"] != req:
        return False
    if ind["ema_alignment"] != req:
        return False
    if ind["adx14"] < adx_min:
        return False
    macd = ind["macd_hist"]
    rsi = ind["rsi14_4h"]
    if direction == "short":
        return macd < 0 and rsi > rsi_short_min
    return macd > 0 and rsi < rsi_long_max


def _rule_exit(
    side: str,
    ind: dict,
    unrealized_pct: float,
    macd_div_rsi_long: float,
    macd_div_rsi_short: float,
) -> str | None:
    ema4h = ind["ema_alignment"]
    ema_d = ind["daily_ema_alignment"]
    rsi = ind["rsi14_4h"]
    macd = ind["macd_hist"]
    macd_p = ind["macd_hist_prev"]
    oi = ind["oi_change_4h_pct"]
    adx = ind["adx14"]

    if side == "short":
        if ema4h == "bullish":
            return "4h EMA turned bullish"
        if ema_d == "bullish":
            return "daily EMA turned bullish"
        if ema4h == "mixed" and macd > macd_p and adx < 25 and unrealized_pct < -MIXED_EMA_LOSS_GUARD:
            return "4h EMA mixed + MACD weakening"
        if rsi < 32:
            return "RSI deep oversold"
        if macd > macd_p and rsi < macd_div_rsi_short:
            return "MACD divergence (short)"
        if oi < -3 and macd > macd_p:
            return "OI falling (shorts covering)"
        if adx < 20:
            return "ADX trend collapsed"
    else:
        if ema4h == "bearish":
            return "4h EMA turned bearish"
        if ema_d == "bearish":
            return "daily EMA turned bearish"
        if ema4h == "mixed" and macd < macd_p and adx < 25 and unrealized_pct < -MIXED_EMA_LOSS_GUARD:
            return "4h EMA mixed + MACD weakening"
        if rsi > 68:
            return "RSI deep overbought"
        if macd < macd_p and rsi > macd_div_rsi_long:
            return "MACD divergence (long)"
        if oi < -3 and macd < macd_p:
            return "OI falling (longs covering)"
        if adx < 20:
            return "ADX trend collapsed"
    return None


def _close_pnl(side: str, entry: float, qty: float, notional: float, entry_fee: float, exit_price: float, fee_rate: float) -> float:
    if side == "long":
        gross = (exit_price - entry) * qty
    else:
        gross = (entry - exit_price) * qty
    exit_fee = abs(exit_price * qty) * fee_rate
    return gross - entry_fee - exit_fee


def _run_combo(params_tuple: tuple[float, ...]) -> tuple[tuple, dict]:
    rsi_short_min, rsi_long_max, adx_min, macd_div_rsi_long, macd_div_rsi_short = params_tuple
    fee = _FEE_RATE
    slip = _SLIPPAGE_RATE
    notional = POSITION_USDT * LEVERAGE

    trades: list[dict] = []

    for coin, snaps in _SNAPSHOTS.items():
        pos: dict | None = None

        for snap in snaps:
            if snap is None:
                continue

            ind = snap["indicators"]
            price = snap["price"]
            high = snap["high"]
            low = snap["low"]
            now_ms = snap["close_time_ms"]

            # 1. Intrabar SL/TP (checked before rule exits)
            if pos is not None:
                if pos["side"] == "long":
                    sl_p = pos["entry"] * (1 - pos["sl"])
                    tp_p = pos["entry"] * (1 + pos["tp"])
                    hit_sl = low <= sl_p
                    hit_tp = high >= tp_p
                else:
                    sl_p = pos["entry"] * (1 + pos["sl"])
                    tp_p = pos["entry"] * (1 - pos["tp"])
                    hit_sl = high >= sl_p
                    hit_tp = low <= tp_p

                if hit_sl or hit_tp:
                    exit_p = sl_p if hit_sl else tp_p
                    pnl = _close_pnl(pos["side"], pos["entry"], pos["qty"], notional, pos["fee"], exit_p, fee)
                    trades.append({"pnl": pnl, "exit": "SL" if hit_sl else "TP", "side": pos["side"], "entry_rsi": pos["entry_rsi"], "entry_adx": pos["entry_adx"]})
                    pos = None
                    continue

            # 2. Rule-based exit
            if pos is not None:
                entry = pos["entry"]
                unrealized = (price - entry) / entry if pos["side"] == "long" else (entry - price) / entry
                reason = _rule_exit(pos["side"], ind, unrealized, macd_div_rsi_long, macd_div_rsi_short)
                if reason:
                    exit_p = price * (1 - slip) if pos["side"] == "long" else price * (1 + slip)
                    pnl = _close_pnl(pos["side"], entry, pos["qty"], notional, pos["fee"], exit_p, fee)
                    trades.append({"pnl": pnl, "exit": reason, "side": pos["side"], "entry_rsi": pos["entry_rsi"], "entry_adx": pos["entry_adx"]})
                    pos = None
                # hold or just closed — either way don't enter this bar
                continue

            # 3. Entry (only when flat)
            for direction in ("short", "long"):
                if _can_enter(direction, snap, rsi_short_min, rsi_long_max, adx_min):
                    entry_p = price * (1 + slip) if direction == "long" else price * (1 - slip)
                    qty = notional / entry_p if entry_p > 0 else 0.0
                    if qty <= 0:
                        continue
                    pos = {
                        "side": direction,
                        "entry": entry_p,
                        "qty": qty,
                        "fee": abs(entry_p * qty) * fee,
                        "sl": snap["suggested_sl_pct"],
                        "tp": snap["suggested_tp_pct"],
                        "entry_rsi": ind["rsi14_4h"],
                        "entry_adx": ind["adx14"],
                    }
                    break

        # Mark-to-market at end of coin window
        if pos is not None:
            valid = [s for s in snaps if s is not None]
            if valid:
                last_p = valid[-1]["price"]
                pnl = _close_pnl(pos["side"], pos["entry"], pos["qty"], notional, pos["fee"], last_p, fee)
                trades.append({"pnl": pnl, "exit": "EOD", "side": pos["side"], "entry_rsi": pos["entry_rsi"], "entry_adx": pos["entry_adx"]})
            pos = None

    return params_tuple, _stats(trades)


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "net_pnl": 0.0, "pf": 0.0, "avg_pnl": 0.0, "median_pnl": 0.0, "max_dd": 0.0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    equity, peak, mdd = 0.0, 0.0, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    return {
        "n": len(trades),
        "win_rate": len(wins) / len(trades),
        "net_pnl": sum(pnls),
        "pf": gp / gl if gl > 0 else (999.0 if gp > 0 else 0.0),
        "avg_pnl": mean(pnls),
        "median_pnl": median(pnls),
        "max_dd": mdd,
        "_trades": trades,  # kept for detail mode, stripped before display
    }


def _print_detail(label: str, params_tuple: tuple, stats: dict) -> None:
    p = dict(zip(PARAM_KEYS, params_tuple))
    print(f"\n{'='*80}")
    print(f"DETAIL: rsi_sh={p['rsi_short_min']:.0f}  rsi_lo={p['rsi_long_max']:.0f}  adx={p['adx_min']:.0f}  mdiv_l={p['macd_div_rsi_long']:.0f}  mdiv_s={p['macd_div_rsi_short']:.0f}")
    print(f"        n={stats['n']}  win={stats['win_rate']*100:.1f}%  net_pnl={stats['net_pnl']:.2f}  pf={stats['pf']:.2f}  max_dd={stats['max_dd']:.2f}")

    trades = stats["_trades"]
    buckets: dict[str, list[dict]] = {}
    for t in trades:
        buckets.setdefault(t["exit"], []).append(t)

    print(f"\n  exit_reason                                  | n  | win% | net_pnl | avg_pnl | med_pnl | avg_rsi | avg_adx | long%")
    print(f"  {'─'*105}")
    for reason, ts in sorted(buckets.items(), key=lambda x: -len(x[1])):
        pnls = [t["pnl"] for t in ts]
        w = sum(1 for p in pnls if p > 0)
        avg_rsi = mean(t["entry_rsi"] for t in ts)
        avg_adx = mean(t["entry_adx"] for t in ts)
        long_pct = sum(1 for t in ts if t["side"] == "long") / len(ts) * 100
        print(
            f"  {reason:<45} | {len(ts):>2} | {w/len(ts)*100:>4.0f}% "
            f"| {sum(pnls):>7.2f} | {mean(pnls):>7.3f} | {median(pnls):>7.3f} "
            f"| {avg_rsi:>7.1f} | {avg_adx:>7.1f} | {long_pct:>5.0f}%"
        )


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def _fetch_coin(engine: ReplayEngine, coin: str) -> tuple[str, list, list]:
    client = Client()
    symbol = f"{coin}USDT"
    start_ms = int(engine.start.timestamp() * 1000)
    end_ms = int(engine.end.timestamp() * 1000)
    kl4 = engine._fetch_klines(client, symbol, Client.KLINE_INTERVAL_4HOUR, start_ms, end_ms)
    kl1d = engine._fetch_klines(
        client, symbol, Client.KLINE_INTERVAL_1DAY,
        start_ms - int(timedelta(days=250).total_seconds() * 1000), end_ms,
    )
    return coin, kl4, kl1d


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Grid search over swing strategy parameters")
    parser.add_argument("--coins", default="BTC,ETH,SOL,BNB,DOGE,AVAX,LINK,SUI")
    parser.add_argument("--start", default="2021-01-01T00:00:00Z")
    parser.add_argument("--end", default="2026-01-01T00:00:00Z")
    parser.add_argument("--fee-bps", type=float, default=4.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=4, help="Process workers for combo evaluation")
    parser.add_argument("--top", type=int, default=30, help="Number of top results to print")
    parser.add_argument("--min-trades", type=int, default=40, help="Minimum trades to include result")
    parser.add_argument("--sort-by", default="pf", choices=["pf", "net_pnl", "win_rate"], help="Sort metric")
    parser.add_argument("--detail", type=int, default=0, help="Print full exit breakdown for top N combos")
    args = parser.parse_args()

    fee_rate = args.fee_bps / 10_000.0
    slippage_rate = args.slippage_bps / 10_000.0

    def _parse_dt(s: str) -> datetime:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)

    start = _parse_dt(args.start)
    end = _parse_dt(args.end)
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]

    engine = ReplayEngine(coins, start, end, fee_bps=args.fee_bps, slippage_bps=args.slippage_bps)

    # ── Step 1: fetch klines (parallel, one client per thread) ──────────────
    print(f"Fetching klines for {len(coins)} coins...")
    raw: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=len(coins)) as ex:
        futures = {ex.submit(_fetch_coin, engine, coin): coin for coin in coins}
        for fut in as_completed(futures):
            coin, kl4, kl1d = fut.result()
            raw[coin] = (kl4, kl1d)
            print(f"  {coin}: {len(kl4)} 4h bars, {len(kl1d)} daily bars")

    # ── Step 2: precompute all indicator snapshots (O(n), done once) ─────────
    print("Precomputing indicators...")
    snapshots: dict[str, list] = {}
    for coin in coins:
        kl4, kl1d = raw[coin]
        snapshots[coin] = engine._precompute_coin(kl4, kl1d)
        valid = sum(1 for s in snapshots[coin] if s is not None)
        print(f"  {coin}: {valid} valid bars")

    # ── Step 3: generate and run all combos ───────────────────────────────────
    combos = list(itertools.product(*[GRID[k] for k in PARAM_KEYS]))
    total = len(combos)
    print(f"\nRunning {total} combinations ({args.workers} workers)...")

    results: list[tuple[tuple, dict]] = []
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_init_worker,
        initargs=(snapshots, fee_rate, slippage_rate),
    ) as executor:
        futures_map = {executor.submit(_run_combo, combo): combo for combo in combos}
        done = 0
        for fut in as_completed(futures_map):
            params_tuple, stats = fut.result()
            results.append((params_tuple, stats))
            done += 1
            if done % 200 == 0 or done == total:
                print(f"  {done}/{total} done...", flush=True)

    # ── Step 4: filter, sort, print ───────────────────────────────────────────
    results = [(p, s) for p, s in results if s["n"] >= args.min_trades]
    results.sort(key=lambda x: x[1][args.sort_by], reverse=True)

    print(f"\nTop {args.top} by {args.sort_by} (min {args.min_trades} trades):")
    hdr = (
        f"{'rsi_sh':>6} {'rsi_lo':>6} {'adx':>5} {'mdiv_l':>7} {'mdiv_s':>7} "
        f"| {'n':>4} {'win%':>6} {'net_pnl':>8} {'pf':>5} {'avg':>7} {'med':>7} {'maxdd':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    for params_tuple, s in results[:args.top]:
        p = dict(zip(PARAM_KEYS, params_tuple))
        print(
            f"{p['rsi_short_min']:>6.0f} {p['rsi_long_max']:>6.0f} {p['adx_min']:>5.0f} "
            f"{p['macd_div_rsi_long']:>7.0f} {p['macd_div_rsi_short']:>7.0f} "
            f"| {s['n']:>4} {s['win_rate']*100:>5.1f}% {s['net_pnl']:>8.2f} "
            f"{s['pf']:>5.2f} {s['avg_pnl']:>7.3f} {s['median_pnl']:>7.3f} {s['max_dd']:>7.2f}"
        )

    if args.detail > 0:
        # Deduplicate by (net_pnl, pf) to avoid printing identical combos
        seen: set[tuple] = set()
        detail_candidates = []
        for params_tuple, s in results:
            key = (round(s["net_pnl"], 4), round(s["pf"], 4), s["n"])
            if key not in seen:
                seen.add(key)
                detail_candidates.append((params_tuple, s))
        for params_tuple, s in detail_candidates[:args.detail]:
            _print_detail("", params_tuple, s)

    if not results:
        print("No results met the minimum trade threshold.")
        return

    # Print baseline from results if present, otherwise note it
    baseline = (42.0, 58.0, 32.0, 62.0, 38.0)
    base_match = [(p, s) for p, s in results if p == baseline]
    print(f"\nBaseline (rsi_sh=42, rsi_lo=58, adx=32, mdiv_l=62, mdiv_s=38):")
    if base_match:
        _, s = base_match[0]
        p = dict(zip(PARAM_KEYS, baseline))
        print(
            f"{p['rsi_short_min']:>6.0f} {p['rsi_long_max']:>6.0f} {p['adx_min']:>5.0f} "
            f"{p['macd_div_rsi_long']:>7.0f} {p['macd_div_rsi_short']:>7.0f} "
            f"| {s['n']:>4} {s['win_rate']*100:>5.1f}% {s['net_pnl']:>8.2f} "
            f"{s['pf']:>5.2f} {s['avg_pnl']:>7.3f} {s['median_pnl']:>7.3f} {s['max_dd']:>7.2f}"
        )
    else:
        print("  (filtered out by --min-trades)")


if __name__ == "__main__":
    main()
