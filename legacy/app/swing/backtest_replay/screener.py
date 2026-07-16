"""Coin fitness screener — quantifies how well a coin fits the swing strategy."""

from __future__ import annotations

import bisect
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any

from .engine import _to_ms, ReplayEngine
from .indicators import (
    _vs_ema,
    _vs_adx,
    _vs_atr_rank,
    _vs_atr,
    _vs_macd,
    _vs_rsi,
)
from .strategy import _ema_alignment


def _trend_run_lengths(adx_above: list[bool], ema_aligned: list[bool]) -> list[int]:
    """Return lengths of consecutive runs where both ADX > 32 AND EMA is aligned."""
    runs: list[int] = []
    current = 0
    for a, e in zip(adx_above, ema_aligned):
        if a and e:
            current += 1
        else:
            if current > 0:
                runs.append(current)
            current = 0
    if current > 0:
        runs.append(current)
    return runs


def _return_autocorrelation(closes: list[float], lag: int = 1) -> float:
    """Lag-1 autocorrelation of 4h returns. Higher = more trend persistence."""
    if len(closes) < lag + 10:
        return 0.0
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    n = len(returns)
    if n < lag + 2:
        return 0.0
    r1 = returns[:n - lag]
    r2 = returns[lag:]
    m1 = mean(r1)
    m2 = mean(r2)
    cov = sum((a - m1) * (b - m2) for a, b in zip(r1, r2)) / len(r1)
    std1 = (sum((x - m1) ** 2 for x in r1) / len(r1)) ** 0.5
    std2 = (sum((x - m2) ** 2 for x in r2) / len(r2)) ** 0.5
    if std1 == 0 or std2 == 0:
        return 0.0
    return cov / (std1 * std2)


def _tp_sl_hit_ratio(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    atr_s: list[float],
    entry_bars: list[int],
    entry_dirs: list[str],
    max_hold: int = 30,
) -> tuple[float, float]:
    """Simulate TP/SL outcomes at entry points. Returns (tp_hit_rate, avg_reward_risk)."""
    tp_hits = 0
    sl_hits = 0
    reward_risks: list[float] = []

    for bar_idx, direction in zip(entry_bars, entry_dirs):
        if bar_idx >= len(closes) or atr_s[bar_idx] <= 0:
            continue
        entry_price = closes[bar_idx]
        atr = atr_s[bar_idx]
        sl_dist = atr * 1.5
        tp_dist = atr * 3.0

        if direction == "long":
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

        # Walk forward up to max_hold bars
        hit = None
        max_favorable = 0.0
        for j in range(bar_idx + 1, min(bar_idx + max_hold + 1, len(closes))):
            if direction == "long":
                if lows[j] <= sl_price:
                    hit = "sl"
                    break
                if highs[j] >= tp_price:
                    hit = "tp"
                    break
                max_favorable = max(max_favorable, highs[j] - entry_price)
            else:
                if highs[j] >= sl_price:
                    hit = "sl"
                    break
                if lows[j] <= tp_price:
                    hit = "tp"
                    break
                max_favorable = max(max_favorable, entry_price - lows[j])

        if hit == "tp":
            tp_hits += 1
            reward_risks.append(tp_dist / sl_dist)
        elif hit == "sl":
            sl_hits += 1
            reward_risks.append(-1.0)
        else:
            # Didn't hit either — use max favorable excursion
            rr = max_favorable / sl_dist if sl_dist > 0 else 0.0
            reward_risks.append(rr)

    total = tp_hits + sl_hits
    tp_rate = tp_hits / total if total > 0 else 0.0
    avg_rr = mean(reward_risks) if reward_risks else 0.0
    return tp_rate, avg_rr


