"""Entrypoint wiring: restore state, honor INTRADAY_RESUME, loop aligned to
15m closes."""

from __future__ import annotations

import logging
import time

from binance.client import Client

from app.db import models
from app.intraday import config, notifier
from app.intraday import universe as iuniverse
from app.intraday.engine import Context, persist, run_cycle
from app.intraday.paper import PaperBook
from app.intraday.risk import ErrorTracker, KillSwitch

log = logging.getLogger(__name__)


def build_context() -> Context:
    if config.EXECUTION_MODE != "paper":
        raise NotImplementedError("live mode is not implemented in Phase 3")
    client = Client("", "")   # unsigned market data only — keyless by design

    saved_book = models.intraday_state_get("paper_book")
    book = (PaperBook.from_dict(saved_book) if saved_book
            else PaperBook(equity=config.PAPER_EQUITY, max_k=config.MAX_K,
                           horizon_bars=config.HORIZON_BARS))
    saved_ks = models.intraday_state_get("killswitch")
    ks = (KillSwitch.from_dict(saved_ks) if saved_ks
          else KillSwitch(daily_loss_pct=config.DAILY_LOSS_HALT,
                          max_dd_pct=config.MAX_DD_HALT))
    if config.RESUME and ks.halted:
        ks.resume()
        notifier.send("▶️ Kill-switch cleared via INTRADAY_RESUME — trading resumed")

    saved_uni = models.intraday_state_get("universe")
    if saved_uni:
        universe, refreshed = saved_uni["symbols"], saved_uni["refreshed_ms"]
    else:
        universe, refreshed = iuniverse.resolve_top30(client), int(time.time() * 1000)
    saved_f = models.intraday_state_get("last_funding_ms")

    return Context(
        client=client, book=book, killswitch=ks,
        tracker=ErrorTracker(strikes=config.ERROR_ALERT_STRIKES),
        universe=universe, universe_refreshed_ms=refreshed,
        last_funding_ms=(saved_f or {}).get("ms", int(time.time() * 1000)),
        notify=notifier,
        state_get=models.intraday_state_get, state_set=models.intraday_state_set,
    )


def main():
    ctx = build_context()
    notifier.send(f"🚀 Intraday engine up — mode={config.EXECUTION_MODE}, "
                  f"universe={len(ctx.universe)}, "
                  f"equity=${ctx.book.equity:,.2f}"
                  f"{' [HALTED]' if ctx.killswitch.halted else ''}")
    persist(ctx)
    while True:
        try:
            run_cycle(ctx)
        except Exception as e:
            log.exception("cycle crashed: %s", e)
            notifier.send(f"💥 Intraday cycle crashed: {type(e).__name__}")
        now = time.time()
        next_close = (int(now) // config.CHECK_INTERVAL + 1) * config.CHECK_INTERVAL
        time.sleep(max(next_close + 20 - now, 5))
