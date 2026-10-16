"""Research tests need the dev-only deps; skip the whole directory without them.

Shared fixtures: `warehouse` points the store at a temp dir; `archive` stands in for
data.binance.vision and its S3 listing, so no test touches the network; `spot_market` makes
synthetic BTC and ETH spot klines for the model lab's timing arms.
"""

import hashlib
import io
import urllib.error
import urllib.parse
import zipfile

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

import numpy as np  # noqa: E402  (the skips above guard these imports)
import pandas as pd  # noqa: E402

from research import archive_source, config  # noqa: E402


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WAREHOUSE_DIR", tmp_path)
    return tmp_path


class FakeArchive:
    """data.binance.vision in memory: published files plus S3-style paged listings.

    Call it like archive_source.http_get. Every requested URL is kept in `urls`."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.urls: list[str] = []
        self.page_size = 1000

    def publish(self, key: str, csv_text: str, *, corrupt: bool = False) -> None:
        """Publish a monthly zip holding one CSV beside its .CHECKSUM (a wrong one if corrupt)."""
        name = key.rsplit("/", 1)[-1]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(name.removesuffix(".zip") + ".csv", csv_text)
        payload = buf.getvalue()
        digest = hashlib.sha256(b"tampered" if corrupt else payload).hexdigest()
        self.files[key] = payload
        self.files[key + ".CHECKSUM"] = f"{digest}  {name}\n".encode()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url.startswith(archive_source.LISTING_URL):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)
            return self._listing(query["prefix"][0], query["marker"][0], "delimiter" in query)
        key = urllib.parse.unquote(url.removeprefix(archive_source.ARCHIVE_URL))
        if key not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return self.files[key]

    def _listing(self, prefix: str, marker: str, delimited: bool) -> bytes:
        entries = sorted(k for k in self.files if k.startswith(prefix))
        if delimited:
            entries = sorted({prefix + k[len(prefix):].split("/")[0] + "/"
                              for k in entries if "/" in k[len(prefix):]})
        remaining = [e for e in entries if e > marker]
        page, truncated = remaining[: self.page_size], len(remaining) > self.page_size
        tag = ("<CommonPrefixes><Prefix>{}</Prefix></CommonPrefixes>" if delimited
               else "<Contents><Key>{}</Key></Contents>")
        next_marker = f"<NextMarker>{page[-1]}</NextMarker>" if delimited and truncated else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>{next_marker}"
            + "".join(tag.format(e) for e in page)
            + "</ListBucketResult>"
        ).encode()


@pytest.fixture
def archive():
    return FakeArchive()


def make_spot_market(seed: int, signal: float = 0.0, start: str = "2017-08-17",
                     end: str = "2023-07-01", hourly_vol: float = 0.006):
    """(daily, hourly): synthetic BTCUSDT and ETHUSDT spot klines in the warehouse's columns.

    Each asset has a hidden regime f = ±1 that flips on about one day in 20 and shows in its
    taker-buy share (0.5 + 0.04·f). Day d drifts by `signal` · f[d-1], spread evenly over its 24
    hours, so with signal 0 both assets are random walks whatever their flow."""
    rng = np.random.default_rng(seed)
    first = int(pd.Timestamp(start, tz="UTC").value // 1_000_000)
    n_days = (int(pd.Timestamp(end, tz="UTC").value // 1_000_000) - first) // config.DAY_MS
    daily, hourly = {}, {}
    for k, symbol in enumerate(("BTCUSDT", "ETHUSDT")):
        regime = np.where(np.cumsum(rng.random(n_days) < 0.05) % 2 == 0, 1.0, -1.0)
        drift = signal * np.concatenate([[0.0], regime[:-1]])
        hours = rng.normal(np.repeat(drift / 24, 24), hourly_vol)
        close = 100.0 * (k + 1) * np.exp(np.cumsum(hours))
        open_ = np.concatenate([[100.0 * (k + 1)], close[:-1]])
        quote = rng.lognormal(10.0, 0.3, close.size)
        share = 0.5 + 0.04 * np.repeat(regime, 24) + rng.normal(0.0, 0.02, close.size)
        h = pd.DataFrame({
            "open_time": first + np.arange(close.size) * config.HOUR_MS,
            "open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close),
            "close": close, "volume": quote / close, "quote_volume": quote,
            "taker_buy_volume": share * quote / close, "taker_buy_quote_volume": share * quote,
            "trades": 100,
        })
        g = h.groupby(h["open_time"] // config.DAY_MS * config.DAY_MS)
        daily[symbol] = pd.DataFrame({
            "open_time": g["open_time"].first(), "open": g["open"].first(),
            "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
            "volume": g["volume"].sum(), "quote_volume": g["quote_volume"].sum(),
            "taker_buy_volume": g["taker_buy_volume"].sum(),
            "taker_buy_quote_volume": g["taker_buy_quote_volume"].sum(),
            "trades": g["trades"].sum(),
        }).reset_index(drop=True)
        hourly[symbol] = h
    return daily, hourly


@pytest.fixture
def spot_market():
    """make_spot_market, for the model lab's timing tests."""
    return make_spot_market
