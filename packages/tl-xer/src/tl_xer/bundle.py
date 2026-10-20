"""The raw bundle: every table of the XER file, verbatim, as gzip-compressed JSON lines (bronze).

The bundle is what the lake loads into its ``xer_<table>`` tables (brief 28): all the tables the
file holds, not only the ones the snapshot is typed from. Layout of the uncompressed text, one JSON
value per line (version 2):

* line 1: ``{"kind": "xer-raw", "version": 2, "header": [...], "encoding": "cp1252"}``
* then for each table in file order: ``{"table": "TASK", "columns": [...], "rows": N}`` followed by
  the N rows in *batches*: each line is a JSON array of up to ``BUNDLE_BATCH_ROWS`` rows (cut at
  about ``BUNDLE_BATCH_CHARS`` of text), and each row a JSON array of ``len(columns)`` strings.

Batches make writing fast (one encoder call per batch, not per row) and reading bounded (a line
is at most ``MAX_BUNDLE_LINE_BYTES``).

The bytes are deterministic (gzip with a zero time stamp and no file name), and ``raw_sha256`` is
the SHA-256 of the *uncompressed* text, so it does not depend on the zlib version. Reading a bundle
back is bounded twice: by ``MAX_BUNDLE_BYTES`` inflated, counted as the stream is read in fixed
chunks, and by ``MAX_BUNDLE_LINE_BYTES`` for any one line. It is a file this system wrote, but the
reader never trusts a size it did not count, and never lets the library hold a line it has not
measured.
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
BUNDLE_VERSION = 2
_CHUNK = 64 * 1024


class BundleError(Exception):
    """A stored bundle is damaged, too large, or not the one the ledger recorded."""


def _dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _batches(rows: tuple[tuple[str, ...], ...]) -> Iterator[list[tuple[str, ...]]]:
    """The rows in groups of at most ``BUNDLE_BATCH_ROWS`` and about ``BUNDLE_BATCH_CHARS``."""
    batch: list[tuple[str, ...]] = []
    chars = 0
    for row in rows:
        batch.append(row)
        chars += sum(map(len, row))
        if len(batch) >= limits.BUNDLE_BATCH_ROWS or chars >= limits.BUNDLE_BATCH_CHARS:
            yield batch
            batch, chars = [], 0
    if batch:
        yield batch


def write_bundle(raw: RawXer) -> tuple[bytes, str]:
    """``(gzip bytes, SHA-256 of the uncompressed text)``."""
    digest = hashlib.sha256()
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="", compresslevel=6) as gz:

        def put(value: Any) -> None:
            data = _dumps(value) + b"\n"
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
            for batch in _batches(table.rows):
                put(batch)
    return out.getvalue(), digest.hexdigest()


@dataclass(frozen=True)
class BundleTable:
    name: str
    columns: tuple[str, ...]
    rows: Iterator[tuple[str, ...]]


def _inflated(blob: bytes) -> Iterator[bytes]:
    """The lines of the uncompressed text (each with its newline).

    The stream is read in chunks of 64 KiB, every byte is counted against ``MAX_BUNDLE_BYTES``, and
    the lines are split here: the library's own line iteration would hold a whole line (a gigabyte
    of zeros is one line) before anyone could measure it. A line over ``MAX_BUNDLE_LINE_BYTES`` is
    refused as soon as it is seen to be that long.
    """
    total = 0
    pending = bytearray()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as gz:
            while True:
                chunk = gz.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.MAX_BUNDLE_BYTES:
                    raise BundleError("the raw bundle inflates past its bound")
                start = 0
                while (end := chunk.find(b"\n", start)) != -1:
                    pending += chunk[start : end + 1]
                    start = end + 1
                    yield bytes(pending)
                    pending.clear()
                pending += chunk[start:]
                if len(pending) > limits.MAX_BUNDLE_LINE_BYTES:
                    raise BundleError("a line of the raw bundle is longer than its bound")
            if pending:
                yield bytes(pending)  # the last line has no newline: the digest still counts it
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
    except (StopIteration, ValueError, RecursionError) as exc:
        raise BundleError("the raw bundle has no header line") from exc
    if (
        not isinstance(head, dict)
        or head.get("kind") != BUNDLE_KIND
        or head.get("version") != BUNDLE_VERSION
    ):  # pyright: ignore[reportUnknownMemberType]
        raise BundleError("the raw bundle is not an xer-raw version 2 file")

    def tables() -> Iterator[BundleTable]:
        try:
            for raw in lines:
                spec = json.loads(raw)
                count = int(spec["rows"])

                def rows(n: int = count) -> Iterator[tuple[str, ...]]:
                    seen = 0
                    while seen < n:
                        try:
                            batch = json.loads(next(lines))
                        except (ValueError, RecursionError, StopIteration) as exc:
                            raise BundleError("the raw bundle is damaged") from exc
                        seen += len(batch)
                        if seen > n:
                            raise BundleError(
                                "a table of the raw bundle has more rows than it says"
                            )
                        for row in batch:
                            yield tuple(row)

                yield BundleTable(str(spec["table"]), tuple(spec["columns"]), rows())
        except (ValueError, KeyError, TypeError, StopIteration, RecursionError) as exc:
            raise BundleError("the raw bundle is damaged") from exc

    return head, tables()  # pyright: ignore[reportUnknownVariableType]