def screen_coin(coin: str, start: datetime, end: datetime, rate_limit_delay: float = 0.15) -> dict[str, Any]:
    """Fetch klines and compute fitness metrics for a single coin."""
    import app.swing.backtest_replay as _pkg

    client = _pkg.Client()
    symbol = f"{coin}USDT"
    start_ms = _to_ms(start)
    end_ms = _to_ms(end)

    engine = ReplayEngine([coin], start, end, rate_limit_delay=rate_limit_delay)

    try:
        kl4 = engine._fetch_klines(client, symbol, client.KLINE_INTERVAL_4HOUR, start_ms, end_ms)
        kl1d = engine._fetch_klines(
            client, symbol, client.KLINE_INTERVAL_1DAY,
            start_ms - int(timedelta(days=250).total_seconds() * 1000),
            end_ms,
        )
    except Exception as e:
        return {"coin": coin, "error": str(e)}

    if len(kl4) < 200 or len(kl1d) < 200:
        return {"coin": coin, "error": f"insufficient data ({len(kl4)} 4h, {len(kl1d)} 1d bars)"}

    # Compute indicators
    closes4 = [float(k[4]) for k in kl4]
    highs4 = [float(k[2]) for k in kl4]
    lows4 = [float(k[3]) for k in kl4]

    ema9_s = _vs_ema(closes4, 9)
    ema21_s = _vs_ema(closes4, 21)
    ema50_s = _vs_ema(closes4, 50)
    adx_s = _vs_adx(highs4, lows4, closes4)
    atr_s = _vs_atr(highs4, lows4, closes4)
    atr_rank_s = _vs_atr_rank(atr_s)
    macd_s = _vs_macd(closes4)

    closes1d = [float(k[4]) for k in kl1d]
    d_close_times = [int(k[6]) for k in kl1d]
    ema21_d_s = _vs_ema(closes1d, 21)
    ema50_d_s = _vs_ema(closes1d, 50)
    ema200_d_s = _vs_ema(closes1d, 200)

    # Return autocorrelation — measures trend persistence in price action
    autocorr = _return_autocorrelation(closes4)

    # Analyze bars after warmup
    adx_vals: list[float] = []
    atr_ranks: list[float] = []
    adx_above_32: list[bool] = []
    ema4h_aligned: list[bool] = []
    entry_bars: list[int] = []
    entry_dirs: list[str] = []

    for i in range(199, len(kl4)):
        close_time_ms = int(kl4[i][6])
        d_idx = bisect.bisect_right(d_close_times, close_time_ms) - 1
        if d_idx < 199:
            continue

        price = closes4[i]
        adx_val, plus_di, minus_di = adx_s[i]
        macd_hist, _ = macd_s[i]

        ema_align = _ema_alignment(price, ema9_s[i], ema21_s[i], ema50_s[i])
        daily_align = _ema_alignment(price, ema21_d_s[d_idx], ema50_d_s[d_idx], ema200_d_s[d_idx])

        adx_vals.append(adx_val)
        atr_ranks.append(atr_rank_s[i])
        adx_above_32.append(adx_val >= 32)
        ema4h_aligned.append(ema_align in ("bullish", "bearish"))

        # Track entry points for TP/SL simulation
        can_short = (
            daily_align == "bearish"
            and ema_align == "bearish"
            and macd_hist <= 0
            and adx_val >= 32
            and minus_di > plus_di
        )
        can_long = (
            daily_align == "bullish"
            and ema_align == "bullish"
            and macd_hist > 0
            and adx_val >= 32
            and plus_di > minus_di
        )
        if can_short:
            entry_bars.append(i)
            entry_dirs.append("short")
        elif can_long:
            entry_bars.append(i)
            entry_dirs.append("long")

    n = len(adx_vals)
    if n == 0:
        return {"coin": coin, "error": "no valid bars after warmup"}

    trend_pct = sum(adx_above_32) / n
    ema_aligned_pct = sum(ema4h_aligned) / n
    avg_atr_rank = mean(atr_ranks)
    high_vol_pct = sum(1 for r in atr_ranks if r > 70) / n
    avg_adx = mean(adx_vals)
    entry_density = len(entry_bars) / n

    runs = _trend_run_lengths(adx_above_32, ema4h_aligned)
    trend_persistence = median(runs) if runs else 0.0

    # TP/SL simulation at actual entry points
    tp_rate, avg_rr = _tp_sl_hit_ratio(
        closes4, highs4, lows4, atr_s, entry_bars, entry_dirs,
    )

    return {
        "coin": coin,
        "bars": n,
        "entries": len(entry_bars),
        "trend_pct": trend_pct,
        "ema_aligned_pct": ema_aligned_pct,
        "avg_atr_rank": avg_atr_rank,
        "high_vol_pct": high_vol_pct,
        "avg_adx": avg_adx,
        "trend_persistence": trend_persistence,
        "entry_density": entry_density,
        "autocorr": autocorr,
        "tp_rate": tp_rate,
        "avg_rr": avg_rr,
    }


