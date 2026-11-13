"""State guards: what a void punch item refuses (the module's commands and the generic ones)."""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_quality.errors import PunchStateError
from tl_mod_quality.names import OPEN, VOID

MSG_VOID = "a void punch item accepts no further change"
_STATE = text("SELECT status FROM cur_core_record WHERE id = :id")


def require_not_void(state: str) -> None:
    """``PunchStateError`` (the fixed message) when ``state`` is ``Void``."""
    if state == VOID:
        raise PunchStateError(MSG_VOID)


def not_void(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse a punch item that is Void."""
    del slot
    found = conn.execute(_STATE, {"id": record_id}).scalar_one_or_none()
    if (OPEN if found is None else str(found)) == VOID:
        raise UnsupportedRecordTypeError(MSG_VOID)
