"""What other modules read from the punch list: the open items raised from a record.

Imports only ``tl_core`` and this module's own names. The viewer default is the lowest clearance
(``confidentiality.LOWEST``), never the ambient viewer and never widened: a caller that reads for a
person says so. A punch item whose source the viewer may not read is hidden whole
(``tl_core.confidentiality``, ``SUBJECT_LINKS``). The hidden filter is in the query, before the
limit; an answer holds at most ``MAX_ROWS`` items, more is a ``ValueError`` with a fixed message.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_quality.names import CATEGORIES, CLEARED, OPEN, PUNCH_ITEM_TABLE

MAX_ROWS: Final = 500
MSG_TOO_MANY: Final = "more than 500 punch items: narrow the question"
MSG_CATEGORY: Final = "unknown punch category"


@dataclass(frozen=True)
class PunchRef:
    """A punch item as a reader sees it in a list."""

    id: str
    key: str
    state: str
    category: str
    due_on: str | None


def open_punch_for(
    conn: Connection,
    record_id: str,
    *,
    categories: Collection[str] | None = None,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[PunchRef]:
    """The punch items raised from ``record_id`` that are not final (``Open`` and ``Cleared``), by
    key. ``categories`` limits them (an unknown one is a ``ValueError``). Hidden ones are left
    out."""
    if categories is not None and set(categories) - set(CATEGORIES):
        raise ValueError(MSG_CATEGORY)
    wanted = tuple(c for c in CATEGORIES if categories is None or c in set(categories))
    if not wanted:
        return []
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    marks = ", ".join(f":c{n}" for n in range(len(wanted)))
    statement = text(
        "SELECT t.id, r.key, COALESCE(r.status, :open) AS state, t.category, t.due_on "
        f"FROM {PUNCH_ITEM_TABLE} t JOIN cur_core_record r ON r.id = t.id "
        "WHERE t.source_id = :record AND r.voided = :no "
        f"AND COALESCE(r.status, :open) IN (:s_open, :s_cleared) AND t.category IN ({marks}) "
        f"AND {visible} ORDER BY r.key, r.id LIMIT :limit"
    )
    params = {
        "record": record_id,
        "no": False,
        "open": OPEN,
        "s_open": OPEN,
        "s_cleared": CLEARED,
        "limit": MAX_ROWS + 1,
        **{f"c{n}": c for n, c in enumerate(wanted)},
        **extra,
    }
    found = [
        PunchRef(
            id=str(row.id),
            key=str(row.key),
            state=str(row.state),
            category=str(row.category),
            due_on=None if row.due_on is None else str(row.due_on),
        )
        for row in conn.execute(statement, params)
    ]
    if len(found) > MAX_ROWS:
        raise ValueError(MSG_TOO_MANY)
    return found


__all__ = ["MAX_ROWS", "PunchRef", "open_punch_for"]
