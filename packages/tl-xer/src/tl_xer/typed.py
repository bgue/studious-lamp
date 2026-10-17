"""From raw tables to the typed snapshot, with the XER document schema checks (P1-I4-T04).

``analyse`` checks what a schedule must hold (supported version, the tables and columns the
snapshot is built from, one project, a data date, unique activity ids, dates and numbers that
parse, references that resolve) and, when nothing is an error, builds the typed rows. It is a pure
function of the raw tables and the options: no clock, no randomness, no I/O.

**What is read.** ``PROJECT`` (data date), ``PROJWBS`` (the tree and each node's path), ``CALENDAR``
(the ones the activities use), ``TASK`` (activities), ``TASKPRED`` (relationships), and where
present ``ACTVTYPE``, ``ACTVCODE``, ``TASKACTV`` (activity codes) and ``UDFTYPE``, ``UDFVALUE``
(user fields of activities). Every other table stays in the raw bundle only (bronze).

**Units.** Durations and floats are hours, as P6 writes them; a day is the activity's calendar
``day_hr`` (8 when it says nothing). Dates are ISO local date-times without a zone,
``YYYY-MM-DDTHH:MM``: P6 does not export a zone, and the schedule is read in its own calendar.

**Severity.** An *error* means the snapshot cannot be built and the file is invalid; a *warning*
is reported and the snapshot is built (relationships to other projects, a missing optional table).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from tl_xer import limits
from tl_xer.problems import Problems
from tl_xer.reader import RawTable, RawXer

Cell = str | float | int | bool | None

#: Major versions of the P6 export that are read. Older ones lack columns the snapshot needs.
SUPPORTED_MAJOR: Final = range(8, 31)
_VERSION = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.\d{1,3})?")
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2})(?::\d{2})?)?")
_NUMBER = re.compile(r"-?\d{1,12}(?:\.\d{1,8})?")

REQUIRED_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "PROJECT": ("proj_id", "proj_short_name", "last_recalc_date"),
    "PROJWBS": ("wbs_id", "proj_id", "wbs_short_name", "wbs_name", "parent_wbs_id"),
    "CALENDAR": ("clndr_id", "clndr_name", "day_hr_cnt"),
    "TASK": (
        "task_id",
        "proj_id",
        "wbs_id",
        "clndr_id",
        "task_type",
        "status_code",
        "task_code",
        "task_name",
        "target_drtn_hr_cnt",
        "remain_drtn_hr_cnt",
        "total_float_hr_cnt",
        "early_start_date",
        "early_end_date",
        "late_start_date",
        "late_end_date",
        "act_start_date",
        "act_end_date",
    ),
    "TASKPRED": ("task_id", "pred_task_id", "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt"),
}
#: Columns that are used when present and make a warning when absent.
USEFUL_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "TASK": ("free_float_hr_cnt", "phys_complete_pct", "complete_pct_type"),
}

TASK_TYPES: Final = {
    "TT_Task": "task",
    "TT_Mile": "start_milestone",
    "TT_FinMile": "finish_milestone",
    "TT_LOE": "level_of_effort",
    "TT_WBS": "wbs_summary",
    "TT_Rsrc": "resource_dependent",
}
STATUSES: Final = {
    "TK_NotStart": "not_started",
    "TK_Active": "in_progress",
    "TK_Complete": "completed",
}
RELATIONSHIP_TYPES: Final = {"PR_FS": "FS", "PR_FF": "FF", "PR_SS": "SS", "PR_SF": "SF"}

# The columns of the typed tables, in order. A row is a tuple in this order (the wire form).
CALENDAR_COLUMNS: Final = (
    "calendar_id",
    "name",
    "day_hr",
    "week_hr",
    "month_hr",
    "year_hr",
    "is_default",
    "seq",
)
WBS_COLUMNS: Final = (
    "wbs_id",
    "parent_wbs_id",
    "short_name",
    "name",
    "path",
    "is_project_node",
    "seq",
)
ACTIVITY_COLUMNS: Final = (
    "activity_id",
    "task_id",
    "name",
    "wbs_id",
    "wbs_path",
    "task_type",
    "status",
    "calendar_id",
    "original_duration_hr",
    "remaining_duration_hr",
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
    "actual_start",
    "actual_finish",
    "target_start",
    "target_finish",
    "total_float_hr",
    "free_float_hr",
    "percent_complete",
    "percent_type",
    "constraint_type",
    "constraint_date",
    "critical",
    "longest_path",
    "seq",
)
RELATIONSHIP_COLUMNS: Final = (
    "pred_activity_id",
    "succ_activity_id",
    "relationship_type",
    "lag_hr",
    "seq",
)
CODE_COLUMNS: Final = ("activity_id", "code_type", "code_value", "code_name", "seq")
UDF_COLUMNS: Final = ("activity_id", "udf_name", "udf_label", "value_type", "value", "seq")

#: The kind of each column, one letter per column in the order above: ``s`` text, ``S`` text or
#: null, ``f`` number, ``F`` number or null, ``b`` boolean, ``i`` integer. The parent checks every
#: cell the child sends against this string, and the database layer builds its inserts from it.
COLUMN_KINDS: Final[dict[str, str]] = {
    "calendars": "ssfFFFbi",
    "wbs": "sSsssbi",
    "activities": "ssssssssFFSSSSSSSSFFfSSSbbi",
    "relationships": "sssfi",
    "codes": "ssssi",
    "udfs": "ssSssi",
}

TABLE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "calendars": CALENDAR_COLUMNS,
    "wbs": WBS_COLUMNS,
    "activities": ACTIVITY_COLUMNS,
    "relationships": RELATIONSHIP_COLUMNS,
    "codes": CODE_COLUMNS,
    "udfs": UDF_COLUMNS,
}
TABLE_LIMITS: Final[dict[str, int]] = {
    "calendars": limits.MAX_CALENDARS,
    "wbs": limits.MAX_WBS,
    "activities": limits.MAX_ACTIVITIES,
    "relationships": limits.MAX_RELATIONSHIPS,
    "codes": limits.MAX_CODES,
    "udfs": limits.MAX_UDFS,
}
PROJECT_KEYS: Final = (
    "proj_id",
    "short_name",
    "data_date",
    "plan_start",
    "plan_finish",
    "export_version",
    "export_date",
    "other_projects",
)


@dataclass(frozen=True)
class Options:
    """What the caller says about the file: the P6 project to read when the file holds several."""

    project: str | None = None


@dataclass
class Snapshot:
    """The typed rows of one P6 project, ready to store."""

    project: dict[str, str | int | None]
    tables: dict[str, list[tuple[Cell, ...]]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


def clean_text(value: str) -> str:
    return value.strip()


def parse_date(value: str) -> str | None:
    """``YYYY-MM-DDTHH:MM`` for a P6 date, ``None`` for an empty one; ``ValueError`` otherwise."""
    text = value.strip()
    if not text:
        return None
    found = _DATE.fullmatch(text)
    if found is None:
        raise ValueError("not a date")
    year, month, day = (int(found.group(i)) for i in (1, 2, 3))
    hour, minute = int(found.group(4) or 0), int(found.group(5) or 0)
    stamp = datetime(year, month, day, hour, minute)  # raises ValueError for 2026-02-30
    return stamp.strftime("%Y-%m-%dT%H:%M")


def parse_number(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    if _NUMBER.fullmatch(text) is None:
        raise ValueError("not a number")
    return float(text)


class _View:
    """A raw table with its column positions."""

    def __init__(self, table: RawTable) -> None:
        self.table = table
        self.pos = table.index()
        self.rows = table.rows

    def has(self, column: str) -> bool:
        return column in self.pos

    def get(self, row: tuple[str, ...], column: str) -> str:
        i = self.pos.get(column)
        return "" if i is None else row[i]


def _fail_names(names: list[str]) -> str:
    return ", ".join(names[: limits.MAX_PROJECTS_LISTED])


def _check_version(raw: RawXer, problems: Problems) -> str | None:
    version = raw.header[0] if raw.header else ""
    found = _VERSION.fullmatch(version)
    if found is None:
        problems.error("bad_version", "the ERMHDR line does not state a P6 version")
        return None
    if int(found.group(1)) not in SUPPORTED_MAJOR:
        problems.error(
            "unsupported_version",
            f"P6 version {version} is not supported; export from version "
            f"{SUPPORTED_MAJOR.start} or later",
        )
    return version


def _check_columns(raw: RawXer, problems: Problems) -> dict[str, _View] | None:
    views: dict[str, _View] = {}
    failed = False
    for name, columns in REQUIRED_COLUMNS.items():
        table = raw.table(name)
        if table is None:
            problems.error("missing_table", f"the table {name} is missing", table=name)
            failed = True
            continue
        view = _View(table)
        views[name] = view
        for column in columns:
            if not view.has(column):
                problems.error(
                    "missing_column",
                    f"the table {name} lacks the column {column}",
                    table=name,
                    field=column,
                )
                failed = True
        for column in USEFUL_COLUMNS.get(name, ()):
            if not view.has(column):
                problems.warn(
                    "missing_optional_column",
                    f"the table {name} lacks the column {column}; it is left empty",
                    table=name,
                    field=column,
                )
    return None if failed else views


def _select_project(
    projects: _View, options: Options, problems: Problems
) -> tuple[tuple[str, ...], int] | None:
    """The PROJECT row to read and the number of other projects in the file."""
    rows = projects.rows
    names = [clean_text(projects.get(r, "proj_short_name")) for r in rows]
    if not rows:
        problems.error("no_project", "the file holds no project", table="PROJECT")
        return None
    wanted = options.project
    if wanted is not None:
        matches = [i for i, name in enumerate(names) if name == wanted]
        if not matches:
            problems.error(
                "project_not_found",
                f"the file has no project named {wanted[: limits.MAX_ID_CHARS]!r}; it holds: "
                + _fail_names(names),
                table="PROJECT",
            )
            return None
        if len(matches) > 1:
            problems.error(
                "duplicate_project", "two projects share the chosen name", table="PROJECT"
            )
            return None
        return rows[matches[0]], len(rows) - 1
    if len(rows) > 1:
        problems.error(
            "multi_project",
            f"the file holds {len(rows)} projects ({_fail_names(names)}); name the one to read",
            table="PROJECT",
        )
        return None
    return next(iter(rows)), 0


def _wbs_rows(
    view: _View, project_id: str, problems: Problems
) -> tuple[list[tuple[Cell, ...]], dict[str, str]]:
    nodes: dict[str, tuple[str, str, str, str]] = {}  # id -> parent, short, name, node flag
    order: list[str] = []
    for n, row in enumerate(view.rows, 1):
        if view.get(row, "proj_id") != project_id:
            continue
        wbs_id = clean_text(view.get(row, "wbs_id"))
        if not wbs_id or wbs_id in nodes:
            problems.error(
                "bad_wbs_id", "a WBS node has no id or repeats one", table="PROJWBS", row=n
            )
            continue
        short = clean_text(view.get(row, "wbs_short_name"))
        name = clean_text(view.get(row, "wbs_name"))
        if len(short) > limits.MAX_ID_CHARS or len(name) > limits.MAX_TEXT_CHARS:
            problems.error("text_too_long", "a WBS name is too long", table="PROJWBS", row=n)
            continue
        nodes[wbs_id] = (
            clean_text(view.get(row, "parent_wbs_id")),
            short,
            name,
            view.get(row, "proj_node_flag").strip(),
        )
        order.append(wbs_id)
        if len(order) > limits.MAX_WBS:
            problems.error("too_many_wbs", "the project has more WBS nodes than the limit")
            return [], {}
    paths: dict[str, str] = {}
    depths: dict[str, int] = {}
    failure: str | None = None
    for wbs_id in order:
        chain: list[str] = []
        cursor: str | None = wbs_id
        while cursor and cursor in nodes and cursor not in paths:
            if cursor in chain:
                failure = "wbs_loop"
                break
            if len(chain) > limits.MAX_WBS_DEPTH:
                failure = "wbs_too_deep"
                break
            chain.append(cursor)
            cursor = nodes[cursor][0] or None
        if failure:
            break
        base = paths.get(cursor, "") if cursor else ""
        depth = depths.get(cursor, 0) if cursor else 0
        for node in reversed(chain):
            base = f"{base} > {nodes[node][1]}" if base else nodes[node][1]
            depth += 1
            if depth > limits.MAX_WBS_DEPTH or len(base) > limits.MAX_TEXT_CHARS:
                failure = "wbs_too_deep"
                break
            paths[node] = base
            depths[node] = depth
        if failure:
            break
    if failure == "wbs_loop":
        problems.error("wbs_loop", "the WBS tree loops", table="PROJWBS")
        return [], {}
    if failure:
        problems.error(
            "wbs_too_deep",
            "the WBS tree is deeper than the limit or has a path longer than the limit",
            table="PROJWBS",
        )
        return [], {}
    rows: list[tuple[Cell, ...]] = []
    for seq, wbs_id in enumerate(order, 1):
        parent, short, name, flag = nodes[wbs_id]
        rows.append((wbs_id, parent or None, short, name, paths[wbs_id], flag == "Y", seq))
    return rows, paths


def _calendar_rows(
    view: _View, used: set[str], default_id: str, problems: Problems
) -> list[tuple[Cell, ...]]:
    found: dict[str, tuple[Cell, ...]] = {}
    for n, row in enumerate(view.rows, 1):
        calendar_id = clean_text(view.get(row, "clndr_id"))
        if calendar_id not in used and calendar_id != default_id:
            continue
        try:
            numbers = [
                parse_number(view.get(row, c))
                for c in ("day_hr_cnt", "week_hr_cnt", "month_hr_cnt", "year_hr_cnt")
            ]
        except ValueError:
            problems.error(
                "bad_number", "a calendar hour count is not a number", table="CALENDAR", row=n
            )
            continue
        name = clean_text(view.get(row, "clndr_name"))
        if len(name) > limits.MAX_TEXT_CHARS:
            problems.error("text_too_long", "a calendar name is too long", table="CALENDAR", row=n)
            continue
        if numbers[0] is None or numbers[0] <= 0:
            problems.error("bad_number", "a calendar has no hours per day", table="CALENDAR", row=n)
            continue
        found.setdefault(
            calendar_id,
            (calendar_id, name, *numbers, calendar_id == default_id, len(found) + 1),
        )
    return list(found.values())


def _percent(
    kind: str,
    physical: float | None,
    original: float | None,
    remaining: float | None,
    done: float | None,
    planned: float | None,
    status: str,
) -> float:
    if status == "completed":
        return 100.0
    if status == "not_started":
        return 0.0
    if kind == "CP_Phys" and physical is not None:
        return round(min(max(physical, 0.0), 100.0), 2)
    if kind == "CP_Units" and done is not None and planned:
        return round(min(max(done / planned * 100.0, 0.0), 100.0), 2)
    if original and remaining is not None:
        return round(min(max((original - remaining) / original * 100.0, 0.0), 100.0), 2)
    return 0.0


@dataclass
class _Tasks:
    rows: list[tuple[Cell, ...]]
    by_task_id: dict[str, str]  # task_id -> activity_id
    calendars: set[str]
    rejected: set[str]  # task ids of rows that were reported; their relationships are not


def _tasks(
    view: _View, project_id: str, paths: dict[str, str], calendar_ids: set[str], problems: Problems
) -> _Tasks | None:
    rows: list[tuple[Cell, ...]] = []
    by_task_id: dict[str, str] = {}
    seen_codes: dict[str, int] = {}
    used_calendars: set[str] = set()
    rejected: set[str] = set()
    date_columns = (
        ("early_start", "early_start_date"),
        ("early_finish", "early_end_date"),
        ("late_start", "late_start_date"),
        ("late_finish", "late_end_date"),
        ("actual_start", "act_start_date"),
        ("actual_finish", "act_end_date"),
        ("target_start", "target_start_date"),
        ("target_finish", "target_end_date"),
        ("constraint_date", "cstr_date"),
    )
    for n, row in enumerate(view.rows, 1):
        if view.get(row, "proj_id") != project_id:
            continue
        if len(rows) >= limits.MAX_ACTIVITIES:
            problems.error("too_many_activities", "the project has more activities than the limit")
            return None
        errors_before = problems.errors
        task_id = clean_text(view.get(row, "task_id"))
        code = clean_text(view.get(row, "task_code"))
        name = clean_text(view.get(row, "task_name"))
        if not task_id or task_id in by_task_id:
            problems.error(
                "bad_task_id", "an activity has no task id or repeats one", table="TASK", row=n
            )
            continue
        rejected.add(task_id)  # until the row is kept: one error is enough for its relationships
        if not code or len(code) > limits.MAX_ID_CHARS:
            problems.error(
                "bad_activity_id",
                "an activity id is empty or longer than the limit",
                table="TASK",
                row=n,
                field="task_code",
            )
            continue
        if code in seen_codes:
            problems.error(
                "duplicate_activity_id",
                f"activity id {code} appears twice (rows {seen_codes[code]} and {n})",
                table="TASK",
                row=n,
                field="task_code",
            )
            continue
        seen_codes[code] = n
        if len(name) > limits.MAX_TEXT_CHARS:
            problems.error(
                "text_too_long",
                "an activity name is too long",
                table="TASK",
                row=n,
                field="task_name",
            )
        wbs_id = clean_text(view.get(row, "wbs_id"))
        if wbs_id not in paths:
            problems.error(
                "dangling_wbs",
                f"activity {code} names a WBS node the project does not have",
                table="TASK",
                row=n,
                field="wbs_id",
            )
        calendar_id = clean_text(view.get(row, "clndr_id"))
        if calendar_id not in calendar_ids:
            problems.error(
                "dangling_calendar",
                f"activity {code} names a calendar the file does not have",
                table="TASK",
                row=n,
                field="clndr_id",
            )
        task_type = TASK_TYPES.get(view.get(row, "task_type").strip())
        if task_type is None:
            problems.error(
                "unknown_task_type",
                f"activity {code} has an unknown type",
                table="TASK",
                row=n,
                field="task_type",
            )
        status = STATUSES.get(view.get(row, "status_code").strip())
        if status is None:
            problems.error(
                "unknown_status",
                f"activity {code} has an unknown status",
                table="TASK",
                row=n,
                field="status_code",
            )
        numbers: dict[str, float | None] = {}
        for key, column in (
            ("original", "target_drtn_hr_cnt"),
            ("remaining", "remain_drtn_hr_cnt"),
            ("total_float", "total_float_hr_cnt"),
            ("free_float", "free_float_hr_cnt"),
            ("physical", "phys_complete_pct"),
            ("done", "act_work_qty"),
            ("planned", "target_work_qty"),
        ):
            try:
                numbers[key] = parse_number(view.get(row, column))
            except ValueError:
                numbers[key] = None
                problems.error(
                    "bad_number",
                    f"activity {code}: {column} is not a number",
                    table="TASK",
                    row=n,
                    field=column,
                )
        dates: dict[str, str | None] = {}
        for key, column in date_columns:
            try:
                dates[key] = parse_date(view.get(row, column))
            except ValueError:
                dates[key] = None
                problems.error(
                    "bad_date",
                    f"activity {code}: {column} is not a date written YYYY-MM-DD HH:MM",
                    table="TASK",
                    row=n,
                    field=column,
                )
        if problems.errors > errors_before or task_type is None or status is None:
            continue
        percent_type = view.get(row, "complete_pct_type").strip()
        total_float = numbers["total_float"]
        rejected.discard(task_id)
        by_task_id[task_id] = code
        used_calendars.add(calendar_id)
        rows.append(
            (
                code,
                task_id,
                name,
                wbs_id,
                paths[wbs_id],
                task_type,
                status,
                calendar_id,
                numbers["original"],
                numbers["remaining"],
                dates["early_start"],
                dates["early_finish"],
                dates["late_start"],
                dates["late_finish"],
                dates["actual_start"],
                dates["actual_finish"],
                dates["target_start"],
                dates["target_finish"],
                total_float,
                numbers["free_float"],
                _percent(
                    percent_type,
                    numbers["physical"],
                    numbers["original"],
                    numbers["remaining"],
                    numbers["done"],
                    numbers["planned"],
                    status,
                ),
                percent_type[:20] or None,
                view.get(row, "cstr_type").strip()[:20] or None,
                dates["constraint_date"],
                total_float is not None and total_float <= 0 and status != "completed",
                view.get(row, "driving_path_flag").strip() == "Y",
                len(rows) + 1,
            )
        )
    return _Tasks(rows, by_task_id, used_calendars, rejected)


def _relationships(
    view: _View, project_id: str, tasks: _Tasks, problems: Problems
) -> list[tuple[Cell, ...]]:
    rows: list[tuple[Cell, ...]] = []
    external = 0
    for n, row in enumerate(view.rows, 1):
        if view.get(row, "proj_id").strip() != project_id:
            continue
        successor = tasks.by_task_id.get(clean_text(view.get(row, "task_id")))
        if successor is None:
            continue  # the successor belongs to a task that was already reported or is not ours
        if view.get(row, "pred_proj_id").strip() != project_id:
            external += 1
            continue
        pred_id = clean_text(view.get(row, "pred_task_id"))
        if pred_id in tasks.rejected:
            continue  # the activity itself was reported
        predecessor = tasks.by_task_id.get(pred_id)
        kind = RELATIONSHIP_TYPES.get(view.get(row, "pred_type").strip())
        if predecessor is None or kind is None:
            problems.error(
                "bad_relationship",
                f"a relationship of {successor} names an unknown predecessor or type",
                table="TASKPRED",
                row=n,
            )
            continue
        try:
            lag = parse_number(view.get(row, "lag_hr_cnt"))
        except ValueError:
            problems.error(
                "bad_number",
                "a relationship lag is not a number",
                table="TASKPRED",
                row=n,
                field="lag_hr_cnt",
            )
            continue
        if len(rows) >= limits.MAX_RELATIONSHIPS:
            problems.error(
                "too_many_relationships", "the project has more relationships than the limit"
            )
            return []
        rows.append((predecessor, successor, kind, lag or 0.0, len(rows) + 1))
    if external:
        problems.warn(
            "external_relationships",
            f"{external} relationship(s) to activities of other projects were left out",
            table="TASKPRED",
        )
    return rows


def _codes(raw: RawXer, tasks: _Tasks, problems: Problems) -> list[tuple[Cell, ...]]:
    types, codes, links = raw.table("ACTVTYPE"), raw.table("ACTVCODE"), raw.table("TASKACTV")
    if types is None or codes is None or links is None:
        if any(t is not None for t in (types, codes, links)):
            problems.warn(
                "codes_incomplete",
                "activity codes need ACTVTYPE, ACTVCODE and TASKACTV; they are left out",
            )
        return []
    tv, cv, lv = _View(types), _View(codes), _View(links)
    needed = (
        (tv, ("actv_code_type_id", "actv_code_type")),
        (cv, ("actv_code_id", "actv_code_type_id", "short_name", "actv_code_name")),
        (lv, ("task_id", "actv_code_type_id", "actv_code_id")),
    )
    for view, columns in needed:
        if not all(view.has(c) for c in columns):
            problems.warn(
                "codes_incomplete",
                f"{view.table.name} lacks columns; activity codes are left out",
                table=view.table.name,
            )
            return []
    type_names = {
        clean_text(tv.get(r, "actv_code_type_id")): clean_text(tv.get(r, "actv_code_type"))
        for r in tv.rows
    }
    code_values = {
        clean_text(cv.get(r, "actv_code_id")): (
            clean_text(cv.get(r, "short_name")),
            clean_text(cv.get(r, "actv_code_name")),
        )
        for r in cv.rows
    }
    rows: list[tuple[Cell, ...]] = []
    for n, row in enumerate(lv.rows, 1):
        activity = tasks.by_task_id.get(clean_text(lv.get(row, "task_id")))
        if activity is None:
            continue
        type_name = type_names.get(clean_text(lv.get(row, "actv_code_type_id")))
        value = code_values.get(clean_text(lv.get(row, "actv_code_id")))
        if type_name is None or value is None:
            problems.warn(
                "dangling_code",
                "an activity code names a type or value the file lacks",
                table="TASKACTV",
                row=n,
            )
            continue
        if (
            len(type_name) > limits.MAX_ID_CHARS
            or len(value[0]) > limits.MAX_ID_CHARS
            or len(value[1]) > limits.MAX_TEXT_CHARS
        ):
            problems.error("text_too_long", "an activity code is too long", table="TASKACTV", row=n)
            continue
        if len(rows) >= limits.MAX_CODES:
            problems.error("too_many_codes", "the project has more activity codes than the limit")
            return []
        rows.append((activity, type_name, value[0], value[1], len(rows) + 1))
    return rows


def _udf_value(view: _View, row: tuple[str, ...]) -> tuple[str, str] | None:
    """The kind and text of the first filled value column of a ``UDFVALUE`` row."""
    for kind, column in (
        ("text", "udf_text"),
        ("number", "udf_number"),
        ("date", "udf_date"),
        ("code", "udf_code_id"),
    ):
        value = view.get(row, column).strip()
        if value:
            return kind, value
    return None


def _udfs(raw: RawXer, tasks: _Tasks, problems: Problems) -> list[tuple[Cell, ...]]:
    types, values = raw.table("UDFTYPE"), raw.table("UDFVALUE")
    if types is None or values is None:
        if types is not None or values is not None:
            problems.warn(
                "udfs_incomplete", "user fields need UDFTYPE and UDFVALUE; they are left out"
            )
        return []
    tv, vv = _View(types), _View(values)
    if not (
        all(tv.has(c) for c in ("udf_type_id", "table_name", "udf_type_name"))
        and all(vv.has(c) for c in ("udf_type_id", "fk_id"))
    ):
        problems.warn(
            "udfs_incomplete", "UDFTYPE or UDFVALUE lacks columns; user fields are left out"
        )
        return []
    names = {
        clean_text(tv.get(r, "udf_type_id")): (
            clean_text(tv.get(r, "udf_type_name")),
            clean_text(tv.get(r, "udf_type_label")),
        )
        for r in tv.rows
        if tv.get(r, "table_name").strip() == "TASK"
    }
    rows: list[tuple[Cell, ...]] = []
    for n, row in enumerate(vv.rows, 1):
        activity = tasks.by_task_id.get(clean_text(vv.get(row, "fk_id")))
        spec = names.get(clean_text(vv.get(row, "udf_type_id")))
        if activity is None or spec is None:
            continue
        found = _udf_value(vv, row)
        if found is None:
            continue
        kind, value = found
        if (
            len(value) > limits.MAX_TEXT_CHARS
            or len(spec[0]) > limits.MAX_ID_CHARS
            or len(spec[1]) > limits.MAX_TEXT_CHARS
        ):
            problems.error("text_too_long", "a user field is too long", table="UDFVALUE", row=n)
            continue
        if len(rows) >= limits.MAX_UDFS:
            problems.error("too_many_udfs", "the project has more user field values than the limit")
            return []
        rows.append((activity, spec[0], spec[1] or None, kind, value, len(rows) + 1))
    return rows


def analyse(raw: RawXer, options: Options, problems: Problems) -> Snapshot | None:
    """Validate ``raw`` and build the typed snapshot; ``None`` when there is any error."""
    version = _check_version(raw, problems)
    views = _check_columns(raw, problems)
    if views is None or problems.errors:
        return None
    chosen = _select_project(views["PROJECT"], options, problems)
    if chosen is None:
        return None
    project_row, others = chosen
    pv = views["PROJECT"]
    project_id = clean_text(pv.get(project_row, "proj_id"))
    try:
        data_date = parse_date(pv.get(project_row, "last_recalc_date"))
        plan_start = parse_date(pv.get(project_row, "plan_start_date"))
        plan_finish = parse_date(pv.get(project_row, "scd_end_date"))
    except ValueError:
        problems.error(
            "bad_date", "a project date is not written YYYY-MM-DD HH:MM", table="PROJECT"
        )
        return None
    if data_date is None:
        problems.error(
            "no_data_date",
            "the project has no data date (last_recalc_date)",
            table="PROJECT",
            field="last_recalc_date",
        )
        return None
    short_name = clean_text(pv.get(project_row, "proj_short_name"))
    if not short_name or len(short_name) > limits.MAX_ID_CHARS:
        problems.error(
            "bad_project_name", "the project short name is empty or too long", table="PROJECT"
        )
        return None
    wbs_rows, paths = _wbs_rows(views["PROJWBS"], project_id, problems)
    if not paths:
        if not problems.errors:
            problems.error("no_wbs", "the project has no WBS nodes", table="PROJWBS")
        return None
    calendar_ids = {
        clean_text(views["CALENDAR"].get(r, "clndr_id")) for r in views["CALENDAR"].rows
    }
    tasks = _tasks(views["TASK"], project_id, paths, calendar_ids, problems)
    if tasks is None:
        return None
    if not tasks.rows and not problems.errors:
        problems.error("no_activities", "the project has no activities", table="TASK")
        return None
    relationships = _relationships(views["TASKPRED"], project_id, tasks, problems)
    default_calendar = clean_text(pv.get(project_row, "clndr_id"))
    calendars = _calendar_rows(views["CALENDAR"], tasks.calendars, default_calendar, problems)
    codes = _codes(raw, tasks, problems)
    udfs = _udfs(raw, tasks, problems)
    if problems.errors:
        return None
    header = raw.header
    snapshot = Snapshot(
        project={
            "proj_id": project_id,
            "short_name": short_name,
            "data_date": data_date,
            "plan_start": plan_start,
            "plan_finish": plan_finish,
            "export_version": version,
            "export_date": header[1][:10] if len(header) > 1 else None,
            "other_projects": others,
        }
    )
    snapshot.tables = {
        "calendars": calendars,
        "wbs": wbs_rows,
        "activities": tasks.rows,
        "relationships": relationships,
        "codes": codes,
        "udfs": udfs,
    }
    return snapshot


def table_dicts(snapshot: Snapshot, name: str) -> list[dict[str, Cell]]:
    """The rows of one typed table as dictionaries (for readers that want names)."""
    columns = TABLE_COLUMNS[name]
    return [dict(zip(columns, row, strict=True)) for row in snapshot.tables[name]]


def as_json_value(snapshot: Snapshot) -> dict[str, Any]:
    """The snapshot as plain JSON values: the project, and per table its columns and rows."""
    return {
        "project": snapshot.project,
        "tables": {
            name: {"columns": list(TABLE_COLUMNS[name]), "rows": [list(r) for r in rows]}
            for name, rows in snapshot.tables.items()
        },
    }
