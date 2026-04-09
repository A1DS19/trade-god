"""Simulation engine: Position, Trade, StrategyState, ReplayEngine."""

from __future__ import annotations

import bisect
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from binance.client import Client

from .indicators import (
    _vs_ema,
    _vs_rsi,
    _vs_macd,
    _vs_atr,
    _vs_atr_rank,
    _vs_adx,
    _vs_stoch_rsi,
    _vs_vwap,
    _vs_vol_ratio,
)
from .strategy import (
    LEVERAGE,
    V1_MIN_CONFIDENCE,
    V2_MIN_CONFIDENCE,
    V2_MIN_TP_TO_COST_MULT,
    V2_MIN_NET_TP_PCT,
    _ema_alignment,
    _position_size_usdt_v2,
    decide_v1,
    decide_v2,
)

# Re-export so __init__.py can pull it from here
__all__ = [
    "Client",
    "Position",
    "Trade",
    "StrategyState",
    "ReplayEngine",
    "_summarize",
    "_max_drawdown",
    "_fmt_pct",
    "_parse_iso_utc",
    "_to_ms",
]


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _parse_iso_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Position:
    side: str
    entry_price: float
    qty: float
    notional: float
    sl_pct: float
    tp_pct: float
    entry_time: int
    entry_fee: float = 0.0
    entry_rsi: float = 0.0
    entry_adx: float = 0.0
    entry_conf: float = 0.0
    entry_regime: str = ""


@dataclass
class Trade:
    coin: str
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    gross_pnl: float
    total_fees: float
    exit_reason: str
    confidence: float
    entry_rsi: float = 0.0
    entry_adx: float = 0.0
    entry_regime: str = ""


@dataclass
class StrategyState:
    name: str
    fee_rate: float
    slippage_rate: float
    position: Position | None = None
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=lambda: [0.0])
    entries_conf: list[float] = field(default_factory=list)

    def _apply_exit_slippage(self, side: str, price: float) -> float:
        if self.slippage_rate <= 0:
            return price
        if side == "long":
            return price * (1 - self.slippage_rate)
        return price * (1 + self.slippage_rate)

    def close(self, coin: str, now_ms: int, price: float, reason: str, confidence: float = 0.0) -> None:
        if not self.position:
            return
        p = self.position
        exit_price = self._apply_exit_slippage(p.side, price)
        gross_pnl = (
            (exit_price - p.entry_price) * p.qty
            if p.side == "long"
            else (p.entry_price - exit_price) * p.qty
        )
        exit_notional = abs(exit_price * p.qty)
        exit_fee = exit_notional * self.fee_rate
        total_fees = p.entry_fee + exit_fee
        pnl = gross_pnl - total_fees
        pnl_pct = pnl / p.notional if p.notional else 0.0
        self.trades.append(
            Trade(
                coin=coin,
                side=p.side,
                entry_time=p.entry_time,
                exit_time=now_ms,
                entry_price=p.entry_price,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                entry_rsi=p.entry_rsi,
                entry_adx=p.entry_adx,
                entry_regime=p.entry_regime,
                gross_pnl=gross_pnl,
                total_fees=total_fees,
                exit_reason=reason,
                confidence=p.entry_conf,
            )
        )
        self.equity_curve.append(self.equity_curve[-1] + pnl)
        self.position = None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _max_drawdown(equity_curve: list[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for x in equity_curve:
        peak = max(peak, x)
        dd = peak - x
        mdd = max(mdd, dd)
    return mdd


def _summarize(state: StrategyState) -> dict[str, float]:
    trades = state.trades
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "avg_conf": 0.0,
            "gross_pnl": 0.0,
            "total_fees": 0.0,
        }

    pnls = [t.pnl for t in trades]
    gross_pnls = [t.gross_pnl for t in trades]
    total_fees = sum(t.total_fees for t in trades)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": float(len(trades)),
        "win_rate": len(wins) / len(trades),
        "net_pnl": sum(pnls),
        "avg_pnl": mean(pnls),
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "max_drawdown": _max_drawdown(state.equity_curve),
        "avg_conf": mean(state.entries_conf) if state.entries_conf else 0.0,
        "gross_pnl": sum(gross_pnls),
        "total_fees": total_fees,
    }


