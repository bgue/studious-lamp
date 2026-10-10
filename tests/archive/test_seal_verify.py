"""Sealer, signer and verifier: chains, crash safety, and a tampering test per VerifyIssue kind."""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pytest
from sqlalchemy import text
from tl_adapters.sqlite.engine import read_tx
from tl_core.archive import (
    ArchiveError,
    Ed25519Signer,
    SegmentManifest,
    generate_signer,
    key_id_of,
    load_public_key,
    load_signer,
    seal_segment,
    verify_archive,
    write_keypair,
)
from tl_core.archive.segments import (
    EVENT_COLUMNS,
    MANIFEST,
    NDJSON,
    PARQUET,
    canonical_bytes,
    manifest_bytes,
    manifest_signing_bytes,
    sha256_hex,
)
from tl_core.ledger import canonical_json, event_hash

MakeBox = Callable[[str], Any]
MakeStore = Callable[..., Any]

SEG1 = "segments/000000000001-000000000006"
SEG2 = "segments/000000000007-000000000012"
SEG3 = "segments/000000000013-000000000015"


def seal(box: Any, store: Any, signer: Ed25519Signer, **kw: Any) -> SegmentManifest | None:
    with read_tx(box.engine) as conn:
        return seal_segment(conn, store, signer, **kw)


def verify(store: Any, signer: Ed25519Signer, box: Any = None, **kw: Any) -> list[Any]:
    if box is None:
        return verify_archive(store, public_key=signer.public_key, **kw)
    with read_tx(box.engine) as conn:
        return verify_archive(store, public_key=signer.public_key, conn=conn, **kw)


@pytest.fixture
def sealed(make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer) -> tuple[Any, Any]:
    """15 events sealed as three segments of 6, 6 and 3 events."""
    box = make_box("a")
    box.add(15)
    store = memory_store()
    for _ in range(3):
        assert seal(box, store, signer, max_events=6) is not None
    assert seal(box, store, signer, max_events=6) is None
    return box, store


def resign(store: Any, signer: Ed25519Signer, segment: str, **changes: Any) -> None:
    """Rewrite a segment's manifest with the current file hashes plus ``changes``, and re-sign.

    Simulates an attacker who holds the signing key (or a sealer bug): only the semantic
    inconsistency is left for the verifier to find.
    """
    manifest = SegmentManifest.model_validate_json(store.get_bytes(f"{segment}/{MANIFEST}"))
    manifest.ndjson_sha256 = sha256_hex(store.get_bytes(f"{segment}/{NDJSON}"))
    manifest.parquet_sha256 = sha256_hex(store.get_bytes(f"{segment}/{PARQUET}"))
    for name, value in changes.items():
        setattr(manifest, name, value)
    manifest.signature = None
    from tl_core.archive.segments import encode_signature
    from tl_core.archive.types import SegmentSignature

    manifest.signature = SegmentSignature(
        alg="ed25519",
        key_id=signer.key_id,
        value=encode_signature(signer.sign(manifest_signing_bytes(manifest))),
    )
    store.overwrite(f"{segment}/{MANIFEST}", manifest_bytes(manifest))


def lines(store: Any, segment: str) -> list[dict[str, Any]]:
    data = store.get_bytes(f"{segment}/{NDJSON}")
    return [json.loads(line) for line in data.splitlines()]


def write_lines(store: Any, segment: str, rows: list[dict[str, Any]]) -> None:
    store.overwrite(f"{segment}/{NDJSON}", b"".join(canonical_bytes(row) + b"\n" for row in rows))


# --- sealing --------------------------------------------------------------------------------


