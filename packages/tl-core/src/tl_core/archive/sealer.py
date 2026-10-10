"""Seal ledger events into a signed, hash-chained segment (brief 24.3).

``seal_segment`` is idempotent. Files are written in the order ndjson, parquet, manifest, and the
manifest is the commit marker: a segment without a manifest is unsealed. A crash between files
leaves a directory whose name fixes the seq range, and the next call seals exactly that range
(checking that any file already there matches what the database yields) before it takes new events.
So a crash never produces a different segment, and sealing never needs a delete (the store is
write-once).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.archive.chain import ChainState, load_chain_state
from tl_core.archive.errors import ArchiveError, ArchiveExistsError
from tl_core.archive.segments import (
    MANIFEST,
    NDJSON,
    PARQUET,
    encode_ndjson,
    encode_parquet,
    encode_signature,
    manifest_bytes,
    manifest_signing_bytes,
    parquet_matches,
    recomputed_hash,
    segment_key,
    segment_name,
    sha256_hex,
)
from tl_core.archive.signing import Signer
from tl_core.archive.types import (
    ARCHIVE_FORMAT,
    ArchiveStore,
    ScopeChain,
    SegmentManifest,
    SegmentSignature,
)
from tl_core.ledger import Event
from tl_core.util import utcnow

DEFAULT_MAX_EVENTS = 10_000

_SELECT_RANGE = text(
    "SELECT seq, event_id, stream_id, stream_type, stream_version, event_type, schema_version, "
    "scope, payload, actor, recorded_at, effective_at, correlation_id, causation_id, source, "
    "prev_hash, hash FROM events WHERE seq >= :first AND seq <= :last ORDER BY seq"
)
_HEAD = text("SELECT COALESCE(MAX(seq), 0) FROM events")


def _moment(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def read_events(conn: Connection, first_seq: int, last_seq: int) -> list[Event]:
    """The events ``first_seq`` to ``last_seq`` from the ledger table, in seq order."""
    rows = conn.execute(_SELECT_RANGE, {"first": first_seq, "last": last_seq}).mappings().all()
    return [
        Event(
            event_type=row["event_type"],
            schema_version=row["schema_version"],
            payload=json.loads(row["payload"]),
            seq=row["seq"],
            event_id=row["event_id"],
            stream_id=row["stream_id"],
            stream_type=row["stream_type"],
            stream_version=row["stream_version"],
            scope=row["scope"],
            actor=row["actor"],
            recorded_at=_moment(row["recorded_at"]),
            effective_at=_moment(row["effective_at"]),
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            source=row["source"],
            prev_hash=row["prev_hash"],
            hash=row["hash"],
        )
        for row in rows
    ]


def _utc_z(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _scope_chains(events: list[Event], state: ChainState) -> dict[str, ScopeChain]:
    """Check the events continue the archive's chain, and summarise each scope.

    Raises ``ArchiveError`` when the database disagrees with what is already sealed or with
    itself: sealing a divergent ledger would make the archive vouch for it.
    """
    running = dict(state.scope_last)
    chains: dict[str, ScopeChain] = {}
    for event in events:
        if recomputed_hash(event) != event.hash:
            raise ArchiveError(
                f"seq {event.seq}: the stored hash does not match the event's own fields; "
                "refusing to seal a corrupt ledger"
            )
        expected_prev = running.get(event.scope)
        if event.prev_hash != expected_prev:
            raise ArchiveError(
                f"seq {event.seq}: prev_hash of scope {event.scope!r} does not continue the "
                "archive's chain; the database has diverged from what is sealed"
            )
        running[event.scope] = event.hash
        existing = chains.get(event.scope)
        if existing is None:
            chains[event.scope] = ScopeChain(
                prev_hash=expected_prev, last_hash=event.hash, event_count=1
            )
        else:
            existing.last_hash = event.hash
            existing.event_count += 1
    return chains


_SCOPE_HASH = text(
    "SELECT hash FROM events WHERE scope = :scope AND seq <= :last ORDER BY seq DESC LIMIT 1"
)


def _check_sealed_prefix(conn: Connection, state: ChainState) -> None:
    """Refuse to continue when the database disagrees with what is already sealed.

    Every scope's newest sealed event must be the database's newest event of that scope at or
    below the last sealed seq. That covers the event at the last sealed seq itself and every scope
    the new segment does not touch, which the per-event chain check cannot see.
    """
    for scope, sealed_hash in sorted(state.scope_last.items()):
        found = conn.execute(_SCOPE_HASH, {"scope": scope, "last": state.last_seq}).scalar()
        if found != sealed_hash:
            raise ArchiveError(
                f"the database has diverged from what is sealed: scope {scope!r} ends at hash "
                f"{found!r} at or below seq {state.last_seq}, the archive says {sealed_hash!r}"
            )


def _put_same(store: ArchiveStore, key: str, data: bytes) -> None:
    """Write ``data`` at ``key``; a file already there is accepted only if it is identical."""
    if store.exists(key):
        if store.get_bytes(key) != data:
            raise ArchiveError(f"{key} already exists and differs from the ledger's events")
        return
    try:
        store.put_bytes(key, data)
    except ArchiveExistsError as error:  # another sealer won the race: accept only a match
        if store.get_bytes(key) != data:
            raise ArchiveError(f"{key} was written concurrently with different bytes") from error


def seal_segment(
    conn: Connection,
    store: ArchiveStore,
    signer: Signer,
    *,
    max_events: int = DEFAULT_MAX_EVENTS,
    clock: Callable[[], datetime] = utcnow,
) -> SegmentManifest | None:
    """Seal the events after the last sealed seq, at most ``max_events``; ``None`` if none are new.

    Finishes an interrupted segment first (see the module docstring).
    """
    if max_events < 1:
        raise ValueError("max_events must be at least 1")
    state = load_chain_state(store)
    head: int = conn.execute(_HEAD).scalar_one()
    if head < state.last_seq:
        raise ArchiveError(
            f"the database head ({head}) is behind the last sealed seq ({state.last_seq})"
        )
    _check_sealed_prefix(conn, state)
    if state.orphan is not None:
        first, last, _ = state.orphan
        if last > head:
            raise ArchiveError(
                f"unsealed segment {segment_name(first, last)} ends at seq {last} but the "
                f"database head is {head}"
            )
    else:
        first = state.last_seq + 1
        last = min(head, first + max_events - 1)
        if last < first:
            return None

    events = read_events(conn, first, last)
    if [e.seq for e in events] != list(range(first, last + 1)):
        raise ArchiveError(f"the database has no gap-free events for seq {first} to {last}")
    chains = _scope_chains(events, state)

    name = segment_name(first, last)
    ndjson = encode_ndjson(events)
    _put_same(store, segment_key(name, NDJSON), ndjson)

    parquet_key = segment_key(name, PARQUET)
    if store.exists(parquet_key):
        parquet = store.get_bytes(parquet_key)
        if not parquet_matches(parquet, events):
            raise ArchiveError(f"{parquet_key} exists but does not hold the ledger's events")
    else:
        parquet = encode_parquet(events)
        _put_same(store, parquet_key, parquet)

    manifest = SegmentManifest(
        format=ARCHIVE_FORMAT,
        first_seq=first,
        last_seq=last,
        event_count=last - first + 1,
        sealed_at=_utc_z(clock()),
        ndjson_sha256=sha256_hex(ndjson),
        parquet_sha256=sha256_hex(parquet),
        scopes=chains,
        prev_manifest_sha256=state.last_manifest_sha256,
    )
    manifest.signature = SegmentSignature(
        alg="ed25519",
        key_id=signer.key_id,
        value=encode_signature(signer.sign(manifest_signing_bytes(manifest))),
    )
    try:
        store.put_bytes(segment_key(name, MANIFEST), manifest_bytes(manifest))
    except ArchiveExistsError as error:
        raise ArchiveError(f"segment {name} was sealed concurrently; run seal again") from error
    return manifest
