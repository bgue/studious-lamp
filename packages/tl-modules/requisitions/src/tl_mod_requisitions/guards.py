"""State guards: what a record in a final state refuses.

A requisition that is Closed, Rejected or Cancelled and a work order that is Closed or Cancelled
take no further command (``require_open``: one fixed message). The same guard runs for the generic
commands a requisition takes (links, files, property values; ``ModuleSpec.generic_guards``).
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_requisitions.errors import RequisitionStateError
from tl_mod_requisitions.names import REQUISITION_FINAL, WORK_ORDER, WORK_ORDER_FINAL

MSG_FINAL = "the record is final and takes no further command"
_STATE = text("SELECT type, status FROM cur_core_record WHERE id = :id")


def require_open(record_type: str, state: str) -> None:
    """``RequisitionStateError`` (the fixed message) when ``state`` is a final one of the type."""
    final = WORK_ORDER_FINAL if record_type == WORK_ORDER else REQUISITION_FINAL
    if state in final:
        raise RequisitionStateError(MSG_FINAL)


def not_final(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse a record in a final state."""
    row = conn.execute(_STATE, {"id": record_id}).first()
    if row is None or row.status is None:
        return  # no such record (the caller reports that), or none moved yet
    final = WORK_ORDER_FINAL if row.type == WORK_ORDER else REQUISITION_FINAL
    if str(row.status) in final:
        raise UnsupportedRecordTypeError(MSG_FINAL)