def screen_all(
    coins: list[str],
    start: datetime,
    end: datetime,
    workers: int = 8,
    rate_limit_delay: float = 0.15,
) -> list[dict[str, Any]]:
    """Screen multiple coins in parallel and return sorted by composite score."""
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(coins))) as executor:
        futures = {executor.submit(screen_coin, coin, start, end, rate_limit_delay): coin for coin in coins}
        for future in as_completed(futures):
            coin = futures[future]
            try:
                result = future.result()
                print(f"Screened {coin}")
                results.append(result)
            except Exception as e:
                print(f"Error screening {coin}: {e}")
                results.append({"coin": coin, "error": str(e)})

    # Compute composite score — heavily weight outcome-based metrics
    valid = [r for r in results if "error" not in r]
    if not valid:
        return results

    max_persistence = max(r["trend_persistence"] for r in valid) or 1.0
    for r in valid:
        tp_norm = r["trend_persistence"] / max_persistence
        # Clamp autocorr to [0, 1] range (negative autocorr = mean-reverting = bad)
        ac = max(r["autocorr"], 0.0)
        r["composite_score"] = (
            r["tp_rate"] * 0.30           # most important: does TP get hit?
            + max(r["avg_rr"], 0) * 0.15  # reward/risk quality
            + ac * 0.15                   # trend persistence in returns
            + r["trend_pct"] * 0.10       # ADX above entry gate
            + r["ema_aligned_pct"] * 0.10 # clean EMA structure
            + r["high_vol_pct"] * 0.10    # volatility for ATR-based TP
            + tp_norm * 0.05              # trend duration
            + r["entry_density"] * 0.05   # enough opportunities
        )

    for r in results:
        if "error" in r:
            r["composite_score"] = 0.0

    results.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
    return results


def _print_screen_results(results: list[dict[str, Any]]) -> None:
    """Print ranked fitness table."""
    print(f"\nCoin Fitness Screening ({len(results)} coins)")
    print(
        f"{'rank':>4} | {'coin':<10} | {'score':>5} | {'tp_rate':>7} | {'avg_rr':>6} | "
        f"{'autocr':>6} | {'trend%':>6} | {'ema4h%':>6} | {'hivol%':>6} | "
        f"{'avg_adx':>7} | {'persist':>7} | {'entry%':>6} | {'#ent':>4} | {'bars':>5}"
    )
    print(f"{'─' * 125}")

    for rank, r in enumerate(results, 1):
        if "error" in r:
            print(f"{rank:>4} | {r['coin']:<10} | {'ERROR':>5} | {r['error']}")
            continue
        print(
            f"{rank:>4} | {r['coin']:<10} | {r['composite_score']:.3f} | "
            f"{r['tp_rate']*100:>6.1f}% | {r['avg_rr']:>6.2f} | "
            f"{r['autocorr']:>6.3f} | {r['trend_pct']*100:>5.1f}% | "
            f"{r['ema_aligned_pct']*100:>5.1f}% | {r['high_vol_pct']*100:>5.1f}% | "
            f"{r['avg_adx']:>7.1f} | {r['trend_persistence']:>7.1f} | "
            f"{r['entry_density']*100:>5.2f}% | {r['entries']:>4} | {r['bars']:>5}"
        )
