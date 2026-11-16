"""State guards: what a void punch item, a retired checklist and a cancelled inspection refuse
(the module's commands and the generic ones)."""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_quality.errors import PunchStateError
from tl_mod_quality.names import CANCELLED, DRAFT, OPEN, PLANNED, RETIRED, VOID

MSG_VOID = "a void punch item accepts no further change"
MSG_RETIRED = "a retired checklist accepts no further change"
MSG_CANCELLED = "a cancelled inspection accepts no further change"
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


def _refuse_state(conn: Connection, record_id: str, initial: str, state: str, message: str) -> None:
    found = conn.execute(_STATE, {"id": record_id}).scalar_one_or_none()
    if (initial if found is None else str(found)) == state:
        raise UnsupportedRecordTypeError(message)


def not_retired(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse a checklist that is Retired."""
    del slot
    _refuse_state(conn, record_id, DRAFT, RETIRED, MSG_RETIRED)


def not_cancelled(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse an inspection that is Cancelled."""
    del slot
    _refuse_state(conn, record_id, PLANNED, CANCELLED, MSG_CANCELLED)
