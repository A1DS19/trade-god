from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.swing.backtest_replay as replay


class DummyClient:
    KLINE_INTERVAL_4HOUR = "4h"
    KLINE_INTERVAL_1DAY = "1d"

    def __init__(self, *args, **kwargs) -> None:
        pass


def _build_klines(
    *,
    pattern: tuple[float, ...],
    bars: int,
    start_ms: int,
    step_ms: int,
    base_price: float = 100.0,
) -> list[list[str | int]]:
    out: list[list[str | int]] = []
    price = base_price
    period = len(pattern)
    for i in range(bars):
        delta = pattern[i % period]
        price += delta

        open_price = price - (delta * 0.2)
        close_price = price
        wick = max(0.08, abs(delta) * 2.5)
        high = max(open_price, close_price) + wick
        low = min(open_price, close_price) - wick
        volume = 1000 + (i % 10) * 20

        open_time = start_ms + i * step_ms
        close_time = open_time + step_ms - 1
        out.append(
            [
                open_time,
                f"{open_price:.6f}",
                f"{high:.6f}",
                f"{low:.6f}",
                f"{close_price:.6f}",
                f"{volume:.2f}",
                close_time,
                "0",
                "0",
                "0",
                "0",
                "0",
            ]
        )
    return out


def _run_offline_replay(
    monkeypatch: pytest.MonkeyPatch,
    pattern: tuple[float, ...],
) -> tuple[dict[str, float], dict[str, float]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 3, 1, tzinfo=timezone.utc)

    kl4 = _build_klines(
        pattern=pattern,
        bars=700,
        start_ms=int(start.timestamp() * 1000),
        step_ms=4 * 60 * 60 * 1000,
    )
    kl1d = _build_klines(
        pattern=pattern,
        bars=600,
        start_ms=int((start - timedelta(days=300)).timestamp() * 1000),
        step_ms=24 * 60 * 60 * 1000,
    )

    monkeypatch.setattr(replay, "Client", DummyClient)

    def _fake_fetch_klines(self, client, symbol, interval, start_ms, end_ms):
        if interval == DummyClient.KLINE_INTERVAL_4HOUR:
            return kl4
        return kl1d

    monkeypatch.setattr(replay.ReplayEngine, "_fetch_klines", _fake_fetch_klines)

    engine = replay.ReplayEngine(
        ["DOGE"],
        start,
        end,
        fee_bps=4.0,
        slippage_bps=2.0,
    )
    v1, v2, _bars = engine._run_coin("DOGE")
    return replay._summarize(v1), replay._summarize(v2)


@pytest.mark.parametrize(
    ("pattern", "min_trades"),
    [
        ((-0.2, -0.2, -0.2, 0.15, 0.2, 0.15), 3),  # downtrend with relief rallies
        ((-0.2, -0.15, 0.2, 0.2, -0.1, 0.2), 4),  # uptrend with pullbacks
    ],
)
def test_v2_replay_profitability_guardrail(
    monkeypatch: pytest.MonkeyPatch,
    pattern: tuple[float, ...],
    min_trades: int,
) -> None:
    v1, v2 = _run_offline_replay(monkeypatch, pattern)

    assert v2["trades"] >= min_trades
    assert v2["net_pnl"] > 0
    assert v2["profit_factor"] > 1.0
    assert v2["total_fees"] > 0

    # Regression guard: tuned v2 should not underperform v1 on canonical fixtures.
    assert v2["net_pnl"] >= v1["net_pnl"]


def test_v2_expected_move_filter_rejects_low_edge_setup() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)
    engine = replay.ReplayEngine(["DOGE"], start, end, fee_bps=4.0, slippage_bps=2.0)

    # Roundtrip costs = 0.12%; required TP is >= 3x roundtrip and net TP >= 0.4%.
    # 0.30% TP should be rejected.
    assert engine._v2_expected_move_ok(0.0030) is False
    assert engine._v2_expected_move_ok(0.0060) is True
