"""The 15m cycle: data -> z -> paper book -> risk -> persistence -> Telegram.
Every stage is isolated; a failure alerts and the loop continues (the
TON/IP postmortem is the design constraint here)."""

from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import models
from app.intraday import config, strategy
from app.intraday import universe as iuniverse
from app.intraday.data import fetch_funding_since, fetch_panels, latest_bars

log = logging.getLogger(__name__)

DAY_MS = 86_400_000


@dataclass
class Context:
    client: object
    book: object
    killswitch: object
    tracker: object
    universe: list
    universe_refreshed_ms: int
    last_funding_ms: int
    notify: object
    state_get: object
    state_set: object


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def refresh_universe(ctx: Context):
    now_ms = int(time.time() * 1000)
    if now_ms - ctx.universe_refreshed_ms < config.UNIVERSE_REFRESH_DAYS * DAY_MS:
        return
    try:
        new = iuniverse.resolve_top30(ctx.client)
        if new and new != ctx.universe:
            added = sorted(set(new) - set(ctx.universe))
            dropped = sorted(set(ctx.universe) - set(new))
            ctx.notify.send(f"🔄 Universe refreshed: "
                            f"+{html.escape(str(added))} "
                            f"-{html.escape(str(dropped))}")
        if new:
            ctx.universe = new
        ctx.universe_refreshed_ms = now_ms
        ctx.tracker.record("__universe__", ok=True)
    except Exception as e:
        log.error("universe refresh failed: %s", e)
        # back off ~24h — a 100-symbol resolve every 15m risks a -1003 ban
        ctx.universe_refreshed_ms = (
            now_ms - config.UNIVERSE_REFRESH_DAYS * DAY_MS + DAY_MS)
        if ctx.tracker.record("__universe__", ok=False):
            ctx.notify.notify_error_strikes("__universe__", config.ERROR_ALERT_STRIKES)


