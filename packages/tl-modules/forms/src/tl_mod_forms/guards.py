"""State guard of the generic commands a submission takes (property values, links, files).

A draft is the author's private work: it takes none of them, and neither does a discarded or a
voided form. A submitted, returned or accepted form does.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.services.errors import UnsupportedRecordTypeError

from tl_mod_forms.names import DISCARDED, DRAFT, VOIDED

MSG_NOT_SUBMITTED = "a form takes this change only once it is submitted, and not when it is void"
_STATE = text("SELECT status FROM cur_core_record WHERE id = :id")
_REFUSED = frozenset({DRAFT, DISCARDED, VOIDED})


def submitted_or_later(conn: Connection, record_id: str, slot: str | None) -> None:
    """The generic-command guard: refuse a submission that is a draft, discarded or void."""
    del slot
    found = conn.execute(_STATE, {"id": record_id}).scalar_one_or_none()
    if (DRAFT if found is None else str(found)) in _REFUSED:
        raise UnsupportedRecordTypeError(MSG_NOT_SUBMITTED)
