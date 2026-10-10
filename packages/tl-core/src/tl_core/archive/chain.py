"""The sealed part of an archive: its manifests in order, and where the chain stands.

Reading this needs no database and no public key, only the manifests. The sealer uses it to
continue the chain; it refuses to continue a chain whose structure is already broken. Full
verification, including signatures, is ``verify_archive``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tl_core.archive.errors import ArchiveError
from tl_core.archive.segments import (
    MANIFEST,
    list_segment_names,
    parse_manifest,
    parse_segment_name,
    segment_key,
    sha256_hex,
)
from tl_core.archive.types import ArchiveStore, SegmentManifest


@dataclass(frozen=True)
class SealedSegment:
    name: str
    manifest: SegmentManifest
    manifest_bytes: bytes


@dataclass
class ChainState:
    """Everything the next segment must continue from."""

    sealed: list[SealedSegment] = field(default_factory=list[SealedSegment])
    orphan: tuple[int, int, str] | None = None  # (first_seq, last_seq, dir) without a manifest
    last_seq: int = 0
    last_manifest_sha256: str | None = None
    scope_last: dict[str, str] = field(default_factory=dict[str, str])
    """Scope to the hash of its last sealed event."""


def load_chain_state(store: ArchiveStore) -> ChainState:
    """Read every manifest and return the chain state; raise ``ArchiveError`` if it is broken."""
    state = ChainState()
    orphans: list[str] = []
    for name, files in list_segment_names(store).items():
        if MANIFEST not in files:
            orphans.append(name)
            continue
        if orphans:
            raise ArchiveError(
                f"segment {orphans[0]} has no manifest but later segments are sealed; "
                "the archive needs a human look"
            )
        data = store.get_bytes(segment_key(name, MANIFEST))
        manifest = parse_manifest(data)
        expected_first = state.last_seq + 1
        if parse_segment_name(name) != (manifest.first_seq, manifest.last_seq):
            raise ArchiveError(f"segment {name}: the directory does not match its manifest range")
        if manifest.first_seq != expected_first:
            raise ArchiveError(
                f"segment {name}: starts at seq {manifest.first_seq}, expected {expected_first}"
            )
        if manifest.prev_manifest_sha256 != state.last_manifest_sha256:
            raise ArchiveError(f"segment {name}: prev_manifest_sha256 does not match the chain")
        state.sealed.append(SealedSegment(name, manifest, data))
        state.last_seq = manifest.last_seq
        state.last_manifest_sha256 = sha256_hex(data)
        for scope, chain in manifest.scopes.items():
            state.scope_last[scope] = chain.last_hash
    if len(orphans) > 1:
        raise ArchiveError(f"more than one unsealed segment: {', '.join(orphans)}")
    if orphans:
        parsed = parse_segment_name(orphans[0])
        assert parsed is not None
        if parsed[0] != state.last_seq + 1:
            raise ArchiveError(
                f"unsealed segment {orphans[0]} does not continue the chain at seq "
                f"{state.last_seq + 1}"
            )
        state.orphan = (parsed[0], parsed[1], orphans[0])
    return state