def test_sealing_continues_the_chain_and_verifies(sealed: tuple[Any, Any], signer: Any) -> None:
    box, store = sealed
    assert verify(store, signer, box) == []
    manifests = [
        SegmentManifest.model_validate_json(store.get_bytes(f"{s}/{MANIFEST}"))
        for s in (SEG1, SEG2, SEG3)
    ]
    assert [(m.first_seq, m.last_seq, m.event_count) for m in manifests] == [
        (1, 6, 6),
        (7, 12, 6),
        (13, 15, 3),
    ]
    assert manifests[0].prev_manifest_sha256 is None
    assert manifests[1].prev_manifest_sha256 == sha256_hex(store.get_bytes(f"{SEG1}/{MANIFEST}"))
    assert manifests[2].prev_manifest_sha256 == sha256_hex(store.get_bytes(f"{SEG2}/{MANIFEST}"))
    # Each scope's chain continues across segments.
    for scope in manifests[1].scopes:
        before = manifests[0].scopes[scope].last_hash
        assert manifests[1].scopes[scope].prev_hash == before
    assert all(m.scopes[s].prev_hash is None for m in manifests[:1] for s in m.scopes)
    assert all(m.signature and m.signature.key_id == signer.key_id for m in manifests)


def test_sealing_nothing_new_returns_none_and_new_events_make_a_new_segment(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    store = memory_store()
    assert seal(box, store, signer) is None
    box.add(3)
    first = seal(box, store, signer)
    assert first is not None and (first.first_seq, first.last_seq) == (1, 3)
    assert seal(box, store, signer) is None
    box.add(2)
    second = seal(box, store, signer)
    assert second is not None and (second.first_seq, second.last_seq) == (4, 5)
    assert verify(store, signer, box) == []


def test_parquet_has_the_ledger_columns_and_the_exact_hashed_text(
    sealed: tuple[Any, Any], tmp_path: Path
) -> None:
    _, store = sealed
    target = tmp_path / "seg.parquet"
    target.write_bytes(store.get_bytes(f"{SEG1}/{PARQUET}"))
    con = duckdb.connect(":memory:")
    described = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{target}')").fetchall()
    assert [row[0] for row in described] == [name for name, _ in EVENT_COLUMNS]
    assert {row[0]: row[1] for row in described}["payload"] == "VARCHAR"
    assert {row[0]: row[1] for row in described}["recorded_at"] == "VARCHAR"
    rows = con.execute(f"SELECT * FROM read_parquet('{target}') ORDER BY seq").fetchall()
    assert [row[0] for row in rows] == [1, 2, 3, 4, 5, 6]
    for row in rows:
        seq, event_id, stream_id, _, version, event_type = row[:6]
        payload, recorded_at, prev_hash, stored = row[8], row[10], row[15], row[16]
        assert payload == canonical_json(json.loads(payload))
        assert (
            event_hash(prev_hash, event_id, stream_id, version, event_type, payload, recorded_at)
            == stored
        ), seq


def test_sealing_is_deterministic_across_stores(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(8)
    one, two = memory_store(), memory_store()
    seal(box, one, signer)
    seal(box, two, signer)
    for name in (NDJSON, PARQUET):
        key = f"segments/000000000001-000000000008/{name}"
        assert one.get_bytes(key) == two.get_bytes(key)


@pytest.mark.parametrize("crash_after_puts", [1, 2])
def test_a_crash_between_files_never_yields_a_different_segment(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer, crash_after_puts: int
) -> None:
    box = make_box("a")
    box.add(5)
    reference = memory_store()
    seal(box, reference, signer)

    crashing = memory_store(fail_after=crash_after_puts)
    with pytest.raises(Exception, match="segments/"):
        seal(box, crashing, signer)
    assert len(crashing.files) == crash_after_puts  # ndjson, then maybe parquet; no manifest
    assert not any(k.endswith(MANIFEST) for k in crashing.files)

    box.add(4)  # new events arrive before the retry
    crashing.fail_after = None
    resumed = seal(box, crashing, signer)
    assert resumed is not None and (resumed.first_seq, resumed.last_seq) == (1, 5)
    segment = "segments/000000000001-000000000005"
    for name in (NDJSON, PARQUET):
        assert crashing.get_bytes(f"{segment}/{name}") == reference.get_bytes(f"{segment}/{name}")
    left = SegmentManifest.model_validate_json(crashing.get_bytes(f"{segment}/{MANIFEST}"))
    ref = SegmentManifest.model_validate_json(reference.get_bytes(f"{segment}/{MANIFEST}"))
    assert left.model_dump(exclude={"sealed_at", "signature"}) == ref.model_dump(
        exclude={"sealed_at", "signature"}
    )
    nxt = seal(box, crashing, signer)
    assert nxt is not None and (nxt.first_seq, nxt.last_seq) == (6, 9)
    assert verify(crashing, signer, box) == []


def test_a_crash_before_any_file_leaves_nothing_and_the_retry_is_clean(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(3)
    store = memory_store(fail_after=0)
    with pytest.raises(Exception, match="segments/"):
        seal(box, store, signer)
    assert store.files == {}
    store.fail_after = None
    assert seal(box, store, signer) is not None
    assert verify(store, signer, box) == []


def test_a_leftover_file_that_differs_from_the_ledger_stops_the_sealer(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(3)
    store = memory_store(fail_after=1)
    with pytest.raises(Exception, match="segments/"):
        seal(box, store, signer)
    key = "segments/000000000001-000000000003/events.ndjson"
    store.overwrite(key, store.get_bytes(key).replace(b"caf", b"cat"))
    store.fail_after = None
    with pytest.raises(ArchiveError, match="differs"):
        seal(box, store, signer)


def test_the_store_is_write_once_so_a_second_sealer_cannot_replace_a_segment(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(3)
    store = memory_store()
    seal(box, store, signer)
    other = generate_signer()
    # Nothing new, so nothing is written; a forced rewrite of the same key is refused by the store.
    assert seal(box, store, other) is None
    with pytest.raises(Exception, match="segments/"):
        store.put_bytes("segments/000000000001-000000000003/manifest.json", b"{}")


def test_the_sealer_refuses_a_database_that_diverged_from_the_archive(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    one, other = make_box("a"), make_box("b")
    one.add(4)
    other.add(6, tag="y")
    store = memory_store()
    seal(one, store, signer)
    with pytest.raises(ArchiveError, match="diverged"):
        seal(other, store, signer)  # same seq 5 onward, but a different history


def test_the_sealer_refuses_a_database_behind_the_archive(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    one, empty = make_box("a"), make_box("b")
    one.add(4)
    store = memory_store()
    seal(one, store, signer)
    with pytest.raises(ArchiveError, match="behind"):
        seal(empty, store, signer)


def test_the_sealer_refuses_a_corrupt_ledger_row(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(3)
    with box.engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER trg_events_no_update")
        conn.exec_driver_sql("UPDATE events SET payload = '{\"n\":99}' WHERE seq = 2")
    with pytest.raises(ArchiveError, match="hash does not match"):
        seal(box, memory_store(), signer)


# --- tampering: one test per VerifyIssue kind ----------------------------------------------------


def test_missing_file(sealed: tuple[Any, Any], signer: Any) -> None:
    _, store = sealed
    store.remove(f"{SEG2}/{PARQUET}")
    [issue] = verify(store, signer)
    assert (issue.kind, issue.segment) == ("missing_file", SEG2.split("/")[1])


def test_file_hash_ndjson_and_parquet(sealed: tuple[Any, Any], signer: Any) -> None:
    _, store = sealed
    copy = store.copy()
    key = f"{SEG2}/{NDJSON}"
    copy.overwrite(key, copy.get_bytes(key).replace(b"caf", b"cat", 1))
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("file_hash", SEG2.split("/")[1])
    copy = store.copy()
    copy.overwrite(f"{SEG1}/{PARQUET}", copy.get_bytes(f"{SEG1}/{PARQUET}")[:-1] + b"x")
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("file_hash", SEG1.split("/")[1])


def test_signature_wrong_key_edited_manifest_and_unsigned(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    [issue] = verify(store, generate_signer())
    assert issue.kind == "signature" and issue.segment == SEG1.split("/")[1]
    copy = store.copy()
    manifest = json.loads(copy.get_bytes(f"{SEG1}/{MANIFEST}"))
    manifest["sealed_at"] = "2020-01-01T00:00:00Z"
    copy.overwrite(f"{SEG1}/{MANIFEST}", canonical_bytes(manifest))
    [issue] = verify(copy, signer)
    assert issue.kind == "signature" and "does not verify" in issue.detail
    copy = store.copy()
    manifest = json.loads(store.get_bytes(f"{SEG3}/{MANIFEST}"))
    manifest["signature"] = None
    copy.overwrite(f"{SEG3}/{MANIFEST}", canonical_bytes(manifest))
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("signature", SEG3.split("/")[1])


def test_manifest_chain_when_a_segment_is_removed_and_when_a_manifest_is_swapped(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    copy = store.copy()
    for name in (NDJSON, PARQUET, MANIFEST):
        copy.remove(f"{SEG2}/{name}")
    [issue] = verify(copy, signer)
    assert issue.kind == "manifest_chain" and issue.segment == SEG3.split("/")[1]
    # Re-signed segment 2 with another predecessor hash: the chain link breaks at segment 2.
    copy = store.copy()
    resign(copy, signer, SEG2, prev_manifest_sha256="0" * 64)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("manifest_chain", SEG2.split("/")[1])
    # And a re-signed segment 1 changes its bytes, so segment 2 no longer points at it.
    copy = store.copy()
    resign(copy, signer, SEG1, sealed_at="2030-01-01T00:00:00Z")
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("manifest_chain", SEG2.split("/")[1])


def test_seq_gap_inside_a_segment_and_between_segments(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    copy = store.copy()
    rows = lines(copy, SEG2)
    del rows[2]  # drop seq 9
    write_lines(copy, SEG2, rows)
    resign(copy, signer, SEG2)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment, issue.seq) == ("seq_gap", SEG2.split("/")[1], 9)
    # A properly chained and signed segment that skips seq 7 to 9.
    copy = store.copy()
    resign(copy, signer, SEG2, first_seq=9, event_count=4)
    [issue] = verify(copy, signer)
    assert issue.kind in {"seq_gap", "manifest_chain"} and issue.segment == SEG2.split("/")[1]


def test_event_hash(sealed: tuple[Any, Any], signer: Any) -> None:
    _, store = sealed
    rows = lines(store, SEG2)
    rows[3]["payload"]["n"] = 12345  # seq 10
    copy = store.copy()
    write_lines(copy, SEG2, rows)
    resign(copy, signer, SEG2)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment, issue.seq) == ("event_hash", SEG2.split("/")[1], 10)


def test_scope_chain_from_a_forged_manifest_and_from_a_forged_prev_hash(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    manifest = SegmentManifest.model_validate_json(store.get_bytes(f"{SEG2}/{MANIFEST}"))
    scopes = {k: v.model_copy() for k, v in manifest.scopes.items()}
    scope = sorted(scopes)[0]
    scopes[scope].last_hash = "f" * 64
    copy = store.copy()
    resign(copy, signer, SEG2, scopes=scopes)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("scope_chain", SEG2.split("/")[1])
    # Segment 2's manifest claims a different starting point for a scope than segment 1 ended at.
    scopes = {k: v.model_copy() for k, v in manifest.scopes.items()}
    scopes[scope].prev_hash = "e" * 64
    copy = store.copy()
    resign(copy, signer, SEG2, scopes=scopes)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment) == ("scope_chain", SEG2.split("/")[1])


def test_scope_chain_when_an_event_is_swapped_for_another_scopes_valid_hash(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    rows = lines(store, SEG2)
    # Re-hash seq 8 with a different prev_hash: a valid event hash, but not the scope's chain.
    row = rows[1]
    row["prev_hash"] = "d" * 64
    row["hash"] = event_hash(
        row["prev_hash"],
        row["event_id"],
        row["stream_id"],
        row["stream_version"],
        row["event_type"],
        canonical_json(row["payload"]),
        _iso(row["recorded_at"]),
    )
    copy = store.copy()
    write_lines(copy, SEG2, rows)
    resign(copy, signer, SEG2)
    [issue] = verify(copy, signer)
    assert (issue.kind, issue.segment, issue.seq) == ("scope_chain", SEG2.split("/")[1], 8)


def _iso(value: str) -> str:
    from datetime import datetime

    from tl_core.ledger import iso_utc

    return iso_utc(datetime.fromisoformat(value))


def test_db_mismatch_other_history_and_short_database(
    sealed: tuple[Any, Any], make_box: MakeBox, signer: Any
) -> None:
    _, store = sealed
    other = make_box("b")
    other.add(15, tag="y")
    [issue] = verify(store, signer, other)
    assert (issue.kind, issue.seq) == ("db_mismatch", 1)
    short = make_box("c")
    short.add(3)  # same events? no: different ids, so seq 1 already differs
    [issue] = verify(store, signer, short)
    assert issue.kind == "db_mismatch"


def test_db_mismatch_when_the_database_lost_its_tail(
    make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer
) -> None:
    box = make_box("a")
    box.add(6)
    store = memory_store()
    seal(box, store, signer)
    with box.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER trg_events_no_delete"))
        conn.execute(text("DELETE FROM events WHERE seq = 6"))
    [issue] = verify(store, signer, box)
    assert (issue.kind, issue.seq) == ("db_mismatch", 6)


def test_stop_at_first_false_reports_one_issue_per_broken_segment(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    copy = store.copy()
    copy.remove(f"{SEG1}/{PARQUET}")
    key = f"{SEG3}/{NDJSON}"
    copy.overwrite(key, copy.get_bytes(key) + b"\n")
    issues = verify(copy, signer, stop_at_first=False)
    assert [(i.kind, i.segment) for i in issues] == [
        ("missing_file", SEG1.split("/")[1]),
        ("file_hash", SEG3.split("/")[1]),
    ]


def test_deep_verification_compares_parquet_with_ndjson(
    sealed: tuple[Any, Any], signer: Any
) -> None:
    _, store = sealed
    assert verify(store, signer, deep=True) == []
    copy = store.copy()
    # A well-formed Parquet with other rows under the last segment; its manifest is re-signed, so
    # only the content check can see it. Nothing later points at that manifest, so the chain holds.
    copy.overwrite(f"{SEG3}/{PARQUET}", copy.get_bytes(f"{SEG2}/{PARQUET}"))
    resign(copy, signer, SEG3)
    assert verify(copy, signer) == []
    [issue] = verify(copy, signer, deep=True)
    assert (issue.kind, issue.segment) == ("file_hash", SEG3.split("/")[1])
    assert "parquet" in issue.detail


# --- signer ----------------------------------------------------------------------------------


def test_keypair_files_roundtrip_and_are_private(tmp_path: Path) -> None:
    path = tmp_path / "keys" / "archive-signing.key"
    signer = write_keypair(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_signer(path).key_id == signer.key_id
    assert load_public_key(path.with_suffix(".pub")) == signer.public_key
    assert load_public_key(path) == signer.public_key
    assert key_id_of(signer.public_key) == signer.key_id and len(signer.key_id) == 16
    with pytest.raises(FileExistsError):
        write_keypair(path)
    assert write_keypair(path, overwrite=True).key_id != signer.key_id


def test_manifest_json_is_canonical(sealed: tuple[Any, Any]) -> None:
    _, store = sealed
    data = store.get_bytes(f"{SEG1}/{MANIFEST}")
    assert data == canonical_bytes(json.loads(data))
    signing = manifest_signing_bytes(SegmentManifest.model_validate_json(data))
    assert b'"signature"' not in signing
