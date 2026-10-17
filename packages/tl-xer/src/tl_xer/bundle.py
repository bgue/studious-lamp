"""The raw bundle: every table of the XER file, verbatim, as gzip-compressed JSON lines (bronze).

The bundle is what the lake loads into its ``xer_<table>`` tables (brief 28): all the tables the
file holds, not only the ones the snapshot is typed from. Layout of the uncompressed text, one JSON
value per line:

* line 1: ``{"kind": "xer-raw", "version": 1, "header": [...], "encoding": "cp1252"}``
* then for each table in file order: ``{"table": "TASK", "columns": [...], "rows": N}`` followed by
  N lines, each a JSON array of ``len(columns)`` strings.

The bytes are deterministic (gzip with a zero time stamp and no file name), and ``raw_sha256`` is
the SHA-256 of the *uncompressed* text, so it does not depend on the zlib version. Reading a bundle
back is bounded by ``MAX_BUNDLE_BYTES`` inflated: it is a file this system wrote, but the reader
never trusts a size it did not count.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from tl_xer import limits
from tl_xer.reader import RawXer

BUNDLE_KIND = "xer-raw"
BUNDLE_VERSION = 1


class BundleError(Exception):
    """A stored bundle is damaged, too large, or not the one the ledger recorded."""


def _line(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
    )


def write_bundle(raw: RawXer) -> tuple[bytes, str]:
    """``(gzip bytes, SHA-256 of the uncompressed text)``."""
    digest = hashlib.sha256()
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="", compresslevel=6) as gz:

        def put(value: Any) -> None:
            data = _line(value)
            digest.update(data)
            gz.write(data)

        put(
            {
                "kind": BUNDLE_KIND,
                "version": BUNDLE_VERSION,
                "header": list(raw.header),
                "encoding": raw.encoding,
            }
        )
        for table in raw.tables:
            put({"table": table.name, "columns": list(table.columns), "rows": len(table.rows)})
            for row in table.rows:
                put(list(row))
    return out.getvalue(), digest.hexdigest()


@dataclass(frozen=True)
class BundleTable:
    name: str
    columns: tuple[str, ...]
    rows: Iterator[tuple[str, ...]]


def _inflated(blob: bytes) -> Iterator[bytes]:
    """The lines of the uncompressed text, counting every byte against the bound."""
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as gz:
            for line in gz:
                total += len(line)
                if total > limits.MAX_BUNDLE_BYTES:
                    raise BundleError("the raw bundle inflates past its bound")
                yield line
    except (OSError, EOFError, zlib.error) as exc:
        raise BundleError("the raw bundle is not a valid gzip stream") from exc


def verify_bundle(blob: bytes, sha256: str) -> None:
    """Raise ``BundleError`` unless the uncompressed text of ``blob`` has digest ``sha256``."""
    digest = hashlib.sha256()
    for line in _inflated(blob):
        digest.update(line)
    if digest.hexdigest() != sha256:
        raise BundleError("the raw bundle is not the one the ledger recorded")


def read_bundle(blob: bytes) -> tuple[dict[str, Any], Iterator[BundleTable]]:
    """``(header line, tables)``: the tables are read one after the other, rows lazily.

    Each ``BundleTable.rows`` must be consumed before the next table is asked for.
    """
    lines = _inflated(blob)
    try:
        head = json.loads(next(lines))
    except (StopIteration, ValueError) as exc:
        raise BundleError("the raw bundle has no header line") from exc
    if (
        not isinstance(head, dict)
        or head.get("kind") != BUNDLE_KIND
        or head.get("version") != BUNDLE_VERSION
    ):  # pyright: ignore[reportUnknownMemberType]
        raise BundleError("the raw bundle is not an xer-raw version 1 file")

    def tables() -> Iterator[BundleTable]:
        for raw in lines:
            spec = json.loads(raw)
            count = int(spec["rows"])

            def rows(n: int = count) -> Iterator[tuple[str, ...]]:
                for _ in range(n):
                    yield tuple(json.loads(next(lines)))

            yield BundleTable(str(spec["table"]), tuple(spec["columns"]), rows())

    return head, tables()  # pyright: ignore[reportUnknownVariableType]
