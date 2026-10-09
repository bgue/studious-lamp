"""Required file slots (brief 20.1, ``required_in_states``): what a record still lacks.

A slot with ``required_in_states`` must hold a current file (available, not superseded) by each of
those workflow states. The workflow layer uses ``missing_required_files`` as a guard, the same way
it uses expected links. A quarantined or rejected file never counts: only a file that passed its
scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from pydantic import BaseModel
from sqlalchemy import text

from tl_core.files.slots import FileSlot, FileSlotRegistry, default_file_slots
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

_COUNT_SQL = text(
    "SELECT COUNT(*) FROM cur_files WHERE record_id = :record_id AND slot = :slot "
    "AND status = 'available' AND superseded_by IS NULL"
)
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")


class MissingFile(BaseModel):
    """A required slot that has no current file."""

    slot: FileSlot
    found: int  # current files in the slot (0 for a slot that is missing)
    needed: int  # always 1: one current file satisfies a slot


def unmet_file_slots(
    uow: UnitOfWork, record_id: str, slots: Sequence[FileSlot]
) -> list[MissingFile]:
    """The slots, in the order given, that hold no current file for ``record_id``.

    Counts rows of ``cur_files`` with ``status = 'available'`` and ``superseded_by IS NULL`` for
    the record and slot name (``_COUNT_SQL``). A slot with at least one such row is met.
    """
    missing: list[MissingFile] = []
    for slot in slots:
        params = {"record_id": record_id, "slot": slot.name}
        found = int(uow.conn().execute(_COUNT_SQL, params).scalar_one())
        if found < 1:
            missing.append(MissingFile(slot=slot, found=found, needed=1))
    return missing


def missing_required_files(
    uow: UnitOfWork,
    record_id: str,
    *,
    registry: FileSlotRegistry | None = None,
    by_state: str | None = None,
) -> list[MissingFile]:
    """The required slots of a record that are still empty, using its type from ``cur_core_record``.

    ``registry`` defaults to ``default_file_slots()``. A slot is required when its
    ``required_in_states`` is not empty. With ``by_state`` only slots whose ``required_in_states``
    contains that state are checked; without it, every required slot is. Raises
    ``RecordNotFoundError`` (message ``no record <id!r>``) when the record does not exist.
    """
    row = uow.conn().execute(_TYPE_SQL, {"id": record_id}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    record_type = cast(str, row[0])
    if registry is None:
        registry = default_file_slots()
    slots = [slot for slot in registry.for_type(record_type) if slot.required_in_states]
    if by_state is not None:
        slots = [slot for slot in slots if by_state in slot.required_in_states]
    return unmet_file_slots(uow, record_id, slots)
