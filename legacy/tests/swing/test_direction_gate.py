"""Per-direction entry kill-switch (2026-06-12: shorts disabled).

All six post-overhaul losses were shorts and Phase C measured short-leg
momentum at PF 0.979 on this universe. Exits are never gated — only entries.
"""

from __future__ import annotations

from app.swing import config
from app.swing.main import _direction_enabled


def test_short_entries_blocked_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(config, "ENABLE_SHORTS", False)
    assert _direction_enabled("short") is False


def test_short_entries_allowed_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(config, "ENABLE_SHORTS", True)
    assert _direction_enabled("short") is True


def test_longs_never_gated(monkeypatch) -> None:
    monkeypatch.setattr(config, "ENABLE_SHORTS", False)
    assert _direction_enabled("long") is True


def test_shorts_are_currently_disabled_in_config() -> None:
    """Pin the live config decision; flipping it back should be deliberate."""
    assert config.ENABLE_SHORTS is False
