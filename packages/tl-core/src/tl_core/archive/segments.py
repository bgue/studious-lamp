"""Segment layout and file encodings (the contract in ``types.py``).

``events.ndjson`` is one canonical-JSON ``Event.model_dump(mode="json")`` per line.
``events.parquet`` has the ledger ``events`` table's column names and order, written by DuckDB;
``payload``, ``recorded_at`` and ``effective_at`` are the exact text the event hash covers, so a
lake rebuild can load a segment directly and every hash still re-verifies from Parquet alone.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb

from tl_core.archive.errors import ArchiveError
from tl_core.archive.types import ArchiveStore, SegmentManifest
from tl_core.ledger import Event, canonical_json, event_hash, iso_utc

SEGMENTS_PREFIX = "segments/"
NDJSON = "events.ndjson"
PARQUET = "events.parquet"
MANIFEST = "manifest.json"
SEGMENT_FILES = (NDJSON, PARQUET, MANIFEST)

EVENT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("seq", "BIGINT NOT NULL"),
    ("event_id", "VARCHAR NOT NULL"),
    ("stream_id", "VARCHAR NOT NULL"),
    ("stream_type", "VARCHAR NOT NULL"),
    ("stream_version", "BIGINT NOT NULL"),
    ("event_type", "VARCHAR NOT NULL"),
    ("schema_version", "BIGINT NOT NULL"),
    ("scope", "VARCHAR NOT NULL"),
    ("payload", "VARCHAR NOT NULL"),
    ("actor", "VARCHAR NOT NULL"),
    ("recorded_at", "VARCHAR NOT NULL"),
    ("effective_at", "VARCHAR NOT NULL"),
    ("correlation_id", "VARCHAR NOT NULL"),
    ("causation_id", "VARCHAR"),
    ("source", "VARCHAR NOT NULL"),
    ("prev_hash", "VARCHAR"),
    ("hash", "VARCHAR NOT NULL"),
)
"""The ledger ``events`` columns in table order, typed as the lake's bronze ``events`` table."""

_NAME = re.compile(r"^(\d{12})-(\d{12})$")


def segment_name(first_seq: int, last_seq: int) -> str:
    """``000000000001-000000000100``: the directory name of a segment."""
    return f"{first_seq:012d}-{last_seq:012d}"


def parse_segment_name(name: str) -> tuple[int, int] | None:
    """The ``(first_seq, last_seq)`` a directory name encodes, or ``None`` if it is not one."""
    match = _NAME.match(name)
    if match is None:
        return None
    first, last = int(match.group(1)), int(match.group(2))
    return (first, last) if 1 <= first <= last else None


def segment_key(name: str, filename: str) -> str:
    return f"{SEGMENTS_PREFIX}{name}/{filename}"


def list_segment_names(store: ArchiveStore) -> dict[str, set[str]]:
    """Segment directory name to the set of file names present, sorted by name."""
    found: dict[str, set[str]] = {}
    for key in store.list_keys(SEGMENTS_PREFIX):
        parts = key[len(SEGMENTS_PREFIX) :].split("/")
        if len(parts) == 2 and parse_segment_name(parts[0]) is not None:
            found.setdefault(parts[0], set()).add(parts[1])
    return dict(sorted(found.items()))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON (sorted keys, no spaces, UTF-8) of a JSON-compatible value."""
    return canonical_json(value).encode("utf-8")


def event_line(event: Event) -> bytes:
    return canonical_bytes(event.model_dump(mode="json")) + b"\n"


def encode_ndjson(events: Iterable[Event]) -> bytes:
    return b"".join(event_line(event) for event in events)


def decode_ndjson(data: bytes) -> list[Event]:
    """The events of an ``events.ndjson``; raises ``ArchiveError`` if a line is not an event."""
    events: list[Event] = []
    for number, line in enumerate(data.split(b"\n"), start=1):
        if not line:
            if number == data.count(b"\n") + 1:
                continue  # the empty piece after the final newline
            raise ArchiveError(f"events.ndjson line {number} is empty")
        try:
            events.append(Event.model_validate(json.loads(line)))
        except ValueError as error:
            raise ArchiveError(f"events.ndjson line {number} is not an event: {error}") from error
    return events


def recomputed_hash(event: Event) -> str:
    """The hash the event should carry, from its own fields (brief 5.1)."""
    return event_hash(
        event.prev_hash,
        event.event_id,
        event.stream_id,
        event.stream_version,
        event.event_type,
        canonical_json(event.payload),
        iso_utc(event.recorded_at),
    )


def event_row(event: Event) -> tuple[Any, ...]:
    """One Parquet row, in :data:`EVENT_COLUMNS` order, with the text the ledger stores."""
    return (
        event.seq,
        event.event_id,
        event.stream_id,
        event.stream_type,
        event.stream_version,
        event.event_type,
        event.schema_version,
        event.scope,
        canonical_json(event.payload),
        event.actor,
        iso_utc(event.recorded_at),
        iso_utc(event.effective_at),
        event.correlation_id,
        event.causation_id,
        event.source,
        event.prev_hash,
        event.hash,
    )


def _quoted(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def encode_parquet(events: Sequence[Event]) -> bytes:
    """``events.parquet`` for ``events``, written by DuckDB ``COPY`` (single thread, so the bytes
    are the same every time for the same events and DuckDB version)."""
    columns = ", ".join(f"{name} {kind}" for name, kind in EVENT_COLUMNS)
    marks = ", ".join("?" for _ in EVENT_COLUMNS)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / PARQUET
        con = duckdb.connect(":memory:")
        try:
            con.execute("SET threads = 1")
            con.execute(f"CREATE TABLE events ({columns})")
            if events:
                con.executemany(
                    f"INSERT INTO events VALUES ({marks})", [event_row(e) for e in events]
                )
            con.execute(
                f"COPY (SELECT * FROM events ORDER BY seq) TO {_quoted(target)} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        finally:
            con.close()
        return target.read_bytes()


def parquet_rows(data: bytes) -> list[tuple[Any, ...]]:
    """The rows of an ``events.parquet`` in seq order, as tuples in column order."""
    names = ", ".join(name for name, _ in EVENT_COLUMNS)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / PARQUET
        source.write_bytes(data)
        con = duckdb.connect(":memory:")
        try:
            rows = con.execute(
                f"SELECT {names} FROM read_parquet({_quoted(source)}) ORDER BY seq"
            ).fetchall()
        except duckdb.Error as error:
            raise ArchiveError(f"events.parquet is not readable: {error}") from error
        finally:
            con.close()
    return [tuple(row) for row in rows]


def parquet_matches(data: bytes, events: Sequence[Event]) -> bool:
    """True when the Parquet bytes hold exactly ``events`` (the ledger column names and text)."""
    try:
        return parquet_rows(data) == [event_row(event) for event in events]
    except ArchiveError:
        return False


def manifest_signing_bytes(manifest: SegmentManifest) -> bytes:
    """What is signed: the canonical manifest JSON with ``signature`` omitted."""
    return canonical_bytes(manifest.model_dump(mode="json", exclude={"signature"}))


def manifest_bytes(manifest: SegmentManifest) -> bytes:
    """The stored form of a manifest: canonical JSON including the signature."""
    return canonical_bytes(manifest.model_dump(mode="json"))


def parse_manifest(data: bytes) -> SegmentManifest:
    try:
        return SegmentManifest.model_validate_json(data)
    except ValueError as error:
        raise ArchiveError(f"manifest.json is not a manifest: {error}") from error


def encode_signature(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
