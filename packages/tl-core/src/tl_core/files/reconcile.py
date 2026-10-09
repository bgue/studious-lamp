"""Object-store reconciliation: referenced hashes versus the store (brief 24.5, "missing or corrupt
objects"). Read-only: it reports; repair is a human decision (see the runbook).

Every distinct ``sha256`` in ``cur_files`` (any status, rejected files included, because their
bytes are kept) must have an object under its content key. With ``verify`` the bytes are read and
re-hashed, which catches corruption at the cost of reading everything. When the store can list its
keys (``iter_keys``, which the fs and s3 backends have and the ``ObjectStore`` Protocol does not),
content keys that no row references are reported as orphans (a rolled-back upload leaves one), and
``staging/`` keys are listed so an operator can clean them up.

STUB (P0-I4-T25): the models and signature are final; the function marked ``raise
NotImplementedError`` is the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy import text

from tl_core.files.types import ObjectStore
from tl_core.uow import UnitOfWork

_ROWS_SQL = text("SELECT sha256, size, file_id FROM cur_files ORDER BY sha256, file_id")


@runtime_checkable
class _Listing(Protocol):
    """A store that can list its keys (the fs and s3 backends; not part of ``ObjectStore``)."""

    def iter_keys(self) -> Iterator[str]: ...


class ObjectProblem(BaseModel):
    """One referenced hash whose object is missing or does not match its row."""

    kind: Literal["missing", "corrupt"]
    sha256: str
    key: str  # the content key (``sha256/aa/bb/<digest>``)
    file_ids: list[str]  # every cur_files row that references the hash, sorted
    detail: str | None = None  # for ``corrupt``: what differed


class ReconcileReport(BaseModel):
    checked: int  # distinct referenced hashes
    verified: bool  # True when the bytes were re-hashed
    listed: bool  # True when the store could list its keys (orphans and staging are meaningful)
    missing: list[ObjectProblem]  # sorted by sha256
    corrupt: list[ObjectProblem]  # sorted by sha256
    orphans: list[str]  # content keys in the store that no row references, sorted
    staging: list[str]  # keys under ``staging/``, sorted

    @property
    def ok(self) -> bool:
        """True when nothing is missing or corrupt (orphans and staging keys are only noise)."""
        return not self.missing and not self.corrupt


def reconcile_objects(
    uow: UnitOfWork, store: ObjectStore, *, verify: bool = False
) -> ReconcileReport:
    """Compare the ledger's file rows with the store.

    ``_ROWS_SQL`` gives one row per attachment. Group the rows by ``sha256``; the size of the first
    row of a hash is the size to check. For each hash, in sha256 order, an object that is not
    there (``store.exists(object_key(h))`` is false) is a ``missing`` problem. With ``verify`` a
    present object is read with ``store.get``, hashed in 1 MiB chunks and counted: a different
    digest gives a ``corrupt`` problem with detail ``"sha256 is <digest>"``; otherwise a different
    byte count gives ``"<n> bytes, expected <size>"``. The stream is always closed. Without
    ``verify`` nothing is read.

    If ``isinstance(store, _Listing)`` the store is listed: keys starting with
    ``sha256/`` that are not the key of a referenced hash are ``orphans``; keys starting with
    ``staging/`` are ``staging``; other keys are ignored. Otherwise ``listed`` is false and both
    lists are empty.
    """
    raise NotImplementedError
