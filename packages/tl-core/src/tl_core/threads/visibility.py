"""Who may read a thread: whoever may read its record (brief 21.5; FANOUT D9).

Every thread read and write loads the record through :func:`readable_record` first. A record the
caller cannot read gives ``RecordNotFoundError``, the same answer the record route gives, so a
thread never says that a record exists. In Phase 1 every signed-in person reads every record of
the scope they ask in; the confidentiality filters of P1-I5 plug in here, at this one function, when
the workstreams integrate (FANOUT D17).
"""

from __future__ import annotations

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


def readable_record(
    uow: UnitOfWork, record_id: str, *, actor: str, scope: str | None = None
) -> ThreadRecord:
    """The record of a thread as ``actor`` may read it.

    Raises ``RecordNotFoundError`` when there is no such record, when ``scope`` is given and the
    record belongs to another one, or (after P1-I5) when the actor may not read it.
    """
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or (scope is not None and row.scope != scope):
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
