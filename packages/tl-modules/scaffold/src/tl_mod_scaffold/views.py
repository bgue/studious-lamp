"""Read views of the scaffold register (P2-I4B T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``). Nothing here reads
the clock: the due questions take ``today`` (``YYYY-MM-DD``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection
from tl_core import confidentiality

MAX_LIMIT: Final = 500
EXPORT_FORMATS: Final = ("csv", "jsonl")
#: The exported columns, in order (the ``ScaffoldRow`` fields without ``id``).
EXPORT_COLUMNS: Final = (
    "key",
    "subject",
    "state",
    "tag",
    "tagged_on",
    "last_inspected_on",
    "next_due_on",
    "location",
    "elevation",
    "gridline",
    "load_class",
    "request_key",
)
_STUB: Final = "T01 fills this body"


@dataclass(frozen=True)
class ScaffoldRow:
    id: str  # the record id, for commands; never printed or exported
    key: str
    subject: str
    state: str
    tag: str | None
    tagged_on: str | None
    last_inspected_on: str | None
    next_due_on: str | None
    location: str | None  # the row's location_text
    elevation: str | None
    gridline: str | None
    load_class: str | None
    request_key: str | None  # the key of the scaffold request it was registered from


@dataclass(frozen=True)
class InspectionRow:
    key: str
    inspected_on: str
    inspector: str
    result: str
    tag: str | None
    note: str | None


@dataclass(frozen=True)
class ScaffoldDetail:
    row: ScaffoldRow
    inspection_count: int
    modify_reason: str | None
    dismantle_reason: str | None
    for_key: str | None  # the key of the record the request serves (an IWP)
    version: int
    inspections: list[InspectionRow]  # oldest first (inspected_on, key)


@dataclass(frozen=True)
class ScaffoldPage:
    rows: list[ScaffoldRow]
    total: int  # visible rows matching the filters, before the limit


def scaffold_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    tag: str | None = None,
    overdue: bool = False,
    today: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ScaffoldPage:
    """Visible scaffolds of ``scope`` by key."""
    raise NotImplementedError(_STUB)


def scaffold_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ScaffoldDetail | None:
    """One scaffold with its inspections; ``None`` when absent, in another project or hidden."""
    raise NotImplementedError(_STUB)


def due_list(
    conn: Connection,
    scope: str,
    today: str,
    *,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[ScaffoldRow]:
    """Standing scaffolds (Inspected, In Use, Modify) whose next inspection is due on or before
    ``today``, soonest due first, then by key."""
    raise NotImplementedError(_STUB)


def export_rows(rows: Sequence[ScaffoldRow], fmt: str) -> str:
    """The rows as ``csv`` (a header line, ``\\n`` line ends) or ``jsonl``; else ``ValueError``."""
    raise NotImplementedError(_STUB)


__all__ = [
    "EXPORT_COLUMNS",
    "EXPORT_FORMATS",
    "MAX_LIMIT",
    "InspectionRow",
    "ScaffoldDetail",
    "ScaffoldPage",
    "ScaffoldRow",
    "due_list",
    "export_rows",
    "scaffold_detail",
    "scaffold_list",
]
