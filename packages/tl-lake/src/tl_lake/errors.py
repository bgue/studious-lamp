"""Errors raised by tl_lake. Every one is a LakeError so a caller can catch the family."""

from __future__ import annotations


class LakeError(Exception):
    """Base class for lake failures."""


class LakeNotInitialisedError(LakeError):
    """The lake has no catalog yet: run ``tl lake sync`` first."""


class LakeLockTimeout(LakeError):
    """Another sync or query held the lake lock for longer than the timeout."""


class LakeSyncError(LakeError):
    """A sync failed. Nothing was committed, except when the message says the committed snapshot
    id differs from the recorded one (that check runs after COMMIT)."""


class LakeAheadError(LakeSyncError):
    """The lake is past the ledger's head: this is not the ledger the lake was built from."""


class LakeDivergedError(LakeSyncError):
    """The lake and the ledger hold different events at the same seq (different hash)."""
