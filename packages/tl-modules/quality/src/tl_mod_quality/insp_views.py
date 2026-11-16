"""Read views of checklists and inspections (P2-INSP S2 fixes the interface, T01 fills the bodies).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``, never widened) and
applies the hidden filter before ``LIMIT`` and before counting: an inspection is hidden through
its subject (``tl_core.confidentiality.SUBJECT_LINKS``), so a hidden subject reads as no rows, a
``None`` detail and a count of zero. Nothing here writes, checks an access word or reads the clock.
At most two SQL statements per call.

Rules the provided test pins, beyond the hidden filter: a row's ``for_key`` is ``None`` when the
viewer may not read the work package (``confidentiality.not_hidden("iwp.id", viewer)`` inside the
select), and a ``for_key`` filter never matches such a package (a key is not probed); a detail
names the punch items linked ``raised_against`` it by key (a second statement, filtered the same
way); ``inspections_for`` of a record the viewer may not read is empty; ``punch_count`` is the
number the result raised; ``done_on`` is the date part of ``done_at``; ``export_rows`` keeps the
columns of ``EXPORT_COLUMNS``, writes a header even for no rows in csv, and puts an apostrophe
before a csv cell that starts with ``= + - @``, TAB or CR (jsonl cells are untouched).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality

from tl_mod_quality.names import (
    CANCELLED,
    DONE,
    DRAFT,
    PLANNED,
    PUBLISHED,
    RETIRED,
    SCHEDULED,
    VERIFIED,
)

#: The most rows one list returns.
MAX_LIMIT: Final = 500
MSG_STATE: Final = "unknown inspection state"
MSG_POINT: Final = "unknown inspection point"
MSG_CHECKLIST_STATE: Final = "unknown checklist state"
MSG_FORMAT: Final = "export format: csv or jsonl"
INSPECTION_STATES: Final = (PLANNED, SCHEDULED, DONE, VERIFIED, CANCELLED)
CHECKLIST_STATES: Final = (DRAFT, PUBLISHED, RETIRED)
#: The columns of an export row, in order (one row per inspection).
EXPORT_COLUMNS: Final = (
    "number",
    "subject",
    "for",
    "point",
    "state",
    "result",
    "scheduled",
    "done",
    "inspector",
    "punch_count",
)
EXPORT_FORMATS: Final = ("csv", "jsonl")


@dataclass(frozen=True)
class InspectionRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    title: str
    subject_key: str | None
    for_key: str | None  # the work package; None when it is not readable by the viewer
    state: str
    point: str
    area: str | None
    planned_on: str | None
    scheduled_for: str | None
    inspector: str | None
    result: str | None
    done_on: str | None  # the day the result was recorded (YYYY-MM-DD)
    punch_count: int  # the punch items the result raised


@dataclass(frozen=True)
class InspectionDetail:
    row: InspectionRow
    checklist_key: str | None
    checklist_version: int | None
    answers: list[dict[str, Any]]
    note: str | None
    done_at: str | None
    recorded_by: str | None
    verified_by: str | None
    verified_on: str | None
    reinspection_of_key: str | None
    cancel_reason: str | None
    punch_keys: list[str]  # the punch items linked raised_against it, by key
    version: int


@dataclass(frozen=True)
class InspectionPage:
    rows: list[InspectionRow]
    total: int


@dataclass(frozen=True)
class ChecklistRow:
    id: str
    key: str
    title: str
    discipline: str | None
    version: int
    state: str
    question_count: int


@dataclass(frozen=True)
class ChecklistDetail:
    row: ChecklistRow
    questions: list[dict[str, Any]]
    supersedes_key: str | None
    published_by: str | None
    published_on: str | None
    retired_on: str | None
    record_version: int


@dataclass(frozen=True)
class ChecklistPage:
    rows: list[ChecklistRow]
    total: int


def inspection_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    point: str | None = None,
    area: str | None = None,
    inspector: str | None = None,
    subject_key: str | None = None,
    for_key: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> InspectionPage:
    """Visible inspections of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    raise NotImplementedError  # T01 fills the body


def inspection_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> InspectionDetail | None:
    """One inspection; ``None`` when it is absent, in another project or hidden."""
    raise NotImplementedError  # T01 fills the body


def inspection_counts(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Visible inspections by state, each of the five present."""
    raise NotImplementedError  # T01 fills the body


def inspections_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[InspectionRow]:
    """Visible inspections whose subject or work package is ``record_id``, by key; none when the
    record itself is hidden."""
    raise NotImplementedError  # T01 fills the body


def checklist_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    discipline: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ChecklistPage:
    """Visible checklists of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    raise NotImplementedError  # T01 fills the body


def checklist_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ChecklistDetail | None:
    """One checklist with its questions; ``None`` when it is absent or in another project."""
    raise NotImplementedError  # T01 fills the body


def export_rows(rows: Sequence[InspectionRow], fmt: str) -> str:
    """The rows as ``csv`` (a header, then a line per row, ``\\n`` ends; a cell that starts like a
    formula gets an apostrophe) or ``jsonl`` (one object per line, the same columns, null for
    none). The rows are the caller's page: whatever the viewer could not read is not in it."""
    raise NotImplementedError  # T01 fills the body
