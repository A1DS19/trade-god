"""GET / — self-contained HTML status page built from queries.py dicts.

No external assets, no JS: inline CSS and a meta-refresh. The page is only
reachable through the SSH tunnel (port 8000 is closed at the firewall).
"""

from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api import queries

router = APIRouter()


def render_sparkline(points: list[float], width: int = 560, height: int = 80) -> str:
    if len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    step = width / (len(points) - 1)
    coords = " ".join(
        f"{i * step:.1f},{height - 4 - (p - lo) / span * (height - 8):.1f}"
        for i, p in enumerate(points)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="spark" role="img">'
        f'<polyline points="{coords}" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/></svg>'
    )


def _fmt(v, digits: int = 2, suffix: str = "") -> str:
    return "—" if v is None else f"{v:.{digits}f}{suffix}"


def _tick(ok: bool | None) -> str:
    return {True: "✅", False: "❌"}.get(ok, "—")


def build_page() -> str:
    state = queries.engine_state()
    gate = queries.gate_progress()
    stats = queries.trade_stats()
    fills = queries.fill_stats()
    trades = queries.list_trades(limit=10)
    curve = queries.realized_equity_curve()

    ks = state["killswitch"]
    halted_badge = '<span class="badge">HALTED</span>' if ks["halted"] else ""
    net_pnl = stats["net_pnl_usd"] if stats["trades"] else 0.0

    headline = (
        '<div class="cards">'
        f'<div class="card"><div class="k">Equity</div><div class="v">${_fmt(state["equity"])}</div></div>'
        f'<div class="card"><div class="k">Net realized</div><div class="v">${_fmt(net_pnl)}</div></div>'
        f'<div class="card"><div class="k">Today</div><div class="v">{_fmt(ks["day_pnl_pct"], suffix="%")}</div></div>'
        f'<div class="card"><div class="k">From peak</div><div class="v">{_fmt(ks["drawdown_from_peak_pct"], suffix="%")}</div></div>'
        f"{halted_badge}</div>"
    )

    w = gate["window"]
    c = gate["criteria"]
    sig, ex5, ksc, tt = (c["significance"], c["ex_top5_pnl"], c["kill_switch"],
                         c["trade_through_rate"])
    gate_html = (
        f'<h2>Go-live gate (extended) <small>day {w["days_elapsed"]} of {w["days_total"]} · ends {w["end"]}</small></h2>'
        "<ul>"
        f'<li>{_tick(sig["pass"])} t-stat {_fmt(sig["t_stat"])} ≥ {queries.T_STAT_MIN:g} '
        f'<small>(n={sig["trades"]}, mean ${_fmt(sig["mean_pnl_usd"], 3)}, sd ${_fmt(sig["sd_pnl_usd"], 3)})</small></li>'
        f'<li>{_tick(ex5["pass"])} ex-top-5 PnL ${_fmt(ex5["value_usd"])} ≥ $0 '
        f'<small>(top-5 ${_fmt(ex5["top5_usd"])})</small></li>'
        f'<li>{_tick(ksc["pass"])} kill-switch clear '
        f'(today {_fmt(ksc["day_pnl_pct"], suffix="%")} vs {_fmt(ksc["daily_halt_at_pct"], suffix="%")}, '
        f'peak {_fmt(ksc["drawdown_from_peak_pct"], suffix="%")} vs {_fmt(ksc["drawdown_halt_at_pct"], suffix="%")}; '
        f'{html.escape(ksc["note"])}) '
        "<small>realized basis — the halt evaluates marked equity</small></li>"
        f'<li>{_tick(tt["pass"])} trade-through {_fmt(tt["value_pct"], suffix="%")} ≥ {queries.TRADE_THROUGH_MIN_PCT:g}%</li>'
        "</ul>"
    )

    spark = render_sparkline(curve)
    spark_html = (
        f"<h2>Realized equity</h2>{spark}" if spark
        else "<h2>Realized equity</h2><p>no data yet — fewer than 2 closed trades</p>"
    )

    def dict_table(title: str, d: dict) -> str:
        if not d:
            return f"<h2>{title}</h2><p>none</p>"
        rows = "".join(
            f"<tr><td>{html.escape(str(sym))}</td><td>{html.escape(str(v))}</td></tr>"
            for sym, v in d.items()
        )
        return f"<h2>{title}</h2><table><tr><th>symbol</th><th>detail</th></tr>{rows}</table>"

    if trades:
        trade_rows = "".join(
            f"<tr><td>{html.escape(t['symbol'])}</td><td>{html.escape(t['entry_time'][:16])}</td>"
            f"<td>{_fmt(t['pnl_pct'], suffix='%')}</td><td>{_fmt(t['pnl_usd'], 4)}</td>"
            f"<td>{html.escape(t['status'])}</td></tr>"
            for t in trades
        )
        trades_html = ("<h2>Recent trades</h2><table>"
                       "<tr><th>symbol</th><th>entry</th><th>gross %</th><th>net USDT</th><th>status</th></tr>"
                       f"{trade_rows}</table>")
    else:
        trades_html = "<h2>Recent trades</h2><p>no data yet</p>"

    fills_html = (
        "<h2>Fill telemetry</h2><table><tr><th>outcome</th><th>count</th><th>pct</th></tr>"
        + "".join(
            f"<tr><td>{name}</td><td>{fills['by_outcome'][name]['count']}</td>"
            f"<td>{fills['by_outcome'][name]['pct']}%</td></tr>"
            for name in queries.OUTCOMES
        )
        + f"<tr><td>pending</td><td>{fills['pending']}</td><td>—</td></tr></table>"
    )

    warning = (f'<p class="warn">{html.escape(state["warning"])}</p>'
               if state.get("warning") else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>Trade-God — Intraday</title>
<style>
 body {{ font: 14px/1.5 monospace; margin: 2rem auto; max-width: 640px;
        background: #101418; color: #d8dee9; }}
 h2 {{ font-size: 1rem; border-bottom: 1px solid #2e3440; padding-bottom: .2rem; }}
 small {{ color: #7b88a1; font-weight: normal; }}
 table {{ border-collapse: collapse; width: 100%; }}
 td, th {{ text-align: left; padding: .15rem .6rem .15rem 0; }}
 th {{ color: #7b88a1; }}
 .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }}
 .card .k {{ color: #7b88a1; font-size: .8rem; }}
 .card .v {{ font-size: 1.3rem; }}
 .badge {{ background: #bf616a; color: #fff; padding: .2rem .6rem; border-radius: 4px; }}
 .spark {{ width: 100%; height: 80px; color: #88c0d0; }}
 .warn {{ color: #ebcb8b; }}
</style></head><body>
<h1>Intraday paper engine</h1>
{warning}
{headline}
{gate_html}
{spark_html}
{dict_table("Open positions", state["positions"])}
{dict_table("Pending limits", state["pending"])}
{trades_html}
{fills_html}
</body></html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def status_page():
    return build_page()
