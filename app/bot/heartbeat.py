"""Shared heartbeat state — updated each cycle, read by watchdog and health check."""

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_last_beat: datetime | None = None


def update() -> None:
    global _last_beat
    with _lock:
        _last_beat = datetime.now(timezone.utc)


def get() -> datetime | None:
    with _lock:
        return _last_beat
