"""Reads of the cost module: codes, snapshots and the history of a code's figures.

Rows are frozen dataclasses joined with ``cur_core_record`` (the title, the voided flag). Nothing
here writes, and nothing here checks a role: the entry points do (reads need ``document.read``).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, text

from tl_mod_cost.names import (
    COST_CODE_TABLE,
    COST_SNAPSHOT_TABLE,
    MEASURE_COLUMNS,
    SNAPSHOT_VALUE_TABLE,
)

_MEASURES = ", ".join(f"t.{c}" for c in MEASURE_COLUMNS)
_CODE_SQL = (
    "SELECT t.id, t.scope, t.code, t.parent_code, t.level, t.uom, t.is_active, t.snapshot_id, "
    f"t.period, t.as_of, {_MEASURES}, r.title FROM {COST_CODE_TABLE} t "
    "JOIN cur_core_record r ON r.id = t.id WHERE t.scope = :scope"
)
_SNAPSHOT_SQL = (
    "SELECT t.id, t.scope, t.period, t.revision, t.as_of, t.currency, t.source_name, "
    "t.source_sha256, t.row_count, t.new_code_count, t.revised_code_count, r.created_at "
    f"FROM {COST_SNAPSHOT_TABLE} t JOIN cur_core_record r ON r.id = t.id WHERE t.scope = :scope"
)


@dataclass(frozen=True)
class CostCodeRow:
    id: str
    scope: str
    code: str
    title: str
    parent_code: str | None
    level: int
    uom: str | None
    is_active: bool
    snapshot_id: str | None
    period: str | None
    as_of: str | None
    figures: dict[str, float | None]


@dataclass(frozen=True)
class CostSnapshotRow:
    id: str
    scope: str
    period: str
    revision: int
    as_of: str
    currency: str | None
    source_name: str | None
    source_sha256: str | None
    row_count: int
    new_code_count: int
    revised_code_count: int
    created_at: str


@dataclass(frozen=True)
class ValueRow:
    """What one snapshot said about one code."""

    snapshot_id: str
    period: str
    revision: int
    as_of: str
    figures: dict[str, float | None]


def _figures(row: object) -> dict[str, float | None]:
    return {c: (None if (v := getattr(row, c)) is None else float(v)) for c in MEASURE_COLUMNS}


def _code(r: object) -> CostCodeRow:
    g = lambda name: getattr(r, name)  # noqa: E731 - a row accessor
    return CostCodeRow(
        id=str(g("id")),
        scope=str(g("scope")),
        code=str(g("code")),
        title=str(g("title")),
        parent_code=None if g("parent_code") is None else str(g("parent_code")),
        level=int(g("level")),
        uom=None if g("uom") is None else str(g("uom")),
        is_active=bool(g("is_active")),
        snapshot_id=None if g("snapshot_id") is None else str(g("snapshot_id")),
        period=None if g("period") is None else str(g("period")),
        as_of=None if g("as_of") is None else str(g("as_of")),
        figures=_figures(r),
    )


def list_cost_codes(conn: Connection, scope: str) -> list[CostCodeRow]:
    """Every cost code of a scope, ordered by code."""
    found = conn.execute(text(_CODE_SQL + " ORDER BY t.code"), {"scope": scope})
    return [_code(r) for r in found]


def get_cost_code(conn: Connection, scope: str, code: str) -> CostCodeRow | None:
    found = conn.execute(
        text(_CODE_SQL + " AND t.code = :code"), {"scope": scope, "code": code}
    ).first()
    return None if found is None else _code(found)


def list_snapshots(conn: Connection, scope: str) -> list[CostSnapshotRow]:
    """Every snapshot of a scope, newest period and revision first."""
    found = conn.execute(
        text(_SNAPSHOT_SQL + " ORDER BY t.period DESC, t.revision DESC"), {"scope": scope}
    )
    return [
        CostSnapshotRow(
            id=str(r.id),
            scope=str(r.scope),
            period=str(r.period),
            revision=int(r.revision),
            as_of=str(r.as_of),
            currency=None if r.currency is None else str(r.currency),
            source_name=None if r.source_name is None else str(r.source_name),
            source_sha256=None if r.source_sha256 is None else str(r.source_sha256),
            row_count=int(r.row_count),
            new_code_count=int(r.new_code_count),
            revised_code_count=int(r.revised_code_count),
            created_at=str(r.created_at),
        )
        for r in found
    ]


def code_history(conn: Connection, cost_code_id: str) -> list[ValueRow]:
    """The figures every snapshot stated for a code, oldest as-of date first."""
    columns = ", ".join(MEASURE_COLUMNS)
    found = conn.execute(
        text(
            f"SELECT snapshot_id, period, revision, as_of, {columns} FROM {SNAPSHOT_VALUE_TABLE} "
            "WHERE cost_code_id = :id ORDER BY as_of, period, revision"
        ),
        {"id": cost_code_id},
    )
    return [
        ValueRow(
            snapshot_id=str(r.snapshot_id),
            period=str(r.period),
            revision=int(r.revision),
            as_of=str(r.as_of),
            figures=_figures(r),
        )
        for r in found
    ]
