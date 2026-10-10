"""Ledger archive: sealed, signed, hash-chained segments (P0-I7).

``seal_segment`` writes them, ``verify_archive`` checks them, and ``iter_segment_events`` reads
them for a restore. The contracts are in ``types.py``.
"""

from tl_core.archive.chain import ArchiveSummary, summarize_archive
from tl_core.archive.errors import ArchiveError, ArchiveExistsError, RestoreError
from tl_core.archive.sealer import DEFAULT_MAX_EVENTS, read_events, seal_segment
from tl_core.archive.signing import (
    DEFAULT_KEY_PATH,
    Ed25519Signer,
    Signer,
    generate_signer,
    key_id_of,
    load_public_key,
    load_signer,
    public_key_path,
    write_keypair,
)
from tl_core.archive.types import (
    ARCHIVE_FORMAT,
    ArchiveStore,
    ScopeChain,
    SegmentManifest,
    SegmentSignature,
    VerifyIssue,
)
from tl_core.archive.verifier import iter_segment_events, verify_archive

__all__ = [
    "ARCHIVE_FORMAT",
    "DEFAULT_KEY_PATH",
    "DEFAULT_MAX_EVENTS",
    "ArchiveError",
    "ArchiveExistsError",
    "ArchiveStore",
    "ArchiveSummary",
    "Ed25519Signer",
    "RestoreError",
    "ScopeChain",
    "SegmentManifest",
    "SegmentSignature",
    "Signer",
    "VerifyIssue",
    "generate_signer",
    "iter_segment_events",
    "key_id_of",
    "load_public_key",
    "load_signer",
    "public_key_path",
    "read_events",
    "seal_segment",
    "summarize_archive",
    "verify_archive",
    "write_keypair",
]
