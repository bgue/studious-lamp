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

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality

from tl_mod_quality.names import (
    CANCELLED,
    CHECKLIST_TABLE,
    DONE,
    DRAFT,
    INSPECTION_TABLE,
    PLANNED,
    POINTS,
    PUBLISHED,
    RAISED_AGAINST,
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


_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")

#: The inspection row: its record, its state (``cur_workflow_state``; Planned until one is written),
#: its subject, and its work package (the key only when the viewer may read the package).
_ROW_COLUMNS = (
    "r.id AS id, r.key AS key, r.title AS title, "
    "COALESCE(ws.state, :planned) AS state, i.point AS point, i.area AS area, "
    "i.planned_on AS planned_on, i.scheduled_for AS scheduled_for, i.inspector AS inspector, "
    "i.result AS result, i.done_at AS done_at, i.punch_count AS punch_count, "
    "subj.key AS subject_key, iwp.key AS for_key"
)
_DETAIL_COLUMNS = (
    "ck.key AS checklist_key, i.checklist_version AS checklist_version, "
    "i.answers_json AS answers_json, i.note AS note, i.recorded_by AS recorded_by, "
    "i.verified_by AS verified_by, i.verified_on AS verified_on, "
    "ro.key AS reinspection_of_key, i.cancel_reason AS cancel_reason, r.version AS version"
)
_CHECKLIST_ROW = (
    "r.id AS id, r.key AS key, r.title AS title, c.discipline AS discipline, "
    "c.checklist_version AS version, COALESCE(ws.state, :draft) AS state, "
    "c.question_count AS question_count"
)
_CHECKLIST_FROM = (
    f"FROM {CHECKLIST_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "LEFT JOIN cur_workflow_state ws ON ws.record_id = c.id "
)


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _joins(viewer: confidentiality.Viewer) -> tuple[str, dict[str, Any]]:
    """The inspection and its joins. A work package the viewer may not read joins to nothing: its
    key is None and a ``for_key`` filter never matches it. The reinspected record is read the same
    way."""
    package, package_params = confidentiality.not_hidden("iwp.id", viewer)
    original, original_params = confidentiality.not_hidden("ro.id", viewer)
    sql = (
        f"FROM {INSPECTION_TABLE} i JOIN cur_core_record r ON r.id = i.id "
        "LEFT JOIN cur_workflow_state ws ON ws.record_id = i.id "
        "LEFT JOIN cur_core_record subj ON subj.id = i.subject_id "
        f"LEFT JOIN cur_core_record iwp ON iwp.id = i.for_iwp_id AND {package} "
        "LEFT JOIN cur_core_record ck ON ck.id = i.checklist_id "
        f"LEFT JOIN cur_core_record ro ON ro.id = i.reinspection_of_id AND {original} "
    )
    return sql, {**package_params, **original_params}


def _row(raw: RowMapping) -> InspectionRow:
    done_at = _text(raw["done_at"])
    return InspectionRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        title=str(raw["title"]),
        subject_key=_text(raw["subject_key"]),
        for_key=_text(raw["for_key"]),
        state=str(raw["state"]),
        point=str(raw["point"]),
        area=_text(raw["area"]),
        planned_on=_text(raw["planned_on"]),
        scheduled_for=_text(raw["scheduled_for"]),
        inspector=_text(raw["inspector"]),
        result=_text(raw["result"]),
        done_on=None if done_at is None else done_at[:10],
        punch_count=int(raw["punch_count"] or 0),
    )


def _checklist_row(raw: RowMapping) -> ChecklistRow:
    return ChecklistRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        title=str(raw["title"]),
        discipline=_text(raw["discipline"]),
        version=int(raw["version"]),
        state=str(raw["state"]),
        question_count=int(raw["question_count"] or 0),
    )


def _export_record(row: InspectionRow) -> dict[str, Any]:
    return {
        "number": row.key,
        "subject": row.subject_key,
        "for": row.for_key,
        "point": row.point,
        "state": row.state,
        "result": row.result,
        "scheduled": row.scheduled_for,
        "done": row.done_on,
        "inspector": row.inspector,
        "punch_count": row.punch_count,
    }


