"""State guards on the generic commands of documents records (ADR-0010 addendum, P1-I2).

The allow-list in ``module.py`` says which generic commands may reach a type; these guards say when.
They run in ``tl_core.modules.require_generic`` at the same places as the allow-list, including the
file upload path, so the API, the CLI, MCP and an accepted proposal all inherit them.

* **Revision, AttachFile.** What a revision accepts as an upload follows its state, the same table
  as ``AttachRendition`` (``UPLOAD_KINDS``): native and PDF only while it is a draft; a markup in
  any live state; a signed copy once issued; nothing when void. An attachment with no slot is
  refused: a revision's files are its four slots.
* **Transmittal, AttachFile, AddLink, SuggestLink.** Only while it is a draft: an issued
  transmittal is the record of what was sent.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_documents.names import RENDITION_KINDS

#: Kinds of file a revision accepts in each of its states.
UPLOAD_KINDS: dict[str, tuple[str, ...]] = {
    "Draft": ("native", "pdf", "markup"),
    "In Review": ("markup",),
    "Issued": ("markup", "signed"),
    "Superseded": ("markup", "signed"),
    "Void": (),
}
_STATE_SQL = text("SELECT status, voided FROM cur_core_record WHERE id = :id")


def state_of(conn: Connection, record_id: str) -> str:
    """The workflow state of a record (``Void`` when voided, ``Draft`` before its first move)."""
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None:
        return "Draft"
    return "Void" if bool(row.voided) else (row.status or "Draft")


def revision_upload(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse an upload the revision's state does not take (``AttachFile`` on a Revision)."""
    if slot is None:
        raise UnsupportedRecordTypeError(
            "a revision takes files in its slots only "
            f"({', '.join(RENDITION_KINDS)}); an attachment with no slot is refused"
        )
    state = state_of(conn, record_id)
    allowed = UPLOAD_KINDS.get(state, ())
    if slot not in allowed:
        raise UnsupportedRecordTypeError(
            f"a {state} revision takes "
            + (f"{', '.join(allowed)} files" if allowed else "no files")
            + f", not {slot}"
        )


def transmittal_draft_only(conn: Connection, record_id: str, slot: str | None) -> None:
    """Refuse a link, a flag, a retraction or an attachment on a transmittal past its draft.

    An admin corrects such a link with the core commands ``AdminFlagLink`` and ``AdminRetractLink``.
    """
    del slot
    state = state_of(conn, record_id)
    if state != "Draft":
        raise UnsupportedRecordTypeError(
            f"a {state} transmittal takes no more links, flags or attachments: it is the record of "
            "what was sent"
        )
