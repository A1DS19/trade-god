"""Walk-forward grid search over swing strategy parameters.

Precomputes indicator snapshots once for the full period, splits into
train/test windows, and evaluates parameter combinations with full
confidence scoring. Ranks by OOS (out-of-sample) performance to avoid
overfitting.

Usage:
    python -m app.swing.wf_grid_search \
        --coins DOGE,1000SHIB,RUNE,RENDER,1000FLOKI,TURBO,IP,BSV,IOTA \
        --fee-bps 4 --slippage-bps 2 --workers 4

Walk-forward splits:
    WF1: train 2021-01-01 -> 2024-06-30, test 2024-07-01 -> 2026-04-15
    WF2: train 2021-01-01 -> 2025-03-31, test 2025-04-01 -> 2026-04-15
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
from app.swing.backtest_replay.strategy import (
    _ema_alignment,
    _map_confidence,
    _score_entry_common,
)

LEVERAGE = 5
POSITION_USDT_MIN = 5.0
POSITION_USDT_MAX = 10.0
CONFIDENCE_SIZING_CAP = 0.95

# ── Parameter grid ────────────────────────────────────────────────────────────
GRID: dict[str, list[float]] = {
    "adx_min":              [25.0, 28.0, 30.0],
    "min_confidence":       [0.75, 0.80, 0.85],
    "borderline_penalty":   [0.05, 0.08, 0.12],
    "macd_div_rsi_long":    [62.0, 65.0, 68.0],
    "macd_div_rsi_short":   [32.0, 35.0, 38.0],
}
PARAM_KEYS = list(GRID.keys())

# Worker-process globals (set once via initializer, read-only during tasks)
_TRAIN_SNAPSHOTS: dict[str, list[dict[str, Any] | None]] = {}
_TEST_SNAPSHOTS: dict[str, list[dict[str, Any] | None]] = {}
_FEE_RATE: float = 0.0
_SLIPPAGE_RATE: float = 0.0


def _init_worker(
    train_snaps: dict, test_snaps: dict, fee_rate: float, slippage_rate: float
) -> None:
    global _TRAIN_SNAPSHOTS, _TEST_SNAPSHOTS, _FEE_RATE, _SLIPPAGE_RATE
    _TRAIN_SNAPSHOTS = train_snaps
    _TEST_SNAPSHOTS = test_snaps
    _FEE_RATE = fee_rate
    _SLIPPAGE_RATE = slippage_rate


# ── Position sizing (mirrors live config) ─────────────────────────────────────

def _position_size_usdt(confidence: float, min_conf: float) -> float:
    x = min(max(confidence, min_conf), CONFIDENCE_SIZING_CAP)
    ratio = (x - min_conf) / (CONFIDENCE_SIZING_CAP - min_conf) if CONFIDENCE_SIZING_CAP > min_conf else 0.0
    return round(POSITION_USDT_MIN + (POSITION_USDT_MAX - POSITION_USDT_MIN) * ratio, 2)


# ── Entry with confidence scoring ─────────────────────────────────────────────

def _try_entry(
    snap: dict,
    adx_min: float,
    min_confidence: float,
    borderline_penalty: float,
) -> dict | None:
    """Attempt entry with full confidence scoring. Returns position dict or None."""
    ind = snap["indicators"]
    regime = snap["market_regime"]

    if regime == "ranging":
        return None

    ema4h = ind["ema_alignment"]
    ema_d = ind["daily_ema_alignment"]
    rsi = ind["rsi14_4h"]
    adx = ind["adx14"]
    macd = ind["macd_hist"]
    plus_di = ind["plus_di"]
    minus_di = ind["minus_di"]

    for direction in ("short", "long"):
        req = "bearish" if direction == "short" else "bullish"
        if ema_d != req:
            continue
        if ema4h != req:
            continue
        if (direction == "short" and macd >= 0) or (direction == "long" and macd <= 0):
            continue
        if adx < adx_min:
            continue
        # DI alignment (always required)
        if direction == "short" and minus_di <= plus_di:
            continue
        if direction == "long" and plus_di <= minus_di:
            continue

        # Compute confidence with parameterized borderline penalty
        conf, reasons = _score_entry_confidence(
            direction, snap, borderline_penalty
        )

        if conf < min_confidence:
            continue

        usdt = _position_size_usdt(conf, min_confidence)
        notional = usdt * LEVERAGE
        price = snap["price"]
        entry_p = price * (1 + _SLIPPAGE_RATE) if direction == "long" else price * (1 - _SLIPPAGE_RATE)
        qty = notional / entry_p if entry_p > 0 else 0.0
        if qty <= 0:
            continue

        # Check TP covers costs (mirrors V2_MIN_TP_TO_COST_MULT / V2_MIN_NET_TP_PCT)
        tp_pct = snap["suggested_tp_pct"]
        roundtrip = 2.0 * (_FEE_RATE + _SLIPPAGE_RATE)
        if tp_pct < roundtrip * 3.0 or (tp_pct - roundtrip) < 0.004:
            continue

        return {
            "side": direction,
            "entry": entry_p,
            "qty": qty,
            "fee": abs(entry_p * qty) * _FEE_RATE,
            "sl": snap["suggested_sl_pct"],
            "tp": snap["suggested_tp_pct"],
            "conf": conf,
            "notional": notional,
        }

    return None


def _score_entry_confidence(
    direction: str, snap: dict, borderline_penalty: float
) -> tuple[float, list[str]]:
    """Score entry using the full confidence model with parameterized borderline penalty."""
    ind = snap["indicators"]
    regime = snap["market_regime"]

    # Temporarily override borderline penalty in the scoring
    # We call _score_entry_common which applies -0.08 for borderline,
    # then adjust for the parameterized penalty.
    conf, reasons = _score_entry_common(
        direction,
        regime,
        ind["rsi14_4h"],
        ind["vol_ratio"],
        snap.get("funding_rate_pct", 0.0),
        ind["oi_change_4h_pct"],
        ind["price_vs_ema200"],
        ind["plus_di"],
        ind["minus_di"],
        ind["macd_hist"],
        ind["macd_hist_prev"],
        ind["stoch_rsi_k"],
        ind["atr_pct_rank"],
        ind["price_vs_vwap"],
        ind.get("ls_ratio", 1.0),
        ind.get("taker_ratio", 1.0),
        rsi_soft_v2=True,
        partial_mode=False,
    )

    # _score_entry_common applies a hardcoded -0.08 for borderline.
    # Undo that and apply the parameterized penalty instead.
    if regime == "borderline" and borderline_penalty != 0.08:
        # The raw score before _map_confidence had -0.08 added.
        # We need to recompute with the correct penalty.
        # Reverse: get the raw score back, adjust, remap.
        conf_with_correct, reasons_fixed = _score_with_custom_penalty(
            direction, snap, borderline_penalty
        )
        return conf_with_correct, reasons_fixed

    return conf, reasons


def _score_with_custom_penalty(
    direction: str, snap: dict, borderline_penalty: float
) -> tuple[float, list[str]]:
    """Recompute confidence with a custom borderline penalty."""
    ind = snap["indicators"]
    regime = snap["market_regime"]
    score = 0.0
    reasons: list[str] = []

    def add(delta: float, label: str) -> None:
        nonlocal score
        score += delta
        reasons.append(f"{'+' if delta >= 0 else '-'}{abs(delta):.2f} {label}")

    rsi = ind["rsi14_4h"]
    vol = ind["vol_ratio"]
    funding = snap.get("funding_rate_pct", 0.0)
    oi_chg = ind["oi_change_4h_pct"]
    vs_ema200 = ind["price_vs_ema200"]
    plus_di = ind["plus_di"]
    minus_di = ind["minus_di"]
    macd = ind["macd_hist"]
    macd_p = ind["macd_hist_prev"]
    stoch_k = ind["stoch_rsi_k"]
    atr_rank = ind["atr_pct_rank"]
    vs_vwap = ind["price_vs_vwap"]
    ls_ratio = ind.get("ls_ratio", 1.0)
    taker_ratio = ind.get("taker_ratio", 1.0)

    # Confirming signals
    if vol > 1.5:
        add(0.05, f"vol {vol:.2f}")
    if direction == "short" and funding > 0.05:
        add(0.04, "funding crowded longs")
    elif direction == "long" and funding < -0.05:
        add(0.04, "funding crowded shorts")
    if direction == "short" and oi_chg > 1 and macd < macd_p * 0.95:
        add(0.04, "OI new shorts")
    elif direction == "long" and oi_chg > 1 and macd > macd_p * 1.05:
        add(0.04, "OI new longs")
    if 40 <= rsi <= 60:
        add(0.03, "RSI healthy")
    if direction == "short" and vs_ema200 < 0:
        add(0.03, "below EMA200")
    elif direction == "long" and vs_ema200 > 0:
        add(0.03, "above EMA200")
    if direction == "short" and minus_di > plus_di:
        add(0.04, "DI aligned")
    elif direction == "long" and plus_di > minus_di:
        add(0.04, "DI aligned")
    if direction == "short" and stoch_k > 80:
        add(0.04, "StochRSI OB")
    elif direction == "long" and stoch_k < 20:
        add(0.04, "StochRSI OS")
    if direction == "short" and ls_ratio >= 2.0:
        add(0.04, "L/S crowded")
    elif direction == "long" and ls_ratio <= 0.5:
        add(0.04, "L/S crowded")
    if direction == "short" and taker_ratio < 0.8:
        add(0.03, "takers selling")
    elif direction == "long" and taker_ratio > 1.2:
        add(0.03, "takers buying")
    if atr_rank > 70:
        add(0.03, "ATR expanding")
    if direction == "short" and vs_vwap < 0:
        add(0.03, "below VWAP")
    elif direction == "long" and vs_vwap > 0:
        add(0.03, "above VWAP")

    # Contradicting signals (v2 soft RSI)
    if direction == "short" and rsi < 42:
        add(-0.05, "RSI below short comfort")
    elif direction == "long" and rsi > 58:
        add(-0.05, "RSI above long comfort")
    if direction == "short" and rsi < 36:
        add(-0.04, "RSI deeply oversold")
    elif direction == "long" and rsi > 64:
        add(-0.04, "RSI deeply overbought")
    if direction == "short" and funding < -0.05:
        add(-0.04, "funding opposes short")
    elif direction == "long" and funding > 0.05:
        add(-0.04, "funding opposes long")
    if oi_chg < -2:
        add(-0.04, "OI closing")
    if direction == "short" and macd > macd_p:
        add(-0.04, "MACD contra short")
    elif direction == "long" and macd < macd_p:
        add(-0.04, "MACD contra long")
    if direction == "short" and stoch_k < 20:
        add(-0.03, "StochRSI already OS")
    elif direction == "long" and stoch_k > 80:
        add(-0.03, "StochRSI already OB")
    if direction == "short" and taker_ratio > 1.2:
        add(-0.02, "takers buying contra short")
    elif direction == "long" and taker_ratio < 0.8:
        add(-0.02, "takers selling contra long")
    if atr_rank < 30:
        add(-0.03, "ATR compressed")
    if direction == "short" and vs_vwap > 2:
        add(-0.02, "above VWAP contra short")
    elif direction == "long" and vs_vwap < -2:
        add(-0.02, "below VWAP contra long")

    # Parameterized borderline penalty
    if regime == "borderline":
        add(-borderline_penalty, "ADX borderline penalty")

    return _map_confidence(score), reasons


# ── Exit logic ────────────────────────────────────────────────────────────────

MIXED_EMA_LOSS_GUARD = 0.005


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
            return "4h_EMA_bull"
        if ema_d == "bullish":
            return "daily_EMA_bull"
        if ema4h == "mixed" and macd > macd_p and adx < 25 and unrealized_pct < -MIXED_EMA_LOSS_GUARD:
            return "mixed_EMA_weak"
        if rsi < 32:
            return "RSI_oversold"
        if macd > macd_p and rsi < macd_div_rsi_short:
            return "MACD_div_short"
        if oi < -3 and macd > macd_p:
            return "OI_fall_short"
        if adx < 20:
            return "ADX_collapse"
    else:
        if ema4h == "bearish":
            return "4h_EMA_bear"
        if ema_d == "bearish":
            return "daily_EMA_bear"
        if ema4h == "mixed" and macd < macd_p and adx < 25 and unrealized_pct < -MIXED_EMA_LOSS_GUARD:
            return "mixed_EMA_weak"
        if rsi > 68:
            return "RSI_overbought"
        if macd < macd_p and rsi > macd_div_rsi_long:
            return "MACD_div_long"
        if oi < -3 and macd < macd_p:
            return "OI_fall_long"
        if adx < 20:
            return "ADX_collapse"
    return None


# ── Close PnL helper ──────────────────────────────────────────────────────────

def _close_pnl(side: str, entry: float, qty: float, entry_fee: float, exit_price: float) -> float:
    gross = (exit_price - entry) * qty if side == "long" else (entry - exit_price) * qty
    exit_fee = abs(exit_price * qty) * _FEE_RATE
    return gross - entry_fee - exit_fee


# ── Run one combo on one set of snapshots ─────────────────────────────────────

def _evaluate(
    snapshots: dict[str, list[dict | None]],
    params: tuple[float, ...],
) -> list[dict]:
    adx_min, min_confidence, borderline_penalty, macd_div_rsi_long, macd_div_rsi_short = params
    trades: list[dict] = []

    for coin, snaps in snapshots.items():
        pos: dict | None = None

        for snap in snaps:
            if snap is None:
                continue

            ind = snap["indicators"]
            price = snap["price"]
            high = snap["high"]
            low = snap["low"]

            # 1. Intrabar SL/TP
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
                    pnl = _close_pnl(pos["side"], pos["entry"], pos["qty"], pos["fee"], exit_p)
                    trades.append({"pnl": pnl, "exit": "SL" if hit_sl else "TP", "side": pos["side"], "conf": pos["conf"], "notional": pos["notional"]})
                    pos = None
                    continue

            # 2. Rule-based exit
            if pos is not None:
                unrealized = (price - pos["entry"]) / pos["entry"] if pos["side"] == "long" else (pos["entry"] - price) / pos["entry"]
                reason = _rule_exit(pos["side"], ind, unrealized, macd_div_rsi_long, macd_div_rsi_short)
                if reason:
                    exit_p = price * (1 - _SLIPPAGE_RATE) if pos["side"] == "long" else price * (1 + _SLIPPAGE_RATE)
                    pnl = _close_pnl(pos["side"], pos["entry"], pos["qty"], pos["fee"], exit_p)
                    trades.append({"pnl": pnl, "exit": reason, "side": pos["side"], "conf": pos["conf"], "notional": pos["notional"]})
                    pos = None
                continue

            # 3. Entry (only when flat)
            entry = _try_entry(snap, adx_min, min_confidence, borderline_penalty)
            if entry:
                pos = entry

        # Mark-to-market at end
        if pos is not None:
            valid = [s for s in snaps if s is not None]
            if valid:
                last_p = valid[-1]["price"]
                pnl = _close_pnl(pos["side"], pos["entry"], pos["qty"], pos["fee"], last_p)
                trades.append({"pnl": pnl, "exit": "EOD", "side": pos["side"], "conf": pos["conf"], "notional": pos["notional"]})

    return trades


def _run_combo(params_tuple: tuple[float, ...]) -> tuple[tuple, dict, dict]:
    """Run one parameter combo on both train and test sets."""
    train_trades = _evaluate(_TRAIN_SNAPSHOTS, params_tuple)
    test_trades = _evaluate(_TEST_SNAPSHOTS, params_tuple)
    return params_tuple, _stats(train_trades), _stats(test_trades)


# ── Statistics ────────────────────────────────────────────────────────────────

def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "net_pnl": 0.0, "pf": 0.0, "avg_pnl": 0.0, "median_pnl": 0.0, "max_dd": 0.0, "avg_conf": 0.0, "capital": 0.0}
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
    capital = sum(t["notional"] for t in trades) / len(trades) if trades else 0.0
    return {
        "n": len(trades),
        "win_rate": len(wins) / len(trades),
        "net_pnl": sum(pnls),
        "pf": gp / gl if gl > 0 else (999.0 if gp > 0 else 0.0),
        "avg_pnl": mean(pnls),
        "median_pnl": median(pnls),
        "max_dd": mdd,
        "avg_conf": mean(t["conf"] for t in trades) if trades else 0.0,
        "capital": capital,
    }


# ── Data fetching ─────────────────────────────────────────────────────────────

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


def _split_snapshots(
    snapshots: dict[str, list[dict | None]], split_ms: int
) -> tuple[dict[str, list[dict | None]], dict[str, list[dict | None]]]:
    """Split precomputed snapshots into train (< split_ms) and test (>= split_ms)."""
    train: dict[str, list[dict | None]] = {}
    test: dict[str, list[dict | None]] = {}
    for coin, snaps in snapshots.items():
        t, o = [], []
        for s in snaps:
            if s is None:
                # Put None in both to preserve indexing alignment (warmup bars)
                t.append(None)
                o.append(None)
            elif s["close_time_ms"] < split_ms:
                t.append(s)
                o.append(None)
            else:
                t.append(None)
                o.append(s)
        train[coin] = t
        test[coin] = o
    return train, test


# ── ROI calculation ───────────────────────────────────────────────────────────

def _annual_roi(net_pnl: float, capital: float, days: int) -> float:
    if capital <= 0 or days <= 0:
        return 0.0
    roi = net_pnl / capital
    return roi * 365.0 / days


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward grid search over swing strategy parameters")
    parser.add_argument("--coins", default="DOGE,1000SHIB,RUNE,RENDER,1000FLOKI,TURBO,IP,BSV,IOTA")
    parser.add_argument("--start", default="2021-01-01T00:00:00Z")
    parser.add_argument("--end", default="2026-04-15T00:00:00Z")
    parser.add_argument("--fee-bps", type=float, default=4.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--top", type=int, default=20, help="Number of top results to print")
    parser.add_argument("--min-trades", type=int, default=10, help="Min OOS trades to include")
    parser.add_argument("--sort-by", default="pf", choices=["pf", "net_pnl", "win_rate"])
    parser.add_argument(
        "--splits",
        default="2024-07-01,2025-04-01",
        help="Comma-separated split dates (train ends before, test starts at). Runs each split independently.",
    )
    args = parser.parse_args()

    fee_rate = args.fee_bps / 10_000.0
    slippage_rate = args.slippage_bps / 10_000.0
    start = _parse_dt(args.start)
    end = _parse_dt(args.end)
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    split_dates = [_parse_dt(s.strip()) for s in args.splits.split(",")]

    engine = ReplayEngine(coins, start, end, fee_bps=args.fee_bps, slippage_bps=args.slippage_bps)

    # ── Step 1: fetch klines ──────────────────────────────────────────────────
    print(f"Fetching klines for {len(coins)} coins ({start.date()} -> {end.date()})...")
    raw: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=min(len(coins), 8)) as ex:
        futures = {ex.submit(_fetch_coin, engine, coin): coin for coin in coins}
        for fut in as_completed(futures):
            coin, kl4, kl1d = fut.result()
            raw[coin] = (kl4, kl1d)
            print(f"  {coin}: {len(kl4)} 4h bars, {len(kl1d)} daily bars")

    # ── Step 2: precompute indicators ─────────────────────────────────────────
    print("Precomputing indicators...")
    full_snapshots: dict[str, list[dict | None]] = {}
    for coin in coins:
        kl4, kl1d = raw[coin]
        full_snapshots[coin] = engine._precompute_coin(kl4, kl1d)
        valid = sum(1 for s in full_snapshots[coin] if s is not None)
        print(f"  {coin}: {valid} valid bars")

    combos = list(itertools.product(*[GRID[k] for k in PARAM_KEYS]))
    total = len(combos)

    # ── Step 3: run each walk-forward split ───────────────────────────────────
    for wf_idx, split_dt in enumerate(split_dates, 1):
        split_ms = int(split_dt.timestamp() * 1000)
        train_snaps, test_snaps = _split_snapshots(full_snapshots, split_ms)

        train_bars = sum(sum(1 for s in v if s is not None) for v in train_snaps.values())
        test_bars = sum(sum(1 for s in v if s is not None) for v in test_snaps.values())
        train_days = (split_dt - start).days
        test_days = (end - split_dt).days

        print(f"\n{'='*90}")
        print(f"WF#{wf_idx}: train {start.date()} -> {split_dt.date()} ({train_days}d, {train_bars} bars)")
        print(f"        test  {split_dt.date()} -> {end.date()} ({test_days}d, {test_bars} bars)")
        print(f"        {total} combos, {args.workers} workers")
        print(f"{'='*90}")

        results: list[tuple[tuple, dict, dict]] = []
        with ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_init_worker,
            initargs=(train_snaps, test_snaps, fee_rate, slippage_rate),
        ) as executor:
            fut_map = {executor.submit(_run_combo, c): c for c in combos}
            done = 0
            for fut in as_completed(fut_map):
                params_tuple, train_stats, test_stats = fut.result()
                results.append((params_tuple, train_stats, test_stats))
                done += 1
                if done % 50 == 0 or done == total:
                    print(f"  {done}/{total} done...", flush=True)

        # Filter by min OOS trades
        results = [(p, tr, te) for p, tr, te in results if te["n"] >= args.min_trades]
        # Sort by OOS metric
        results.sort(key=lambda x: x[2][args.sort_by], reverse=True)

        print(f"\nTop {args.top} by OOS {args.sort_by} (min {args.min_trades} OOS trades):\n")
        hdr = (
            f"{'adx':>5} {'conf':>5} {'bpen':>5} {'mdL':>5} {'mdS':>5} "
            f"| {'IS_n':>4} {'IS_wr':>6} {'IS_pnl':>8} {'IS_pf':>5} "
            f"| {'OOS_n':>5} {'OOS_wr':>6} {'OOS_pnl':>8} {'OOS_pf':>6} {'OOS_dd':>7} {'OOS_roi%':>8}"
        )
        print(hdr)
        print("-" * len(hdr))

        for params_tuple, tr, te in results[:args.top]:
            p = dict(zip(PARAM_KEYS, params_tuple))
            oos_roi = _annual_roi(te["net_pnl"], te["capital"], test_days) * 100
            print(
                f"{p['adx_min']:>5.0f} {p['min_confidence']:>5.2f} {p['borderline_penalty']:>5.2f} "
                f"{p['macd_div_rsi_long']:>5.0f} {p['macd_div_rsi_short']:>5.0f} "
                f"| {tr['n']:>4} {tr['win_rate']*100:>5.1f}% {tr['net_pnl']:>8.2f} {tr['pf']:>5.2f} "
                f"| {te['n']:>5} {te['win_rate']*100:>5.1f}% {te['net_pnl']:>8.2f} {te['pf']:>6.2f} "
                f"{te['max_dd']:>7.2f} {oos_roi:>7.1f}%"
            )

        # Print overfit analysis
        if results:
            print(f"\n--- Overfit analysis (top 5) ---")
            for params_tuple, tr, te in results[:5]:
                p = dict(zip(PARAM_KEYS, params_tuple))
                is_pf = tr["pf"]
                oos_pf = te["pf"]
                overfit = ((is_pf - oos_pf) / is_pf * 100) if is_pf > 0 else 0.0
                is_roi = _annual_roi(tr["net_pnl"], tr["capital"], train_days) * 100
                oos_roi = _annual_roi(te["net_pnl"], te["capital"], test_days) * 100
                roi_decay = ((is_roi - oos_roi) / is_roi * 100) if is_roi > 0 else 0.0
                print(
                    f"  adx={p['adx_min']:.0f} conf={p['min_confidence']:.2f} bpen={p['borderline_penalty']:.2f} "
                    f"mdL={p['macd_div_rsi_long']:.0f} mdS={p['macd_div_rsi_short']:.0f}  |  "
                    f"IS PF={is_pf:.2f} -> OOS PF={oos_pf:.2f} ({overfit:+.0f}% decay)  |  "
                    f"IS ROI={is_roi:.1f}% -> OOS ROI={oos_roi:.1f}% ({roi_decay:+.0f}% decay)"
                )

        # Baseline comparison
        baseline = (28.0, 0.80, 0.08, 68.0, 32.0)
        base_match = [(p, tr, te) for p, tr, te in results if p == baseline]
        print(f"\nBaseline (adx=28, conf=0.80, bpen=0.08, mdL=68, mdS=32):")
        if base_match:
            _, tr, te = base_match[0]
            oos_roi = _annual_roi(te["net_pnl"], te["capital"], test_days) * 100
            print(
                f"  IS:  n={tr['n']} win={tr['win_rate']*100:.1f}% pnl={tr['net_pnl']:.2f} pf={tr['pf']:.2f}"
            )
            print(
                f"  OOS: n={te['n']} win={te['win_rate']*100:.1f}% pnl={te['net_pnl']:.2f} pf={te['pf']:.2f} "
                f"dd={te['max_dd']:.2f} roi={oos_roi:.1f}%"
            )
        else:
            print("  (filtered out by --min-trades)")

        if not results:
            print("No results met the minimum OOS trade threshold.")


if __name__ == "__main__":
    main()
