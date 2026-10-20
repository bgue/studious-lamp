"""State guards on the generic commands of correspondence records (ADR-0010 addendum).

The allow-list in ``module.py`` says which generic commands may reach a type; these guards say
when. They run in ``tl_core.modules.require_generic`` at the same places as the allow-list,
including the file upload path, so the API, the CLI, MCP and an accepted proposal all inherit
them (and a record the viewer may not read answers "not found" before the guard runs, ADR-0016).

* **Item, AttachFile.** A person attaches the slots ``original`` and ``attachment`` only (the
  slots ``rendition`` and ``message`` are written by the module), and only while the item is a
  Draft, Received or Triaged: an issued, answered or closed item is the record of what was sent or
  received.
* **Item, AddLink and SuggestLink.** Any state but Void.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_correspondence.names import (
    SLOT_ATTACHMENT,
    SLOT_ORIGINAL,
    ST_DRAFT,
    ST_RECEIVED,
    ST_TRIAGED,
    ST_VOID,
)

#: The slots a person may fill, and the states in which the item takes a file.
PERSON_SLOTS = (SLOT_ORIGINAL, SLOT_ATTACHMENT)
UPLOAD_STATES = (ST_DRAFT, ST_RECEIVED, ST_TRIAGED)
_STATE_SQL = text("SELECT status, voided FROM cur_core_record WHERE id = :id")


def state_of(conn: Connection, record_id: str) -> str:
    """The workflow state of a record (``Void`` when voided, ``Draft`` before its first move)."""
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None:
        return ST_DRAFT
    return ST_VOID if bool(row.voided) else (row.status or ST_DRAFT)


def item_upload(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse an upload the item's slot or state does not take (``AttachFile`` on an item)."""
    if slot not in PERSON_SLOTS:
        raise UnsupportedRecordTypeError(
            f"an item takes files in the slots {', '.join(PERSON_SLOTS)} only, not {slot!r}"
        )
    state = state_of(conn, record_id)
    if state not in UPLOAD_STATES:
        raise UnsupportedRecordTypeError(
            f"a {state} item takes no more files: it is the record of what was sent or received"
        )


def not_void(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse a new link on a void item."""
    del slot
    if state_of(conn, record_id) == ST_VOID:
        raise UnsupportedRecordTypeError("a void item takes no links")
