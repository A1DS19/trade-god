"""Binance's public archive (data.binance.vision): listing, checksummed downloads, parsing.

Every archive file is a monthly zip holding one CSV, published beside a `.CHECKSUM` in sha256sum
format (`<hex>  <file name>`). Quirks seen in real files on 2026-10-05:
- futures CSVs have a header row from about 2022 on; older ones have none;
- spot klines switch from millisecond to microsecond timestamps in 2025-01;
- funding files are `calc_time,funding_interval_hours,last_funding_rate`, with ms jitter.
Nothing here writes to the warehouse; research.archive_backfill does.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

from research.binance_source import kline_row, premium_row

# Epoch milliseconds reach 1e14 only in the year 5138; epoch microseconds passed it in 1973.
MICROS_FLOOR = 10**14


def verify_checksum(payload: bytes, checksum_text: str) -> None:
    """Raise unless the payload's sha256 is the one the archive published."""
    expected = checksum_text.split()[0]
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch: published {expected}, downloaded {actual}")


def read_csv_rows(payload: bytes) -> list[list[str]]:
    """The zip's single CSV, split into cells, without its header row if it has one."""
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one CSV in the zip, found {names}")
        text = zf.read(names[0]).decode()
    rows = [line.split(",") for line in text.splitlines() if line]
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]
    return rows


def _as_ms(t: int) -> int:
    return t // 1000 if t >= MICROS_FLOOR else t


def _ms_times(row: dict) -> dict:
    return {**row, "open_time": _as_ms(row["open_time"]), "close_time": _as_ms(row["close_time"])}


def parse_klines(rows: list[list[str]]) -> list[dict]:
    return [_ms_times(kline_row(cells)) for cells in rows]


def parse_premium(rows: list[list[str]]) -> list[dict]:
    return [_ms_times(premium_row(cells)) for cells in rows]


def parse_funding(rows: list[list[str]]) -> list[dict]:
    return [
        {"funding_time": _as_ms(int(c[0])), "funding_interval_hours": int(c[1]),
         "funding_rate": float(c[2])}
        for c in rows
    ]