def _csv_cell(value: Any) -> Any:
    """A csv cell that reads as a formula gets an apostrophe in front."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


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
    if state is not None and state not in INSPECTION_STATES:
        raise ValueError(MSG_STATE)
    if point is not None and point not in POINTS:
        raise ValueError(MSG_POINT)
    source, params = _joins(viewer)
    params.update(
        {
            "planned": PLANNED,
            "scope": scope,
            "no": False,
            "limit": max(1, min(int(limit), MAX_LIMIT)),
        }
    )
    conds = ["r.scope = :scope", "r.voided = :no"]
    if state is not None:
        conds.append("COALESCE(ws.state, :planned) = :state")
        params["state"] = state
    if point is not None:
        conds.append("i.point = :point")
        params["point"] = point
    if area is not None:
        conds.append("i.area = :area")
        params["area"] = area
    if inspector is not None:
        conds.append("i.inspector = :inspector")
        params["inspector"] = inspector
    if subject_key is not None:
        conds.append("subj.key = :subject_key")
        params["subject_key"] = subject_key
    if for_key is not None:
        conds.append("iwp.key = :for_key")
        params["for_key"] = for_key
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    conds.append(visible)
    params.update(extra)
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) AS n {source} WHERE {where}"), params).scalar_one()
    raws = conn.execute(
        text(f"SELECT {_ROW_COLUMNS} {source} WHERE {where} ORDER BY r.key, r.id LIMIT :limit"),
        params,
    ).mappings()
    return InspectionPage(rows=[_row(raw) for raw in raws], total=int(total))


def inspection_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> InspectionDetail | None:
    """One inspection; ``None`` when it is absent, in another project or hidden."""
    source, params = _joins(viewer)
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    params.update({**extra, "planned": PLANNED, "scope": scope, "key": key, "no": False})
    statement = text(
        f"SELECT {_ROW_COLUMNS}, {_DETAIL_COLUMNS} {source} "
        f"WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible}"
    )
    raw = conn.execute(statement, params).mappings().first()
    if raw is None:
        return None
    row = _row(raw)
    # the punch items raised against this inspection, by key (the second statement)
    punch_visible, punch_extra = confidentiality.not_hidden("p.id", viewer)
    punch_rows = conn.execute(
        text(
            "SELECT p.key AS key FROM cur_links l JOIN cur_core_record p ON p.id = l.from_id "
            "WHERE l.to_id = :inspection AND l.relation = :relation "
            "AND l.status <> 'retracted' AND p.voided = :no "
            f"AND {punch_visible} ORDER BY p.key, p.id"
        ),
        {**punch_extra, "inspection": row.id, "relation": RAISED_AGAINST, "no": False},
    ).mappings()
    return InspectionDetail(
        row=row,
        checklist_key=_text(raw["checklist_key"]),
        checklist_version=None
        if raw["checklist_version"] is None
        else int(raw["checklist_version"]),
        answers=json.loads(str(raw["answers_json"] or "[]")),
        note=_text(raw["note"]),
        done_at=_text(raw["done_at"]),
        recorded_by=_text(raw["recorded_by"]),
        verified_by=_text(raw["verified_by"]),
        verified_on=_text(raw["verified_on"]),
        reinspection_of_key=_text(raw["reinspection_of_key"]),
        cancel_reason=_text(raw["cancel_reason"]),
        punch_keys=[str(p["key"]) for p in punch_rows],
        version=int(raw["version"]),
    )


def inspection_counts(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Visible inspections by state, each of the five present."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    statement = text(
        "SELECT ws.state AS state, COUNT(*) AS n "
        f"FROM {INSPECTION_TABLE} i JOIN cur_core_record r ON r.id = i.id "
        "LEFT JOIN cur_workflow_state ws ON ws.record_id = i.id "
        f"WHERE r.scope = :scope AND r.voided = :no AND {visible} GROUP BY ws.state"
    )
    counts: dict[str, int] = dict.fromkeys(INSPECTION_STATES, 0)
    for raw in conn.execute(statement, {**extra, "scope": scope, "no": False}).mappings():
        name = PLANNED if raw["state"] is None else str(raw["state"])
        if name in counts:
            counts[name] += int(raw["n"])
    return counts


def inspections_for(
    conn: Connection,
    record_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[InspectionRow]:
    """Visible inspections whose subject or work package is ``record_id``, by key; none when the
    record itself is hidden."""
    if confidentiality.is_hidden(conn, record_id, viewer):
        return []
    source, params = _joins(viewer)
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    params.update({**extra, "planned": PLANNED, "rid": record_id, "no": False})
    raws = conn.execute(
        text(
            f"SELECT {_ROW_COLUMNS} {source} "
            "WHERE (i.subject_id = :rid OR i.for_iwp_id = :rid) AND r.voided = :no "
            f"AND {visible} ORDER BY r.key, r.id"
        ),
        params,
    ).mappings()
    return [_row(raw) for raw in raws]


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
    if state is not None and state not in CHECKLIST_STATES:
        raise ValueError(MSG_CHECKLIST_STATE)
    params: dict[str, Any] = {
        "draft": DRAFT,
        "scope": scope,
        "no": False,
        "limit": max(1, min(int(limit), MAX_LIMIT)),
    }
    conds = ["r.scope = :scope", "r.voided = :no"]
    if state is not None:
        conds.append("COALESCE(ws.state, :draft) = :state")
        params["state"] = state
    if discipline is not None:
        conds.append("c.discipline = :discipline")
        params["discipline"] = discipline
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    conds.append(visible)
    params.update(extra)
    where = " AND ".join(conds)
    total = conn.execute(
        text(f"SELECT COUNT(*) AS n {_CHECKLIST_FROM} WHERE {where}"), params
    ).scalar_one()
    raws = conn.execute(
        text(
            f"SELECT {_CHECKLIST_ROW} {_CHECKLIST_FROM} WHERE {where} "
            "ORDER BY r.key, r.id LIMIT :limit"
        ),
        params,
    ).mappings()
    return ChecklistPage(rows=[_checklist_row(raw) for raw in raws], total=int(total))


def checklist_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ChecklistDetail | None:
    """One checklist with its questions; ``None`` when it is absent or in another project."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    statement = text(
        f"SELECT {_CHECKLIST_ROW}, c.questions_json AS questions_json, "
        "sup.key AS supersedes_key, c.published_by AS published_by, "
        "c.published_on AS published_on, c.retired_on AS retired_on, "
        f"r.version AS record_version {_CHECKLIST_FROM} "
        "LEFT JOIN cur_core_record sup ON sup.id = c.supersedes_id "
        f"WHERE r.scope = :scope AND r.key = :key AND r.voided = :no AND {visible}"
    )
    params = {**extra, "draft": DRAFT, "scope": scope, "key": key, "no": False}
    raw = conn.execute(statement, params).mappings().first()
    if raw is None:
        return None
    return ChecklistDetail(
        row=_checklist_row(raw),
        questions=json.loads(str(raw["questions_json"] or "[]")),
        supersedes_key=_text(raw["supersedes_key"]),
        published_by=_text(raw["published_by"]),
        published_on=_text(raw["published_on"]),
        retired_on=_text(raw["retired_on"]),
        record_version=int(raw["record_version"]),
    )


def export_rows(rows: Sequence[InspectionRow], fmt: str) -> str:
    """The rows as ``csv`` (a header, then a line per row, ``\\n`` ends; a cell that starts like a
    formula gets an apostrophe) or ``jsonl`` (one object per line, the same columns, null for
    none). The rows are the caller's page: whatever the viewer could not read is not in it."""
    if fmt not in EXPORT_FORMATS:
        raise ValueError(MSG_FORMAT)
    records = [_export_record(row) for row in rows]
    if fmt == "jsonl":
        return "".join(json.dumps(record) + "\n" for record in records)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for record in records:
        writer.writerow([_csv_cell(value) for value in record.values()])
    return out.getvalue()
