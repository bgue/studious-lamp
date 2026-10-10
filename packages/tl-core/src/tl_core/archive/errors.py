"""Errors of the ledger archive (P0-I7)."""

from __future__ import annotations

from tl_core.archive.types import VerifyIssue


class ArchiveError(Exception):
    """The archive or the database is in a state the operation refuses to continue from."""


class ArchiveExistsError(ArchiveError):
    """``put_bytes`` was called for a key that already exists (the archive is write-once)."""


class RestoreError(ArchiveError):
    """A restore was refused or its result did not verify.

    ``issue`` carries the first divergence when verification caused the refusal.
    """

    def __init__(self, message: str, issue: VerifyIssue | None = None) -> None:
        super().__init__(message)
        self.issue = issue
