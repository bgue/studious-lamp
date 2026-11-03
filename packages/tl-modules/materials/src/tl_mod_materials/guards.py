"""State guards for the generic commands on a receipt (m4-materials.md section 3, last paragraph).

A file may be added to a receipt only while it is Received or Inspected, plus the
``certificate`` and
``photo`` slots once it is Accepted; nothing once it is Rejected or Void. The guard runs after the
allow-list, from every entry point that attaches a file (``ModuleSpec.generic_guards``).
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

OPEN_STATES = frozenset({"Received", "Inspected"})
ACCEPTED_SLOTS = frozenset({"certificate", "photo"})
_STATE = text("SELECT status, voided FROM cur_core_record WHERE id = :id")


def receipt_upload_guard(conn: Connection, record_id: str, slot: str | None) -> None:
    row = conn.execute(_STATE, {"id": record_id}).first()
    if row is None:
        return  # no such record: the caller reports that
    state = "Received" if row.status is None else str(row.status)
    if bool(row.voided) or state in {"Rejected", "Void"}:
        raise UnsupportedRecordTypeError("a file cannot be added to a rejected or void receipt")
    if state == "Accepted" and slot not in ACCEPTED_SLOTS:
        raise UnsupportedRecordTypeError(
            "an accepted receipt takes only certificate and photo files"
        )
    if state not in OPEN_STATES | {"Accepted"}:
        raise UnsupportedRecordTypeError("a file cannot be added to a receipt in this state")
