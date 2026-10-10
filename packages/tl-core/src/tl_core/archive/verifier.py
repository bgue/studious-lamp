"""Verify an archive: files, signatures, the manifest chain, seq, event hashes, scope chains.

``verify_archive`` reports the first divergence per segment, in the order a tamperer would be
caught: missing file, file hash, signature, manifest chain, then seq gaps, event hashes and scope
chains event by event, and finally (with a connection) agreement with the database. The first
issue in the list is the first divergence in archive order (brief 24.5, "tampering suspicion").
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Connection, text

from tl_core.archive.errors import ArchiveError
from tl_core.archive.segments import (
    MANIFEST,
    NDJSON,
    PARQUET,
    SEGMENT_FILES,
    decode_ndjson,
    list_segment_names,
    manifest_signing_bytes,
    parquet_matches,
    parse_manifest,
    parse_segment_name,
    recomputed_hash,
    segment_key,
    sha256_hex,
)
from tl_core.archive.signing import key_id_of, verify_signature
from tl_core.archive.types import ArchiveStore, ScopeChain, SegmentManifest, VerifyIssue
from tl_core.ledger import Event

_DB_HASHES = text("SELECT seq, hash FROM events WHERE seq >= :first AND seq <= :last ORDER BY seq")


class _Chain:
    """What segment N must continue from, carried across the loop (updated even after an issue)."""

    def __init__(self) -> None:
        self.next_seq = 1
        self.prev_manifest_sha: str | None = None
        self.scope_last: dict[str, str] = {}


def _issue(kind: str, segment: str | None, seq: int | None, detail: str) -> VerifyIssue:
    return VerifyIssue.model_validate(
        {"kind": kind, "segment": segment, "seq": seq, "detail": detail}
    )


def _check_signature(manifest: SegmentManifest, public_key: bytes, name: str) -> VerifyIssue | None:
    signature = manifest.signature
    if signature is None:
        return _issue("signature", name, manifest.first_seq, "the manifest is not signed")
    if signature.alg != "ed25519":
        return _issue("signature", name, manifest.first_seq, f"unsupported alg {signature.alg!r}")
    if signature.key_id != key_id_of(public_key):
        return _issue(
            "signature",
            name,
            manifest.first_seq,
            f"signed by key {signature.key_id}, expected {key_id_of(public_key)}",
        )
    if not verify_signature(public_key, signature.value, manifest_signing_bytes(manifest)):
        return _issue("signature", name, manifest.first_seq, "the signature does not verify")
    return None


def _check_events(
    manifest: SegmentManifest, events: list[Event], name: str, chain: _Chain
) -> VerifyIssue | None:
    running = dict(chain.scope_last)
    first_prev: dict[str, str | None] = {}
    seen: dict[str, ScopeChain] = {}
    expected = manifest.first_seq
    for event in events:
        if event.seq != expected:
            kind_detail = f"expected seq {expected}, found {event.seq}"
            return _issue("seq_gap", name, expected, kind_detail)
        expected += 1
        if recomputed_hash(event) != event.hash:
            return _issue("event_hash", name, event.seq, "the hash does not match the event")
        before = running.get(event.scope)
        if event.prev_hash != before:
            return _issue(
                "scope_chain",
                name,
                event.seq,
                f"prev_hash does not continue scope {event.scope!r}",
            )
        running[event.scope] = event.hash
        if event.scope not in seen:
            first_prev[event.scope] = before
            seen[event.scope] = ScopeChain(prev_hash=before, last_hash=event.hash, event_count=1)
        else:
            seen[event.scope].last_hash = event.hash
            seen[event.scope].event_count += 1
    if expected != manifest.last_seq + 1 or len(events) != manifest.event_count:
        return _issue(
            "seq_gap",
            name,
            expected,
            f"found {len(events)} events up to seq {expected - 1}; the manifest says "
            f"{manifest.event_count} up to {manifest.last_seq}",
        )
    if seen != manifest.scopes:
        return _issue(
            "scope_chain", name, manifest.first_seq, "the manifest's scope chains do not match"
        )
    return None


def _check_segment(
    store: ArchiveStore,
    name: str,
    files: set[str],
    public_key: bytes,
    chain: _Chain,
    deep: bool,
) -> tuple[VerifyIssue | None, SegmentManifest | None, bytes | None, list[Event]]:
    for filename in SEGMENT_FILES:
        if filename not in files:
            missing = _issue("missing_file", name, None, f"{filename} is missing")
            if filename == MANIFEST:
                return missing, None, None, []
            # The manifest still tells the chain where it stands, so later segments are judged
            # on their own faults rather than on this one.
            data = store.get_bytes(segment_key(name, MANIFEST))
            try:
                return missing, parse_manifest(data), data, []
            except ArchiveError:
                return missing, None, None, []
    manifest_data = store.get_bytes(segment_key(name, MANIFEST))
    try:
        manifest = parse_manifest(manifest_data)
    except ArchiveError as error:
        return (
            _issue("signature", name, None, f"manifest.json is unreadable: {error}"),
            None,
            None,
            [],
        )
    ndjson = store.get_bytes(segment_key(name, NDJSON))
    parquet = store.get_bytes(segment_key(name, PARQUET))
    issue: VerifyIssue | None = None
    if sha256_hex(ndjson) != manifest.ndjson_sha256:
        issue = _issue("file_hash", name, manifest.first_seq, "events.ndjson differs from its hash")
    elif sha256_hex(parquet) != manifest.parquet_sha256:
        issue = _issue(
            "file_hash", name, manifest.first_seq, "events.parquet differs from its hash"
        )
    elif (issue := _check_signature(manifest, public_key, name)) is not None:
        pass
    elif parse_segment_name(name) != (manifest.first_seq, manifest.last_seq):
        issue = _issue(
            "manifest_chain", name, manifest.first_seq, "the directory does not match the manifest"
        )
    elif manifest.first_seq != chain.next_seq:
        issue = _issue(
            "manifest_chain"
            if manifest.prev_manifest_sha256 != chain.prev_manifest_sha
            else "seq_gap",
            name,
            chain.next_seq,
            f"segment starts at seq {manifest.first_seq}, expected {chain.next_seq}",
        )
    elif manifest.prev_manifest_sha256 != chain.prev_manifest_sha:
        issue = _issue(
            "manifest_chain", name, manifest.first_seq, "prev_manifest_sha256 breaks the chain"
        )
    events: list[Event] = []
    if issue is None:
        try:
            events = decode_ndjson(ndjson)
        except ArchiveError as error:
            issue = _issue("event_hash", name, manifest.first_seq, str(error))
    if issue is None:
        issue = _check_events(manifest, events, name, chain)
    if issue is None and deep and not parquet_matches(parquet, events):
        issue = _issue(
            "file_hash", name, manifest.first_seq, "events.parquet does not hold the ndjson events"
        )
    return issue, manifest, manifest_data, events


def _check_database(
    conn: Connection, manifest: SegmentManifest, events: list[Event], name: str
) -> VerifyIssue | None:
    rows = conn.execute(_DB_HASHES, {"first": manifest.first_seq, "last": manifest.last_seq}).all()
    stored = {int(row[0]): str(row[1]) for row in rows}
    for event in events:
        found = stored.get(event.seq)
        if found is None:
            return _issue("db_mismatch", name, event.seq, "the database has no event at this seq")
        if found != event.hash:
            return _issue(
                "db_mismatch", name, event.seq, "the database hash differs from the archive"
            )
    return None


def verify_archive(
    store: ArchiveStore,
    *,
    public_key: bytes,
    conn: Connection | None = None,
    deep: bool = False,
    stop_at_first: bool = True,
) -> list[VerifyIssue]:
    """Verify the archive; an empty list means verified.

    ``conn`` also checks that the database holds the same event hashes up to the last sealed seq.
    ``deep`` also checks that each ``events.parquet`` holds exactly its ndjson events.
    ``stop_at_first`` (the default) returns as soon as one divergence is found; otherwise at most
    one issue per segment is reported, in segment order.
    """
    issues: list[VerifyIssue] = []
    chain = _Chain()
    for name, files in list_segment_names(store).items():
        issue, manifest, manifest_data, events = _check_segment(
            store, name, files, public_key, chain, deep
        )
        if issue is None and conn is not None and manifest is not None:
            issue = _check_database(conn, manifest, events, name)
        if issue is not None:
            issues.append(issue)
            if stop_at_first:
                return issues
        if manifest is not None and manifest_data is not None:
            chain.next_seq = manifest.last_seq + 1
            chain.prev_manifest_sha = sha256_hex(manifest_data)
            for scope, scope_chain in manifest.scopes.items():
                chain.scope_last[scope] = scope_chain.last_hash
    return issues


def iter_segment_events(store: ArchiveStore) -> Iterator[Event]:
    """Every archived event in seq order. Call ``verify_archive`` first: this does not verify."""
    for name, files in list_segment_names(store).items():
        if NDJSON not in files or MANIFEST not in files:
            raise ArchiveError(f"segment {name} is incomplete")
        yield from decode_ndjson(store.get_bytes(segment_key(name, NDJSON)))
