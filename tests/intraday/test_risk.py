"""Kill-switch trip edges, resume, error-strike alert edge, serialization."""

from __future__ import annotations

from app.intraday.risk import ErrorTracker, KillSwitch


def test_error_tracker_alerts_once_at_three_strikes():
    t = ErrorTracker(strikes=3)
    assert not t.record("A", ok=False)
    assert not t.record("A", ok=False)
    assert t.record("A", ok=False)          # third consecutive: alert edge
    assert not t.record("A", ok=False)      # no re-alert while still failing
    t.record("A", ok=True)
    assert not t.record("A", ok=False)      # counter reset by the success


def test_daily_loss_halts_on_edge():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.99)
    assert ks.check(100.0, "2026-07-16") is None      # anchors the day
    assert ks.check(96.0, "2026-07-16") is None       # -4%
    assert ks.check(94.9, "2026-07-16") == "daily_loss"
    assert ks.halted
    assert ks.check(94.9, "2026-07-16") is None       # no re-trip while halted


def test_daily_anchor_resets_next_day():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.99)
    ks.check(100.0, "2026-07-16")
    ks.check(97.0, "2026-07-16")
    # the 17th anchors at its first mark (93.0); no trip on the anchor itself
    assert ks.check(93.0, "2026-07-17") is None
    # 88.3 < 93 * 0.95 = 88.35 -> daily-loss trip against the NEW anchor
    assert ks.check(88.3, "2026-07-17") == "daily_loss"


def test_drawdown_halts_from_peak():
    ks = KillSwitch(daily_loss_pct=0.99, max_dd_pct=0.20)
    ks.check(100.0, "2026-07-16")
    ks.check(110.0, "2026-07-16")                     # peak 110
    assert ks.check(88.1, "2026-07-16") is None       # -19.9% from peak
    assert ks.check(87.9, "2026-07-16") == "drawdown"


def test_resume_and_serialization():
    ks = KillSwitch(daily_loss_pct=0.05, max_dd_pct=0.20)
    ks.check(100.0, "2026-07-16")
    ks.check(94.0, "2026-07-16")
    assert ks.halted
    clone = KillSwitch.from_dict(ks.to_dict())
    assert clone.halted
    clone.resume()
    assert not clone.halted
    assert clone.check(93.0, "2026-07-16") is None    # resumed; re-anchor guards re-trip


def test_notify_daily_summary_escapes_html(monkeypatch):
    from app.intraday import notifier
    sent = {}
    monkeypatch.setattr(notifier, "send", lambda msg: sent.update(msg=msg))
    notifier.notify_daily_summary("a<b>&c")
    assert "a&lt;b&gt;&amp;c" in sent["msg"]
