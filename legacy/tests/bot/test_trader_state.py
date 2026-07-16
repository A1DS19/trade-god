"""DCA bot position-state helpers in app.bot.trader.

These manage the per-coin money state (avg_buy, qty, peak_price), so a bug here
mis-sizes positions or mis-reports PnL. The buy/sell *orchestration* still lives
inline in trader.run() and isn't unit-testable without extraction (scope C).
"""

from __future__ import annotations

from app.bot import trader


def test_empty_coin_state_shape():
    assert trader.empty_coin_state() == {
        "avg_buy": 0.0, "qty": 0.0, "last_buy": None,
        "peak_price": None, "partial_taken": False,
    }


def test_ensure_coin_slots_adds_missing_only():
    state = {"DOGE": {"qty": 5.0}}
    trader.ensure_coin_slots(state, ["DOGE", "BTC"])
    assert state["DOGE"] == {"qty": 5.0}                # existing untouched
    assert state["BTC"] == trader.empty_coin_state()    # missing added


def test_active_coins_unions_watchlist_and_held():
    state = {
        "coin_list": {"coins": ["BTC", "ETH"]},
        "daily_spend": {"spent": 1.0},
        "ETH": {"qty": 0.0},      # on watch list, no position
        "DOGE": {"qty": 3.0},     # held but NOT on the watch list
    }
    assert set(trader.active_coins(state)) == {"BTC", "ETH", "DOGE"}  # never drops a held coin


def test_coin_param_returns_default_without_override(monkeypatch):
    monkeypatch.setattr(trader.config, "COIN_OVERRIDES", {})
    assert trader.coin_param("DOGE", "take_profit", 0.05) == 0.05


def test_coin_param_returns_override_when_present(monkeypatch):
    monkeypatch.setattr(trader.config, "COIN_OVERRIDES", {"DOGE": {"take_profit": 0.10}})
    assert trader.coin_param("DOGE", "take_profit", 0.05) == 0.10
    assert trader.coin_param("DOGE", "trailing_stop_pct", 0.07) == 0.07  # unset key → default


def test_clear_position_zeroes_when_fully_sold():
    data = {"qty": 10.0, "avg_buy": 100.0, "peak_price": 120.0}
    trader._clear_position(data, filled_sell_qty=10.0, coin="DOGE")
    assert data["qty"] == 0.0
    assert data["avg_buy"] == 0.0
    assert data["peak_price"] is None


def test_clear_position_keeps_remainder_on_partial_sell():
    data = {"qty": 10.0, "avg_buy": 100.0, "peak_price": 120.0}
    trader._clear_position(data, filled_sell_qty=4.0, coin="DOGE")
    assert data["qty"] == 6.0
    assert data["avg_buy"] == 100.0     # avg + peak untouched on a partial
    assert data["peak_price"] == 120.0


def test_dust_sell_error_classification():
    assert trader._is_dust_sell_error(type("E", (), {"code": -2010})()) is True
    assert trader._is_dust_sell_error(type("E", (), {"code": -1013})()) is True
    assert trader._is_dust_sell_error(type("E", (), {"code": -1121})()) is False