# ---------------------------------------------------------------------------
# Replay engine
# ---------------------------------------------------------------------------

class ReplayEngine:
    def __init__(
        self,
        coins: list[str],
        start: datetime,
        end: datetime,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ):
        self.coins = coins
        self.start = start
        self.end = end
        self.fee_rate = max(fee_bps, 0.0) / 10_000.0
        self.slippage_rate = max(slippage_bps, 0.0) / 10_000.0

    def _v2_expected_move_ok(self, tp_pct: float) -> bool:
        roundtrip_cost_pct = 2.0 * (self.fee_rate + self.slippage_rate)
        required_tp_pct = roundtrip_cost_pct * V2_MIN_TP_TO_COST_MULT
        net_tp_pct = tp_pct - roundtrip_cost_pct
        return tp_pct >= required_tp_pct and net_tp_pct >= V2_MIN_NET_TP_PCT

    @staticmethod
    def _interval_ms(interval: str) -> int:
        if interval == Client.KLINE_INTERVAL_4HOUR:
            return 4 * 60 * 60 * 1000
        if interval == Client.KLINE_INTERVAL_1DAY:
            return 24 * 60 * 60 * 1000
        raise ValueError(f"Unsupported interval: {interval}")

    def _fetch_klines(self, client: Client, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list[Any]]:
        out: list[list[Any]] = []
        cursor = start_ms
        step = self._interval_ms(interval)
        prev_last_open = -1
        while True:
            batch = client.futures_klines(
                symbol=symbol,
                interval=interval,
                startTime=cursor,
                endTime=end_ms,
                limit=1500,
            )
            if not batch:
                break
            out.extend(batch)
            last_open = int(batch[-1][0])
            if last_open <= prev_last_open:
                break
            prev_last_open = last_open
            next_cursor = last_open + step
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(batch) < 1500:
                break
        return out

    def _precompute_coin(self, kl4: list[list[Any]], kl1d: list[list[Any]]) -> list[dict[str, Any] | None]:
        """Precompute all indicator series once (O(n)) and return per-bar snapshots."""
        closes4 = [float(k[4]) for k in kl4]
        highs4 = [float(k[2]) for k in kl4]
        lows4 = [float(k[3]) for k in kl4]
        volumes4 = [float(k[5]) for k in kl4]

        ema9_s = _vs_ema(closes4, 9)
        ema21_s = _vs_ema(closes4, 21)
        ema50_s = _vs_ema(closes4, 50)
        rsi_s = _vs_rsi(closes4, 14)
        macd_s = _vs_macd(closes4)
        atr_s = _vs_atr(highs4, lows4, closes4)
        atr_rank_s = _vs_atr_rank(atr_s)
        adx_s = _vs_adx(highs4, lows4, closes4)
        stoch_s = _vs_stoch_rsi(closes4)
        vwap_s = _vs_vwap(kl4)
        vol_ratio_s = _vs_vol_ratio(volumes4)

        closes1d = [float(k[4]) for k in kl1d]
        d_close_times = [int(k[6]) for k in kl1d]
        ema21_d_s = _vs_ema(closes1d, 21)
        ema50_d_s = _vs_ema(closes1d, 50)
        ema200_d_s = _vs_ema(closes1d, 200)

        results: list[dict[str, Any] | None] = []
        for i in range(len(kl4)):
            if i < 199:
                results.append(None)
                continue
            close_time_ms = int(kl4[i][6])
            d_idx = bisect.bisect_right(d_close_times, close_time_ms) - 1
            if d_idx < 199:
                results.append(None)
                continue

            price = closes4[i]
            adx_val, plus_di, minus_di = adx_s[i]
            macd_hist, macd_hist_prev = macd_s[i]
            stoch_k, stoch_d = stoch_s[i]
            atr = atr_s[i]
            ema200_d = ema200_d_s[d_idx]

            ema_alignment = _ema_alignment(price, ema9_s[i], ema21_s[i], ema50_s[i])
            daily_alignment = _ema_alignment(price, ema21_d_s[d_idx], ema50_d_s[d_idx], ema200_d)
            regime = "trending" if adx_val > 25 else ("borderline" if adx_val >= 20 else "ranging")

            atr_frac = atr / price if price > 0 else 0.0
            results.append({
                "close_time_ms": close_time_ms,
                "price": price,
                "high": highs4[i],
                "low": lows4[i],
                "market_regime": regime,
                "funding_rate_pct": 0.0,
                "suggested_sl_pct": round(max(atr_frac * 1.5, 0.01), 4),
                "suggested_tp_pct": round(max(atr_frac * 3.0, 0.02), 4),
                "open_position": None,
                "indicators": {
                    "ema_alignment": ema_alignment,
                    "daily_ema_alignment": daily_alignment,
                    "ema9": ema9_s[i],
                    "ema21": ema21_s[i],
                    "ema50": ema50_s[i],
                    "ema200_daily": ema200_d,
                    "rsi14_4h": rsi_s[i],
                    "vol_ratio": round(vol_ratio_s[i], 2),
                    "price_vs_ema200": (price - ema200_d) / ema200_d * 100 if ema200_d else 0.0,
                    "adx14": adx_val,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                    "macd_hist": macd_hist,
                    "macd_hist_prev": macd_hist_prev,
                    "oi_change_4h_pct": 0.0,
                    "stoch_rsi_k": stoch_k,
                    "stoch_rsi_d": stoch_d,
                    "atr_pct_rank": atr_rank_s[i],
                    "vwap": vwap_s[i],
                    "price_vs_vwap": (price - vwap_s[i]) / vwap_s[i] * 100 if vwap_s[i] else 0.0,
                    "ls_ratio": 1.0,
                    "taker_ratio": 1.0,
                },
            })
        return results

    def _handle_intrabar_sl_tp(
        self, state: StrategyState, coin: str, now_ms: int, high: float, low: float
    ) -> bool:
        pos = state.position
        if not pos:
            return False

        if pos.side == "long":
            sl_price = pos.entry_price * (1 - pos.sl_pct)
            tp_price = pos.entry_price * (1 + pos.tp_pct)
            hit_sl = low <= sl_price
            hit_tp = high >= tp_price
        else:
            sl_price = pos.entry_price * (1 + pos.sl_pct)
            tp_price = pos.entry_price * (1 - pos.tp_pct)
            hit_sl = high >= sl_price
            hit_tp = low <= tp_price

        if not hit_sl and not hit_tp:
            return False

        # Conservative tie-break: if both hit in same bar, assume stop first.
        if hit_sl:
            state.close(coin, now_ms, sl_price, "SL", 0.0)
        else:
            state.close(coin, now_ms, tp_price, "TP", 0.0)
        return True

    def _run_coin(self, coin: str) -> tuple[StrategyState, StrategyState, int]:
        # Look up Client through package namespace so tests can monkeypatch it
        import app.swing.backtest_replay as _pkg
        client = _pkg.Client()
        symbol = f"{coin}USDT"
        start_ms = _to_ms(self.start)
        end_ms = _to_ms(self.end)

        kl4 = self._fetch_klines(client, symbol, Client.KLINE_INTERVAL_4HOUR, start_ms, end_ms)
        kl1d = self._fetch_klines(
            client, symbol, Client.KLINE_INTERVAL_1DAY,
            start_ms - int(timedelta(days=250).total_seconds() * 1000),
            end_ms,
        )

        precomputed = self._precompute_coin(kl4, kl1d)

        s_v1 = StrategyState(name="v1", fee_rate=self.fee_rate, slippage_rate=self.slippage_rate)
        s_v2 = StrategyState(name="v2", fee_rate=self.fee_rate, slippage_rate=self.slippage_rate)
        bars = 0

        for snap in precomputed:
            if snap is None:
                continue
            bars += 1
            now_ms = snap["close_time_ms"]
            close_price = snap["price"]
            high = snap["high"]
            low = snap["low"]

            for state, decide_fn in ((s_v1, decide_v1), (s_v2, decide_v2)):
                if self._handle_intrabar_sl_tp(state, coin, now_ms, high, low):
                    continue

                local_snap = dict(snap)
                local_snap["open_position"] = None
                if state.position:
                    local_snap["open_position"] = {
                        "side": state.position.side,
                        "qty": state.position.qty,
                        "entry": state.position.entry_price,
                        "notional": state.position.notional,
                    }

                decision = decide_fn(local_snap)
                action = decision["action"]

                if action == "close" and state.position:
                    state.close(coin, now_ms, close_price, decision.get("reasoning", "rule-close"), 0.0)
                    continue

                if action in ("long", "short") and state.position is None:
                    conf = float(decision.get("confidence", 0.0))
                    min_conf = V1_MIN_CONFIDENCE if state.name == "v1" else V2_MIN_CONFIDENCE
                    if conf < min_conf:
                        continue
                    if state.name == "v2":
                        tp_pct = float(decision.get("tp_pct", 0.0) or 0.0)
                        if not self._v2_expected_move_ok(tp_pct):
                            continue
                    usdt = 5.0 if state.name == "v1" else _position_size_usdt_v2(conf)
                    notional = usdt * LEVERAGE
                    if state.slippage_rate > 0:
                        entry_price = (
                            close_price * (1 + state.slippage_rate)
                            if action == "long"
                            else close_price * (1 - state.slippage_rate)
                        )
                    else:
                        entry_price = close_price
                    qty = notional / entry_price if entry_price > 0 else 0.0
                    if qty <= 0:
                        continue
                    entry_fee = abs(entry_price * qty) * state.fee_rate
                    state.entries_conf.append(conf)
                    ind = local_snap["indicators"]
                    state.position = Position(
                        side=action,
                        entry_price=entry_price,
                        qty=qty,
                        notional=notional,
                        sl_pct=float(decision.get("sl_pct", 0.03) or 0.03),
                        tp_pct=float(decision.get("tp_pct", 0.08) or 0.08),
                        entry_time=now_ms,
                        entry_fee=entry_fee,
                        entry_rsi=ind["rsi14_4h"],
                        entry_adx=ind["adx14"],
                        entry_conf=conf,
                        entry_regime=local_snap["market_regime"],
                    )

        # Mark-to-market close at final bar close
        if bars > 0:
            last_close = float(kl4[-1][4])
            last_time = int(kl4[-1][6])
            if s_v1.position:
                s_v1.close(coin, last_time, last_close, "EOD", 0.0)
            if s_v2.position:
                s_v2.close(coin, last_time, last_close, "EOD", 0.0)

        return s_v1, s_v2, bars

    def run_all(
        self, workers: int = 8
    ) -> dict[str, tuple[StrategyState, StrategyState, int]]:
        coin_results: dict[str, tuple[StrategyState, StrategyState, int]] = {}
        with ThreadPoolExecutor(max_workers=min(workers, len(self.coins))) as executor:
            futures = {executor.submit(self._run_coin, coin): coin for coin in self.coins}
            for future in as_completed(futures):
                coin = futures[future]
                v1, v2, bars = future.result()
                print(f"Processed {coin}: {bars} bars, v1 trades={len(v1.trades)}, v2 trades={len(v2.trades)}")
                coin_results[coin] = (v1, v2, bars)
        return coin_results
