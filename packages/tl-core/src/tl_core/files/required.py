"""Required file slots (brief 20.1, ``required_in_states``): what a record still lacks.

A slot with ``required_in_states`` must hold a current file (available, not superseded) by each of
those workflow states. The workflow layer uses ``missing_required_files`` as a guard, the same way
it uses expected links. A quarantined or rejected file never counts: only a file that passed its
scan.

STUB (P0-I4-T23): the models and signatures are final; the two functions marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import text

from tl_core.files.slots import FileSlot, FileSlotRegistry
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
    raise NotImplementedError


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
    raise NotImplementedError
