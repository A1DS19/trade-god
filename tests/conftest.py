"""Shared fixtures for the trade-god test suite.

`app.config` reads credential env vars at import time, so we stub them here at
import (conftest loads before any test module is collected).
"""

from __future__ import annotations

import os

import pytest

# Must run at import time: app modules read these when imported, which happens
# as soon as test modules are collected (conftest is imported first).
_STUB_ENV = {
    "BINANCE_API_KEY": "test",
    "BINANCE_SECRET_KEY": "test",
    "BINANCE_API_KEY_FUTURES": "test",
    "BINANCE_SECRET_KEY_FUTURES": "test",
    "TELEGRAM_BOT_TOKEN": "test",
    "TELEGRAM_CHAT_ID": "test",
    # Valid-looking URL so create_engine() doesn't choke at import; no DB is hit.
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
}
for _key, _value in _STUB_ENV.items():
    os.environ.setdefault(_key, _value)


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.testnet tests unless RUN_TESTNET=1 (they hit the network)."""
    if os.environ.get("RUN_TESTNET") == "1":
        return
    skip = pytest.mark.skip(reason="testnet test — set RUN_TESTNET=1 (+ testnet creds) to run")
    for item in items:
        if "testnet" in item.keywords:
            item.add_marker(skip)
