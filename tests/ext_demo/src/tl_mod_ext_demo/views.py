"""The read of one note, through the viewer's class filter (ADR-0016).

A hidden note and a missing one both answer ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_core import confidentiality

from . import NOTE_TABLE


@dataclass(frozen=True)
class NoteView:
    key: str
    title: str
    body: str


def get_note(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> NoteView | None:
    """The note of ``scope`` with ``key``; ``None`` if absent, voided or hidden from ``viewer``."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    statement = text(
        "SELECT r.key AS key, r.title AS title, n.body AS body "
        f"FROM {NOTE_TABLE} n JOIN cur_core_record r ON r.id = n.id "
        f"WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible}"
    )
    raw = conn.execute(statement, {"scope": scope, "key": key, "no": False, **extra}).mappings()
    found = raw.first()
    if found is None:
        return None
    return NoteView(key=str(found["key"]), title=str(found["title"]), body=str(found["body"]))
