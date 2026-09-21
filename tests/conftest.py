"""Shared fixtures for the trade-god test suite."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.testnet tests unless RUN_TESTNET=1 (they hit the network)."""
    if os.environ.get("RUN_TESTNET") == "1":
        return
    skip = pytest.mark.skip(reason="testnet test — set RUN_TESTNET=1 (+ testnet creds) to run")
    for item in items:
        if "testnet" in item.keywords:
            item.add_marker(skip)
