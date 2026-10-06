"""Research tests need the dev-only deps; skip the whole directory without them.

Shared fixtures: `warehouse` points the store at a temp dir; `archive` stands in for
data.binance.vision and its S3 listing, so no test touches the network.
"""

import hashlib
import io
import urllib.error
import urllib.parse
import zipfile

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from research import archive_source, config  # noqa: E402  (the skips above guard these imports)


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