def run_cycle(ctx: Context) -> dict:
    refresh_universe(ctx)

    watch = sorted(set(ctx.universe)
                   | set(ctx.book.positions) | set(ctx.book.pending))
    try:
        panels, errors = fetch_panels(ctx.client, watch)
        for sym in watch:
            ok = sym not in errors
            if ctx.tracker.record(sym, ok) and not ok:
                ctx.notify.notify_error_strikes(sym, config.ERROR_ALERT_STRIKES)

        bars = latest_bars(panels)
        z_row: dict = {}
        if not ctx.killswitch.halted and len(panels["close"]):
            z = strategy.zscore(panels["close"], panels["volume"],
                                panels["quote_volume"])
            z_row = {s: float(z[s].iloc[-1]) for s in z.columns}
        ctx.tracker.record("__data__", ok=True)
    except Exception as e:
        # book untouched and state unchanged — safe to abort without persist
        log.error("data stage failed: %s", e)
        if ctx.tracker.record("__data__", ok=False):
            ctx.notify.notify_error_strikes("__data__", config.ERROR_ALERT_STRIKES)
        return {"aborted": "data", "halted": ctx.killswitch.halted}

    try:
        if ctx.book.positions:
            events = fetch_funding_since(ctx.client, sorted(ctx.book.positions),
                                         ctx.last_funding_ms)
            for ev in events:
                ctx.book.apply_funding(ev["symbol"], ev["funding_rate"])
                ctx.last_funding_ms = max(ctx.last_funding_ms, ev["funding_time"])
    except Exception as e:
        log.error("funding failed: %s", e)

    active_universe = set() if ctx.killswitch.halted else set(ctx.universe)
    # Deliberately unwrapped: on_bar is pure in-memory — an exception here is
    # a code bug and must NOT be followed by persist (partial-mutation state
    # would be baked in); the outer main-loop catch alerts.
    res = ctx.book.on_bar(bars, z_row, active_universe)

    trade_ids = ctx.state_get("trade_ids") or {}
    now = _now_iso()
    for r in res.resolutions:
        try:
            models.log_intraday_limit(
                symbol=r["symbol"], limit_price=r["limit_price"],
                placed_at=datetime.fromtimestamp(
                    r["placed_ms"] / 1000, tz=timezone.utc).isoformat(),
                resolved_at=now, outcome=r["outcome"], bar_low=r["bar_low"],
                admitted=r["admitted"])
        except Exception as e:
            log.error("limit log failed: %s", e)
    for e_ in res.entries:
        try:
            trade_ids[e_["symbol"]] = models.log_intraday_trade(
                symbol=e_["symbol"], mode=config.EXECUTION_MODE,
                limit_price=e_["entry_price"], entry_price=e_["entry_price"],
                slot_usd=ctx.book.slot_usd, entry_time=now,
                fill_type="trade_through")
        except Exception as ex:
            log.error("trade open log failed: %s", ex)
            ctx.notify.send(f"⚠️ trade open log failed for {e_['symbol']}")
        try:
            ctx.notify.notify_fill(e_["symbol"], e_["entry_price"], e_["z"])
        except Exception as ex:
            log.error("fill notify failed: %s", ex)
    for x in res.exits:
        try:
            tid = trade_ids.get(x["symbol"])
            if tid is not None:
                models.close_intraday_trade(
                    tid, exit_price=x["exit_price"], exit_time=now,
                    hold_bars=x["hold_bars"], pnl_pct=x["pnl_pct"],
                    pnl_usd=x["pnl_usd"], exit_reason="horizon")
            # pop only after the close succeeded — a DB failure leaves the id
            # in state for a later retry or manual reconciliation
            trade_ids.pop(x["symbol"], None)
        except Exception as ex:
            log.error("trade close log failed (id kept for retry): %s", ex)
        try:
            ctx.notify.notify_exit(x["symbol"], x["pnl_usd"], x["pnl_pct"],
                                   x["hold_bars"])
        except Exception as ex:
            log.error("exit notify failed: %s", ex)

    mark = None
    try:
        closes = {s: b.close for s, b in bars.items()}
        mark = ctx.book.mark_equity(closes)
        reason = ctx.killswitch.check(mark, _utc_date())
        if reason:
            ctx.notify.notify_halt(reason, mark)
    except Exception as e:
        log.error("equity mark / kill-switch check failed: %s", e)

    if mark is not None:
        maybe_send_summaries(ctx, mark)
    try:
        ctx.state_set("trade_ids", trade_ids)
        persist(ctx)
    except Exception as e:
        # state_set writes full snapshots — the next cycle self-heals
        log.error("state persist failed: %s", e)
        ctx.notify.send("⚠️ state persist failed — will retry next cycle")
    summary = {"symbols_ok": len(bars), "errors": len(errors),
               "placements": len(res.placements), "entries": len(res.entries),
               "exits": len(res.exits), "equity_mark": mark,
               "halted": ctx.killswitch.halted}
    log.info("cycle done: %s", summary)
    return summary


def maybe_send_summaries(ctx: Context, mark: float):
    """Daily equity summary + weekly fill-telemetry report (spec §3)."""
    try:
        today = _utc_date()
        if (ctx.state_get("last_summary_date") or {}).get("date") != today:
            ctx.notify.notify_daily_summary(
                f"equity mark: ${mark:,.2f}\n"
                f"open positions: {len(ctx.book.positions)}\n"
                f"pending limits: {len(ctx.book.pending)}\n"
                f"halted: {ctx.killswitch.halted}")
            ctx.state_set("last_summary_date", {"date": today})

        now_ms = int(time.time() * 1000)
        last_weekly = (ctx.state_get("last_weekly_ms") or {}).get("ms", 0)
        if now_ms - last_weekly > 7 * DAY_MS:
            from sqlalchemy import func
            from sqlalchemy.orm import Session
            with Session(models.engine) as s:
                counts = dict(
                    s.query(models.IntradayLimit.outcome, func.count())
                    .group_by(models.IntradayLimit.outcome).all())
            total = sum(counts.values()) or 1
            lines = [f"{k}: {v} ({v / total:.0%})"
                     for k, v in sorted(counts.items())]
            ctx.notify.send("📈 <b>Weekly fill telemetry</b>\n"
                            + ("\n".join(lines) if counts else "no limits yet"))
            ctx.state_set("last_weekly_ms", {"ms": now_ms})
    except Exception as e:
        log.error("summary failed: %s", e)


def persist(ctx: Context):
    ctx.state_set("paper_book", ctx.book.to_dict())
    ctx.state_set("killswitch", ctx.killswitch.to_dict())
    ctx.state_set("universe", {"symbols": ctx.universe,
                               "refreshed_ms": ctx.universe_refreshed_ms})
    ctx.state_set("last_funding_ms", {"ms": ctx.last_funding_ms})
