"""Who may read a thread: whoever may read its record (brief 21.5; FANOUT D9).

Every thread read and write loads the record through :func:`readable_record` first. A record the
caller cannot read gives ``RecordNotFoundError``, the same answer the record route gives, so a
thread never says that a record exists. In Phase 1 every signed-in person reads every record of
the scope they ask in; the confidentiality filters of P1-I5 plug in here, at this one function, when
the workstreams integrate (FANOUT D17).
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import text

from tl_core.integration.contract import RecordRef
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

_RECORD_SQL = text(
    "SELECT id, key, type, scope, status, voided, version, last_seq FROM cur_core_record "
    "WHERE id = :id"
)


@dataclass(frozen=True)
class ThreadRecord:
    """The facts about a thread's record that a thread needs."""

    id: str
    key: str | None
    record_type: str
    scope: str
    status: str | None
    voided: bool
    version: int
    seq: int

    def ref(self) -> RecordRef:
        return RecordRef(
            id=self.id,
            key=self.key,
            record_type=self.record_type,
            version=self.version,
            seq=self.seq,
        )


#: ``(uow, record_id, actor) -> bool``: whether ``actor`` may read the record. ``None`` (Phase 1
#: until P1-I5's confidentiality filters are plugged in) means every signed-in person reads every
#: record they ask for. This is the one place the filters plug in: the thread reads and writes
#: (:func:`readable_record`) and the events API and stream (:func:`can_read_record`) both use it.
RecordReadFilter = Callable[[UnitOfWork, str, str], bool]
_read_filter: RecordReadFilter | None = None


def install_read_filter(read_filter: RecordReadFilter | None) -> None:
    """Install (or, with ``None``, remove) the process-wide record read filter."""
    global _read_filter
    _read_filter = read_filter


@contextmanager
def use_read_filter(read_filter: RecordReadFilter) -> Generator[None]:
    """Install ``read_filter`` for the block (tests, embedders)."""
    global _read_filter
    previous, _read_filter = _read_filter, read_filter
    try:
        yield
    finally:
        _read_filter = previous


def can_read_record(uow: UnitOfWork, record_id: str, actor: str) -> bool:
    """Whether ``actor`` may read ``record_id``. A record that is not there cannot be read."""
    if uow.conn().execute(_RECORD_SQL, {"id": record_id}).first() is None:
        return False
    return _read_filter is None or _read_filter(uow, record_id, actor)


def readable_record(
    uow: UnitOfWork, record_id: str, *, actor: str, scope: str | None = None
) -> ThreadRecord:
    """The record of a thread as ``actor`` may read it.

    Raises ``RecordNotFoundError`` when there is no such record, when ``scope`` is given and the
    record belongs to another one, or (after P1-I5) when the actor may not read it.
    """
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if (
        row is None
        or (scope is not None and row.scope != scope)
        or (_read_filter is not None and not _read_filter(uow, record_id, actor))
    ):
        raise RecordNotFoundError(f"no record {record_id!r}")
    return ThreadRecord(
        id=row.id,
        key=row.key,
        record_type=row.type,
        scope=row.scope,
        status=row.status,
        voided=bool(row.voided),
        version=int(row.version),
        seq=int(row.last_seq),
    )
