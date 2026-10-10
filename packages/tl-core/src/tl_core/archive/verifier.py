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
from tl_core.archive.sealer import read_events, read_events_after
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

_HEAD = text("SELECT COALESCE(MAX(seq), 0) FROM events")
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
            if MANIFEST not in files:
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


def _differing_fields(row: Event, event: Event) -> str:
    names = [name for name in Event.model_fields if getattr(row, name) != getattr(event, name)]
    return ", ".join(names)


def _check_database(
    conn: Connection, manifest: SegmentManifest, events: list[Event], name: str, deep: bool
) -> VerifyIssue | None:
    if deep:
        return _check_database_rows(conn, manifest, events, name)
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


def _check_database_rows(
    conn: Connection, manifest: SegmentManifest, events: list[Event], name: str
) -> VerifyIssue | None:
    """Deep: recompute each database event's hash from its stored fields, then compare every field.

    A payload-only edit, a hash-only edit and a consistent payload-plus-hash edit are each caught
    here, in seq order.
    """
    stored = {row.seq: row for row in read_events(conn, manifest.first_seq, manifest.last_seq)}
    for event in events:
        row = stored.get(event.seq)
        if row is None:
            return _issue("db_mismatch", name, event.seq, "the database has no event at this seq")
        if recomputed_hash(row) != row.hash:
            return _issue(
                "event_hash",
                name,
                event.seq,
                "the database event's stored hash does not match its fields",
            )
        if row != event:
            return _issue(
                "db_mismatch",
                name,
                event.seq,
                f"the database row differs from the archive in: {_differing_fields(row, event)}",
            )
    return None


LEDGER_PAGE = 2000


def _scan_ledger(
    conn: Connection, start_seq: int, running: dict[str, str], page_size: int | None = None
) -> VerifyIssue | None:
    """Recompute the hash of every database event from ``start_seq`` on and check its chain.

    ``running`` is each scope's newest hash before ``start_seq`` (updated as the scan goes).
    Checks gap-free seq (across page boundaries too: pages are read by a ``seq >`` cursor and the
    scan ends only on an empty page), the hash against the event's own fields, and ``prev_hash``
    against the scope's previous event.
    """
    size = page_size if page_size is not None else LEDGER_PAGE
    expected = start_seq
    while True:
        page = read_events_after(conn, expected - 1, size)
        if not page:
            break
        for event in page:
            if event.seq != expected:
                detail = f"expected seq {expected}, found {event.seq}"
                return _issue("seq_gap", None, expected, detail)
            if recomputed_hash(event) != event.hash:
                return _issue(
                    "event_hash",
                    None,
                    event.seq,
                    "the database event's stored hash does not match its fields",
                )
            if event.prev_hash != running.get(event.scope):
                return _issue(
                    "scope_chain",
                    None,
                    event.seq,
                    f"prev_hash does not continue scope {event.scope!r}",
                )
            running[event.scope] = event.hash
            expected += 1
    head = int(conn.execute(_HEAD).scalar_one())
    if head != expected - 1 and head >= start_seq:
        return _issue(
            "seq_gap", None, expected, f"scanned up to seq {expected - 1}, head is {head}"
        )
    return None


def verify_ledger(conn: Connection) -> list[VerifyIssue]:
    """Verify the database alone: gap-free seq, every event hash recomputed from its stored
    fields, and every scope's ``prev_hash`` chain (brief 24.5, "hash-chain verification tool").

    Returns at most one issue, the first divergence in seq order; an empty list means the chain
    is intact. What it cannot see, because the database holds nothing to contradict it:
    - an edit to a scope's newest event that keeps that event's own hash consistent;
    - two events of different scopes that swapped their ``seq`` values (``seq`` is not part of the
      hash, and each scope's chain still holds);
    - events deleted from the end of the ledger.
    The remedies are an archive and a record outside the database: ``verify_archive(conn=...,
    deep=True)`` compares every field with the sealed copy, and ``expect_last_seq`` /
    ``expect_manifest_sha256`` (``tl archive verify --expect-last-seq N``) catch a shortened
    archive.
    """
    issue = _scan_ledger(conn, 1, {})
    return [issue] if issue is not None else []


def verify_archive(
    store: ArchiveStore,
    *,
    public_key: bytes,
    conn: Connection | None = None,
    deep: bool = False,
    stop_at_first: bool = True,
    expect_last_seq: int | None = None,
    expect_manifest_sha256: str | None = None,
) -> list[VerifyIssue]:
    """Verify the archive; an empty list means verified.

    ``conn`` also checks that the database holds the same event hashes up to the last sealed seq.
    ``deep`` also checks that each ``events.parquet`` holds exactly its ndjson events and, with
    ``conn``, recomputes every database event's hash from its stored fields, compares every field
    with the archive, and checks the chain of database events newer than the archive.
    ``stop_at_first`` (the default) returns as soon as one divergence is found; otherwise at most
    one issue per segment is reported, in segment order.

    The archive cannot show that whole trailing segments were removed: an archive that lags the
    database is normal. Record the last seq and the SHA-256 of the newest manifest outside the
    archive store (``tl archive seal`` prints them) and pass them back as ``expect_last_seq``
    (the archive must reach at least that seq) and ``expect_manifest_sha256`` (that manifest must
    still be in the chain). An archive longer than the record is fine.

    Design notes. Extra, unsigned fields added to a manifest are not covered by its signature but
    are covered by the next manifest's ``prev_manifest_sha256``, so adding one to anything but the
    newest manifest breaks the chain. ``sealed_at`` is not part of a segment's content: a seal that
    is re-run after a crash records a new time, which is fine.
    """
    issues: list[VerifyIssue] = []
    chain = _Chain()
    seen_manifests: set[str] = set()
    for name, files in list_segment_names(store).items():
        issue, manifest, manifest_data, events = _check_segment(
            store, name, files, public_key, chain, deep
        )
        if issue is None and conn is not None and manifest is not None:
            issue = _check_database(conn, manifest, events, name, deep)
        if issue is not None:
            issues.append(issue)
            if stop_at_first:
                return issues
        if manifest is not None and manifest_data is not None:
            chain.next_seq = manifest.last_seq + 1
            chain.prev_manifest_sha = sha256_hex(manifest_data)
            seen_manifests.add(chain.prev_manifest_sha)
            for scope, scope_chain in manifest.scopes.items():
                chain.scope_last[scope] = scope_chain.last_hash
    have = chain.next_seq - 1
    if deep and conn is not None and not issues:
        tail = _scan_ledger(conn, have + 1, dict(chain.scope_last))
        if tail is not None:
            issues.append(tail)
            if stop_at_first:
                return issues
    if expect_last_seq is not None and have < expect_last_seq:
        issues.append(
            _issue(
                "seq_gap",
                None,
                have + 1,
                f"the archive ends at seq {have} but the record says it reached {expect_last_seq}: "
                "trailing segments are missing",
            )
        )
        if stop_at_first:
            return issues
    if expect_manifest_sha256 is not None and expect_manifest_sha256 not in seen_manifests:
        issues.append(
            _issue(
                "manifest_chain",
                None,
                None,
                f"the recorded manifest {expect_manifest_sha256[:16]}... is not in the archive",
            )
        )
    return issues


def iter_segment_events(store: ArchiveStore) -> Iterator[Event]:
    """Every archived event in seq order. Call ``verify_archive`` first: this does not verify."""
    for name, files in list_segment_names(store).items():
        if NDJSON not in files or MANIFEST not in files:
            raise ArchiveError(f"segment {name} is incomplete")
        yield from decode_ndjson(store.get_bytes(segment_key(name, NDJSON)))
