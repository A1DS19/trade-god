"""archive_source turns the public archive's monthly zips into warehouse rows: checksum first,
then parsing that copes with header rows, microsecond spot timestamps and funding jitter.

The CSV lines below are real rows from data.binance.vision (2026-10-05), trimmed."""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from research import archive_source as src

KLINE_HEADER = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,"
                "taker_buy_volume,taker_buy_quote_volume,ignore")
FUTURES_2020 = (  # no header row, as in every futures file before about 2022
    "1577836800000,7189.43,7260.43,7170.15,7197.57,56801.329,1577923199999,409678760.56957,101871,28834.200,208001969.84595,0\n"
    "1577923200000,7197.57,7209.59,6922.00,6962.04,115295.677,1578009599999,815627831.08338,224747,55404.262,391911677.42577,0\n"
)
FUTURES_2026 = KLINE_HEADER + "\n" + (
    "1788220800000,78549.60,79196.00,76368.00,77400.10,151357.832,1788307199999,11776717838.40160,3622828,72544.811,5646145648.39730,0\n"
)
SPOT_2025 = (  # microseconds, as in every spot file from 2025-01
    "1735689600000000,93576.00000000,95151.15000000,92888.00000000,94591.79000000,10373.32613000,"
    "1735775999999999,975444194.13799830,1516556,5347.73648000,502914035.64059070,0\n"
)
FUNDING = (
    "calc_time,funding_interval_hours,last_funding_rate\n"
    "1785542400001,8,0.00004123\n"
    "1785571200002,8,-0.00001500\n"
)
PREMIUM = KLINE_HEADER + "\n" + (
    "1785542400000,-0.00039615,-0.00000792,-0.00140974,-0.00046270,0,1785628799999,0,17280,0,0,0\n"
)


def _zip(text: str, *names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names or ("data.csv",):
            zf.writestr(name, text)
    return buf.getvalue()


def test_futures_klines_without_a_header_row():
    rows = src.parse_klines(src.read_csv_rows(_zip(FUTURES_2020)))
    assert [r["open_time"] for r in rows] == [1577836800000, 1577923200000]
    assert rows[0]["close"] == 7197.57 and rows[0]["trades"] == 101871
    assert rows[0]["taker_buy_quote_volume"] == 208001969.84595


def test_futures_klines_with_a_header_row():
    [row] = src.parse_klines(src.read_csv_rows(_zip(FUTURES_2026)))
    assert row["open_time"] == 1788220800000 and row["quote_volume"] == 11776717838.4016


def test_spot_microsecond_timestamps_become_milliseconds():
    [row] = src.parse_klines(src.read_csv_rows(_zip(SPOT_2025)))
    assert row["open_time"] == 1735689600000  # 2025-01-01 00:00 UTC
    assert row["close_time"] == 1735775999999


def test_funding_keeps_jitter_and_interval():
    rows = src.parse_funding(src.read_csv_rows(_zip(FUNDING)))
    assert rows[0] == {"funding_time": 1785542400001, "funding_interval_hours": 8,
                       "funding_rate": 0.00004123}
    assert rows[1]["funding_rate"] == -0.000015


def test_premium_keeps_ohlc_and_times_only():
    [row] = src.parse_premium(src.read_csv_rows(_zip(PREMIUM)))
    assert row == {"open_time": 1785542400000, "open": -0.00039615, "high": -0.00000792,
                   "low": -0.00140974, "close": -0.0004627, "close_time": 1785628799999}


def test_checksum_must_match():
    payload = _zip(FUTURES_2020)
    published = f"{hashlib.sha256(payload).hexdigest()}  BTCUSDT-1d-2020-01.zip\n"
    src.verify_checksum(payload, published)
    with pytest.raises(ValueError, match="checksum mismatch"):
        src.verify_checksum(payload + b"x", published)


def test_a_zip_must_hold_exactly_one_csv():
    with pytest.raises(ValueError, match="one CSV"):
        src.read_csv_rows(_zip(FUTURES_2020, "a.csv", "b.csv"))
