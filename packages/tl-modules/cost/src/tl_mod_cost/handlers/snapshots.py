"""``ImportCostSnapshot``: one period of figures from the cost system, as one correlated import.

The command is one unit of work with one correlation id: the snapshot record, the cost codes it
names for the first time (parents before children), a ``Record.Updated`` and ``CostCode.Revised``
for a code whose description or unit changed, and one ``CostCode.MeasuresRecorded`` for every code
in the file. Any refusal leaves nothing behind. The file is read by ``imports.reader`` and checked
by ``imports.plan`` first; the apply runs the same plan, so a preview cannot disagree with it.

Who may run it: the admin (the cost figures are money; ADR-0015). A preview (the plan) writes
nothing and is open to any signed-in person.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_cost.common import append, correlated, require_project
from tl_mod_cost.errors import CostImportRefusedError, InvalidCostSnapshotError
from tl_mod_cost.imports.model import CostRow
from tl_mod_cost.imports.plan import plan_import
from tl_mod_cost.limits import MAX_ROWS, MAX_SOURCE_NAME
from tl_mod_cost.names import (
    CODE_DEFINED,
    CODE_REVISED,
    COST_CODE,
    COST_SNAPSHOT,
    COST_SNAPSHOT_TABLE,
    MEASURE_COLUMNS,
    MEASURES_RECORDED,
    SNAPSHOT_DEFINED,
)

_PERIOD = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CURRENCY = re.compile(r"[A-Z]{3}")
_REVISION_SQL = text(
    f"SELECT MAX(revision) FROM {COST_SNAPSHOT_TABLE} WHERE scope = :scope AND period = :period"
)
MAX_YEARS_BACK = 50


class ImportCostSnapshot(Command):
    """Import one period of cost figures into a project."""

    model_config = ConfigDict(extra="forbid")

    period: str = Field(min_length=7, max_length=7)  # YYYY-MM
    as_of: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD, not in the future
    currency: str | None = Field(default=None, max_length=3)
    source_name: str | None = Field(default=None, max_length=MAX_SOURCE_NAME)
    source_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    rows: list[CostRow] = Field(min_length=1, max_length=MAX_ROWS)

    @field_validator("period")
    @classmethod
    def _period(cls, value: str) -> str:
        if _PERIOD.fullmatch(value) is None:
            raise ValueError("period must be written YYYY-MM")
        return value

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        if value is not None and _CURRENCY.fullmatch(value) is None:
            raise ValueError("currency must be an ISO 4217 code such as USD")
        return value

    @field_validator("source_sha256")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("source_sha256 must be 64 lower-case hex digits")
        return value

    @field_validator("source_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def check_as_of(value: str) -> str:
    """``value`` when it is a calendar date, not in the future and not more than 50 years back."""
    if _DATE.fullmatch(value) is None:
        raise InvalidCostSnapshotError("as_of must be written YYYY-MM-DD")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidCostSnapshotError(f"as_of {value} is not a calendar date") from exc
    today = utcnow().date()
    if day > today:
        raise InvalidCostSnapshotError(f"as_of {value} is in the future; today is {today}")
    if (today - day).days > 366 * MAX_YEARS_BACK:
        raise InvalidCostSnapshotError(f"as_of {value} is more than {MAX_YEARS_BACK} years back")
    return value


def _measures(row: CostRow) -> dict[str, float | None]:
    return {c: row.figures.get(c) for c in MEASURE_COLUMNS}


def handle_import_cost_snapshot(uow: UnitOfWork, cmd: ImportCostSnapshot) -> CommandResult:
    """Create the snapshot and its codes and record every code's figures.

    Raises ``CostScopeError``, ``InvalidCostSnapshotError`` (a date in the future) and
    ``CostImportRefusedError`` (``issues`` lists what is wrong with the rows).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    as_of = check_as_of(cmd.as_of)
    conn = uow.conn()
    plan = plan_import(conn, cmd.scope, cmd.rows)
    if plan.issues:
        raise CostImportRefusedError(
            f"the cost snapshot cannot be imported ({len(plan.issues)} problem(s))",
            list(plan.issues),
        )
    last = conn.execute(_REVISION_SQL, {"scope": cmd.scope, "period": cmd.period}).scalar_one()
    revision = (int(last) if last is not None else 0) + 1
    key = f"{cmd.period}@{revision}"
    made = create_module_record(
        uow,
        cmd,
        record_type=COST_SNAPSHOT,
        title=f"Cost snapshot {cmd.period} revision {revision}",
        key=key,
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=SNAPSHOT_DEFINED,
                payload={
                    "period": cmd.period,
                    "revision": revision,
                    "as_of": as_of,
                    "currency": cmd.currency,
                    "source_name": cmd.source_name,
                    "source_sha256": cmd.source_sha256,
                    "row_count": len(plan.codes),
                    "new_code_count": len(plan.new),
                    "revised_code_count": len(plan.revised),
                },
            )
        ],
    )
    snapshot_id = made.stream_id
    events = list(made.events)

    def recorded(row: CostRow) -> NewEvent:
        return NewEvent(
            event_type=MEASURES_RECORDED,
            payload={
                "snapshot_id": snapshot_id,
                "period": cmd.period,
                "revision": revision,
                "as_of": as_of,
                "measures": _measures(row),
            },
        )

    for planned in plan.codes:
        row = planned.row
        if planned.existing is None:
            created = create_module_record(
                uow,
                cmd,
                record_type=COST_CODE,
                title=row.description or row.code,
                key=row.code,
                extra_events=[
                    NewEvent(
                        event_type=CODE_DEFINED,
                        payload={
                            "code": row.code,
                            "parent_code": row.parent_code,
                            "level": planned.level,
                            "uom": row.uom,
                        },
                    ),
                    recorded(row),
                ],
            )
            events.extend(created.events)
            continue
        stream = planned.existing.id
        more: list[NewEvent] = []
        if "title" in planned.changes:
            more.append(
                NewEvent(
                    event_type="Record.Updated",
                    payload={"changes": {"title": planned.changes["title"]}},
                )
            )
        if planned.changes:
            more.append(
                NewEvent(
                    event_type=CODE_REVISED,
                    payload={"snapshot_id": snapshot_id, "changes": planned.changes},
                )
            )
        more.append(recorded(row))
        events.extend(append(uow, cmd, stream, COST_CODE, more).events)
    return CommandResult(stream_id=snapshot_id, key=key, version=made.version, events=events)
