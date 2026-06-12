"""Backfill orchestration: per symbol x dataset, fetch from high-water mark
(or onboard date), upsert, isolate per-task errors, report a summary."""

from __future__ import annotations

import time

import pytest

from research import backfill, store


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(store.config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class StubSource:
    """Replaces binance_source fetchers; records (symbol, start_ms) requests."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_on: set = set()

    def make(self, dataset, rows_fn):
        def _fetch(client, symbol, *args, **kwargs):
            key = (dataset, symbol)
            self.calls.append((dataset, symbol, args, kwargs))
            if key in self.fail_on:
                raise RuntimeError("boom")
            return rows_fn(symbol)
        return _fetch


def _wire(monkeypatch, stub, rows_by_dataset):
    monkeypatch.setattr(backfill, "FETCHERS", {
        ds: backfill._FetchSpec(stub.make(ds, rows_by_dataset[ds]), backfill.FETCHERS[ds].needs_interval)
        for ds in backfill.FETCHERS
    })


def test_backfill_starts_from_onboard_then_resumes(warehouse, monkeypatch):
    stub = StubSource()
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    summary1 = backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
    # first run: every dataset starts at onboard date
    # a[-1] because interval datasets pass (interval, start_ms) so start is last positional
    starts = {(d, s): a[-1] if a else k.get("start_ms") for d, s, a, k in stub.calls}
    assert all(v == 1234 for v in starts.values())
    assert summary1.failures == []

    stub.calls.clear()
    backfill.run(client=None, targets=targets, datasets=list(backfill.FETCHERS), delay=0)
    # second run: resumes from hwm+1
    starts2 = {(d, s): a[-1] if a else k.get("start_ms") for d, s, a, k in stub.calls}
    assert all(v == 5001 for v in starts2.values())


class FakeExchangeInfoClient:
    """Minimal stub for futures_exchange_info."""

    def __init__(self, symbols_info: list[dict]):
        self._info = symbols_info

    def futures_exchange_info(self):
        return {"symbols": self._info}


def test_resolve_onboard_uses_exchange_info():
    client = FakeExchangeInfoClient([
        {"symbol": "DOGEUSDT", "onboardDate": 1580000000000},
        {"symbol": "BSVUSDT"},  # no onboardDate key
        {"symbol": "BTCUSDT", "onboardDate": 0},
    ])

    targets = backfill._resolve_onboard(client, ["DOGEUSDT", "BSVUSDT", "BTCUSDT"])

    symbols = {t["symbol"]: t["onboard_date_ms"] for t in targets}
    assert symbols["DOGEUSDT"] == 1580000000000   # real date carried through
    assert symbols["BSVUSDT"] == 0                # missing key → 0
    assert symbols["BTCUSDT"] == 0                # onboardDate=0 → 0


def test_backfill_isolates_failures(warehouse, monkeypatch):
    stub = StubSource()
    stub.fail_on.add(("klines_1h", "DOGEUSDT"))
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    summary = backfill.run(client=None, targets=targets, datasets=["klines_1h", "klines_4h"], delay=0)

    assert summary.failures == [("klines_1h", "DOGEUSDT")]
    assert store.load("klines_4h", "DOGEUSDT").shape[0] == 1  # other dataset still landed
