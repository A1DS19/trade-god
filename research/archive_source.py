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
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

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


ARCHIVE_URL = "https://data.binance.vision/"
LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
UM_KLINES_ROOT = "data/futures/um/monthly/klines/"
MONTH_RE = re.compile(r"-(\d{4}-\d{2})\.zip$")
SPOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True)
class Source:
    folder: str  # S3 prefix holding one symbol's monthly files; {symbol} is filled in
    parse: Callable[[list[list[str]]], list[dict]]


SOURCES: dict[str, Source] = {
    "archive_spot_klines_1d": Source("data/spot/monthly/klines/{symbol}/1d/", parse_klines),
    "archive_spot_klines_1h": Source("data/spot/monthly/klines/{symbol}/1h/", parse_klines),
    "archive_um_klines_1d": Source("data/futures/um/monthly/klines/{symbol}/1d/", parse_klines),
    "archive_um_funding": Source("data/futures/um/monthly/fundingRate/{symbol}/", parse_funding),
    "archive_um_premium_1d": Source(
        "data/futures/um/monthly/premiumIndexKlines/{symbol}/1d/", parse_premium),
}


def http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _paced(get, url: str, delay: float) -> bytes:
    """The spec's pacing: wait at least `delay` seconds before every request."""
    if delay > 0:
        time.sleep(delay)
    return get(url)


def list_keys(prefix: str, *, get, delay: float, delimiter: str | None = None) -> list[str]:
    """Every key under `prefix` (or, given a delimiter, every sub-folder), across S3's pages."""
    found: list[str] = []
    marker = ""
    while True:
        query = {"prefix": prefix, "marker": marker}
        if delimiter:
            query["delimiter"] = delimiter
        root = ET.fromstring(_paced(get, f"{LISTING_URL}?{urllib.parse.urlencode(query)}", delay))
        path = "s3:CommonPrefixes/s3:Prefix" if delimiter else "s3:Contents/s3:Key"
        page = [el.text for el in root.iterfind(path, S3_NS)]
        found += page
        if root.findtext("s3:IsTruncated", namespaces=S3_NS) != "true":
            return found
        # S3 names the next marker only for delimited listings; otherwise it is the last key.
        marker = root.findtext("s3:NextMarker", namespaces=S3_NS) or page[-1]


def settled_base(name: str) -> str | None:
    """The ticker a settled folder belongs to (TLMUSDTSETTLED, AERGOUSDTSETTLEDSETTLED and
    ICPUSDT_SETTLED → TLMUSDT, AERGOUSDT and ICPUSDT), or None for an ordinary folder."""
    if "SETTLED" not in name:
        return None
    return name.split("SETTLED")[0].rstrip("_")


def list_um_symbols(*, get, delay: float) -> tuple[list[str], list[str]]:
    """(USDT perps, their settled folders) from the archive's UM klines listing (spec §1.1).

    A perp is a USDT-quoted name without `_`, which marks dated delivery contracts."""
    names = [p[len(UM_KLINES_ROOT):].rstrip("/")
             for p in list_keys(UM_KLINES_ROOT, get=get, delay=delay, delimiter="/")]
    perps = sorted(n for n in names if n.endswith("USDT") and "_" not in n)
    known = set(perps)
    settled = sorted(n for n in names if settled_base(n) in known)
    return perps, settled


def list_month_keys(dataset: str, symbol: str, *, get, delay: float) -> dict[str, str]:
    """month ('YYYY-MM') → zip key, for every monthly zip published for this dataset and symbol."""
    months = {}
    for key in list_keys(SOURCES[dataset].folder.format(symbol=symbol), get=get, delay=delay):
        match = MONTH_RE.search(key)
        if match:
            months[match.group(1)] = key
    return dict(sorted(months.items()))


def fetch_month(dataset: str, key: str, *, get, delay: float) -> list[dict]:
    """Download one monthly zip and its checksum, verify, parse. Nothing unverified is returned.

    Keys are percent-encoded: five tickers are Chinese characters (币安人生USDT …)."""
    checksum = _paced(get, ARCHIVE_URL + urllib.parse.quote(key + ".CHECKSUM"), delay).decode()
    payload = _paced(get, ARCHIVE_URL + urllib.parse.quote(key), delay)
    verify_checksum(payload, checksum)
    return SOURCES[dataset].parse(read_csv_rows(payload))
