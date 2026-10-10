"""Ledger archive contracts for P0-I7 (brief §24.3, §24.4, §24.5 "tampering suspicion").

Frozen for the increment: change only by orchestrator decision.

A segment is a contiguous range of global ``seq`` values, sealed once. Its files live under
``segments/<first_seq:012d>-<last_seq:012d>/`` in an ArchiveStore that is independent of the
database and of the record object store:

- ``events.ndjson``: one event per line, ``Event.model_dump(mode="json")`` serialised as canonical
  JSON (sorted keys, no spaces, UTF-8), ordered by seq, newline-terminated.
- ``events.parquet``: the same rows. ``payload`` is the canonical JSON text, so hashes re-verify
  from Parquet alone. Written with DuckDB ``COPY ... TO`` (no pyarrow dependency).
- ``manifest.json``: a :class:`SegmentManifest`, canonical JSON.

Manifests chain: each manifest names the SHA-256 of the previous manifest's bytes, and records,
per scope, the hash before the segment's first event of that scope and the hash of its last.
Together with the per-scope event hash chain (03 §7 ``event_hash``), that gives one verifiable
chain across the database and the archive.

Restore never goes through ``Ledger.append``, which assigns seq, ids and hashes. It uses an
adapter-level admin function per dialect (``tl_adapters.<dialect>.admin.restore_events``) that
inserts events verbatim into an empty database, then rebuilds projections. The 03 §7 interfaces
do not change.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

ARCHIVE_FORMAT = "tl-archive/1"
SignatureAlg = Literal["ed25519"]


class ScopeChain(BaseModel):
    """The hash chain of one scope across a segment."""

    prev_hash: str | None  # hash of the scope's event just before this segment (None: first ever)
    last_hash: str  # hash of the scope's last event in this segment
    event_count: int


class SegmentSignature(BaseModel):
    alg: SignatureAlg
    key_id: str  # sha256 hex of the raw public key, first 16 characters
    value: str  # base64 signature over the canonical manifest JSON with "signature" omitted


class SegmentManifest(BaseModel):
    format: Literal["tl-archive/1"] = "tl-archive/1"
    first_seq: int
    last_seq: int
    event_count: int  # always last_seq - first_seq + 1: seq is gap-free
    sealed_at: str  # ISO 8601 UTC with "Z"
    ndjson_sha256: str
    parquet_sha256: str
    scopes: dict[str, ScopeChain]
    prev_manifest_sha256: str | None  # None only for the first segment
    signature: SegmentSignature | None = None  # None only while being built


class ArchiveStore(Protocol):
    """Write-once byte store for archive files. Phase 0 backend: a local directory (fs).

    put_bytes refuses to overwrite an existing key (object-lock semantics, §24.3).
    """

    def put_bytes(self, key: str, data: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...  # sorted ascending


class VerifyIssue(BaseModel):
    """The first divergence a verification finds (§24.5 tampering suspicion)."""

    kind: Literal[
        "missing_file",
        "file_hash",
        "signature",
        "manifest_chain",
        "seq_gap",
        "event_hash",
        "scope_chain",
        "db_mismatch",
    ]
    segment: str | None
    seq: int | None
    detail: str


# Service signatures (implemented in tl_core.archive; supervisor-built: sealer and verifier):
#   seal_segment(conn, store: ArchiveStore, signer: Signer, *, max_events: int = 10_000)
#       -> SegmentManifest | None
#       Seals events after the last sealed seq, up to max_events. None when nothing is new.
#       Idempotent: re-running after a crash between files never writes a different segment.
#   verify_archive(store, *, public_key: bytes, conn: Connection | None = None)
#       -> list[VerifyIssue]
#       Checks files, signatures, the manifest chain, gap-free seq, every event hash, and the
#       per-scope chains; with conn, also that the database agrees up to the last sealed seq.
#       Empty list = verified.
#   Signer: Protocol with key_id: str and sign(data: bytes) -> bytes. Dev key: Ed25519 from
#       `cryptography`, private key at dev/data/archive-signing.key (git-ignored, created by
#       `tl archive keygen`). Key custody in production is a later decision.
