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

    summary1 = backfill.run(client=None, targets=targets, datasets=list(backfill.DEFAULT_DATASETS), delay=0)
    # first run: every dataset starts at onboard date
    # a[-1] because interval datasets pass (interval, start_ms) so start is last positional
    starts = {(d, s): a[-1] if a else k.get("start_ms") for d, s, a, k in stub.calls}
    assert all(v == 1234 for v in starts.values())
    assert summary1.failures == []

    stub.calls.clear()
    backfill.run(client=None, targets=targets, datasets=list(backfill.DEFAULT_DATASETS), delay=0)
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


def test_backfill_clamps_intraday_start_to_floor(warehouse, monkeypatch):
    from research import config

    stub = StubSource()
    rows = {ds: (lambda s: [{"open_time": 5000, "close": 1.0}]) for ds in backfill.FETCHERS}
    rows["funding"] = lambda s: [{"funding_time": 5000, "funding_rate": 0.0}]
    rows["oi_1h"] = lambda s: [{"timestamp": 5000, "sum_open_interest": 1.0}]
    rows["long_short_1h"] = lambda s: [{"timestamp": 5000, "long_short_ratio": 1.0}]
    _wire(monkeypatch, stub, rows)
    targets = [{"symbol": "DOGEUSDT", "onboard_date_ms": 1234}]

    before = int(time.time() * 1000)
    backfill.run(client=None, targets=targets, datasets=["klines_15m", "klines_5m"], delay=0)
    after = int(time.time() * 1000)

    starts = {d: a[-1] for d, s, a, k in stub.calls}
    assert starts["klines_15m"] == config.KLINES_15M_FLOOR_MS
    assert (before - config.KLINES_5M_WINDOW_MS
            <= starts["klines_5m"]
            <= after - config.KLINES_5M_WINDOW_MS)


def test_default_datasets_exclude_intraday_klines():
    assert "klines_5m" not in backfill.DEFAULT_DATASETS
    assert "klines_15m" not in backfill.DEFAULT_DATASETS
    assert set(backfill.DEFAULT_DATASETS) < set(backfill.FETCHERS)
    assert backfill.FETCHERS["klines_15m"].needs_interval == "15m"
    assert backfill.FETCHERS["klines_5m"].needs_interval == "5m"


def test_default_datasets_derived_from_cron_default_flag():
    # DEFAULT_DATASETS is a declarative opt-in list, not a hardcoded deny-list:
    # every FETCHERS entry with cron_default=False (and only those) is excluded.
    assert backfill.FETCHERS["klines_5m"].cron_default is False
    assert backfill.FETCHERS["klines_15m"].cron_default is False
    assert backfill.FETCHERS["klines_1h"].cron_default is True
    assert set(backfill.DEFAULT_DATASETS) == {
        d for d, spec in backfill.FETCHERS.items() if spec.cron_default
    }


class FakeClient:
    """Stands in for binance.client.Client so main() never touches the network."""

    def __init__(self, *args, **kwargs):
        pass


def test_main_rejects_empty_symbols(monkeypatch):
    import binance.client

    monkeypatch.setattr(binance.client, "Client", FakeClient)
    monkeypatch.setattr("sys.argv", ["backfill", "--symbols", "", "--datasets", "klines_1h"])

    with pytest.raises(SystemExit):
        backfill.main()


def test_main_parses_symbols_stripping_empty_tokens(monkeypatch):
    import binance.client

    captured = {}

    def fake_resolve_onboard(client, symbols):
        captured["symbols"] = symbols
        return [{"symbol": s, "onboard_date_ms": 0} for s in symbols]

    def fake_run(client, targets, datasets, delay):
        captured["targets"] = targets
        return backfill.Summary()

    monkeypatch.setattr(binance.client, "Client", FakeClient)
    monkeypatch.setattr(backfill, "_resolve_onboard", fake_resolve_onboard)
    monkeypatch.setattr(backfill, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["backfill", "--symbols", "A,,B", "--datasets", "klines_1h"])

    backfill.main()

    assert captured["symbols"] == ["A", "B"]
