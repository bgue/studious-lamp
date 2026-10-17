"""State guards on the generic commands of schedule records (ADR-0010 addendum, ADR-0015).

* **ScheduleSnapshot, AttachFile.** A person attaches the XER file only: the slot ``xer``, only
  while the snapshot is Uploaded and its build has not been queued. The slots ``report`` and ``raw``
  are written by the module with ``by_module`` and are never a person's to fill; a snapshot that
  is read, built or published takes no more files, because it is the record of one export.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_schedule.names import SLOT_XER, SNAPSHOT_TABLE, UPLOADED

_STATE_SQL = text(
    "SELECT r.status, r.voided, t.source_file_id FROM cur_core_record r "
    f"LEFT JOIN {SNAPSHOT_TABLE} t ON t.id = r.id WHERE r.id = :id"
)


def snapshot_upload(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse an upload that is not the ``xer`` slot of an Uploaded snapshot that is not queued."""
    if slot != SLOT_XER:
        raise UnsupportedRecordTypeError(
            f"a schedule snapshot takes files in its {SLOT_XER!r} slot only"
        )
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None:
        return
    state = "Void" if bool(row.voided) else (row.status or UPLOADED)
    if state != UPLOADED or row.source_file_id is not None:
        raise UnsupportedRecordTypeError(
            f"a {state} snapshot takes no more files: "
            + ("its build is queued" if state == UPLOADED else "it is the record of one export")
        )
