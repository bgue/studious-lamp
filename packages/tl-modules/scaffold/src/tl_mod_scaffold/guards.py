"""State guards: what a removed scaffold refuses (the module's commands and the generic ones)."""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_scaffold.errors import ScaffoldStateError
from tl_mod_scaffold.names import REMOVED, REQUESTED

MSG_REMOVED = "a removed scaffold accepts no further change"
_STATE = text("SELECT status FROM cur_core_record WHERE id = :id")


def require_not_removed(state: str) -> None:
    """``ScaffoldStateError`` (the fixed message) when ``state`` is ``Removed``."""
    if state == REMOVED:
        raise ScaffoldStateError(MSG_REMOVED)


def not_removed(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse a scaffold that is Removed."""
    del slot
    found = conn.execute(_STATE, {"id": record_id}).scalar_one_or_none()
    if (REQUESTED if found is None else str(found)) == REMOVED:
        raise UnsupportedRecordTypeError(MSG_REMOVED)


#: The workflow states in which each command takes a scaffold (the handlers read this table).
STATES: dict[str, tuple[str, ...]] = {
    "DesignScaffold": ("Requested",),
    "ErectScaffold": ("Designed",),
    "InspectScaffold": ("Erecting", "Inspected", "In Use", "Modify"),
    "TagScaffoldGreen": ("Erecting", "Modify", "Inspected", "In Use"),
    "ReleaseScaffold": ("Inspected",),
    "ModifyScaffold": ("Inspected", "In Use"),
    "DismantleScaffold": ("Inspected", "In Use", "Modify"),
    "RemoveScaffold": ("Requested", "Designed", "Dismantle"),
}
