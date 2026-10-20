"""Reads of the legacy module: load runs. Nothing here writes or checks a role."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_legacy.names import OPENED, RUN_TABLE

_COLUMNS = (
    "t.id, t.scope, t.source_system, t.source_table, t.run_number, t.loader, t.source_name, "
    "t.source_sha256, t.source_size, t.row_count, t.column_count, t.extracted_file_id, "
    "t.extracted_sha256, t.profile_file_id, t.profile_sha256, t.bronze_rows, t.mapping_name, "
    "t.mapping_sha256, t.plan_new, t.plan_existing, t.plan_invalid, t.loaded_count, t.record_ids, "
    "t.correlation_id, t.report_file_id, t.report_sha256, t.report_document_id, t.mismatches, "
    f"t.opened_by, t.confidentiality, t.last_error, COALESCE(r.status, '{OPENED}') AS state, "
    "r.created_at"
)
_SQL = f"SELECT {_COLUMNS} FROM {RUN_TABLE} t JOIN cur_core_record r ON r.id = t.id"
MAX_PAGE = 500


@dataclass(frozen=True)
class RunRow:
    id: str
    scope: str
    system: str
    table: str
    number: int
    loader: str
    source_name: str | None
    source_sha256: str | None
    source_size: int | None
    row_count: int | None
    column_count: int | None
    extracted_file_id: str | None
    extracted_sha256: str | None
    profile_file_id: str | None
    profile_sha256: str | None
    bronze_rows: int | None
    mapping_name: str | None
    mapping_sha256: str | None
    plan_new: int | None
    plan_existing: int | None
    plan_invalid: int | None
    loaded_count: int | None
    record_ids: list[str]
    correlation_id: str | None
    report_file_id: str | None
    report_sha256: str | None
    report_document_id: str | None
    mismatches: int | None
    opened_by: str
    confidentiality: str | None
    last_error: str | None
    state: str
    created_at: str

    @property
    def key(self) -> str:
        return f"{self.system}/{self.table}#{self.number}"


def _run(row: Any) -> RunRow:
    m = row._mapping
    ids = m["record_ids"]
    return RunRow(
        id=m["id"],
        scope=m["scope"],
        system=m["source_system"],
        table=m["source_table"],
        number=int(m["run_number"]),
        loader=m["loader"],
        source_name=m["source_name"],
        source_sha256=m["source_sha256"],
        source_size=m["source_size"],
        row_count=m["row_count"],
        column_count=m["column_count"],
        extracted_file_id=m["extracted_file_id"],
        extracted_sha256=m["extracted_sha256"],
        profile_file_id=m["profile_file_id"],
        profile_sha256=m["profile_sha256"],
        bronze_rows=m["bronze_rows"],
        mapping_name=m["mapping_name"],
        mapping_sha256=m["mapping_sha256"],
        plan_new=m["plan_new"],
        plan_existing=m["plan_existing"],
        plan_invalid=m["plan_invalid"],
        loaded_count=m["loaded_count"],
        record_ids=list(json.loads(ids)) if ids else [],
        correlation_id=m["correlation_id"],
        report_file_id=m["report_file_id"],
        report_sha256=m["report_sha256"],
        report_document_id=m["report_document_id"],
        mismatches=m["mismatches"],
        opened_by=m["opened_by"],
        confidentiality=m["confidentiality"],
        last_error=m["last_error"],
        state=m["state"],
        created_at=str(m["created_at"]),
    )


def _visible() -> tuple[str, dict[str, Any]]:
    """The clause that leaves out the runs the current reader may not read (ADR-0016)."""
    return confidentiality.not_hidden("t.id")


def get_run(conn: Connection, run_id: str) -> RunRow | None:
    clause, params = _visible()
    row = conn.execute(
        text(f"{_SQL} WHERE t.id = :id AND {clause}"), {"id": run_id, **params}
    ).first()
    return _run(row) if row is not None else None


def find_run(conn: Connection, scope: str, key: str) -> RunRow | None:
    """A run by ``system/table#n`` in a project."""
    clause, params = _visible()
    head, _, number = key.rpartition("#")
    system, _, table = head.partition("/")
    if not number.isascii() or not number.isdigit() or not system or not table:
        return None
    row = conn.execute(
        text(
            f"{_SQL} WHERE t.scope = :s AND t.source_system = :sys AND t.source_table = :tab "
            f"AND t.run_number = :n AND {clause}"
        ),
        {"s": scope, "sys": system, "tab": table, "n": int(number[:9]), **params},
    ).first()
    return _run(row) if row is not None else None


def list_runs(
    conn: Connection, scope: str, *, state: str | None = None, limit: int = 100
) -> list[RunRow]:
    where = " AND COALESCE(r.status, 'Opened') = :state" if state else ""
    clause, params = _visible()
    rows = conn.execute(
        text(
            f"{_SQL} WHERE t.scope = :s{where} AND {clause} "
            "ORDER BY r.created_at DESC, t.id DESC LIMIT :n"
        ),
        {"s": scope, "state": state, "n": max(1, min(limit, MAX_PAGE)), **params},
    )
    return [_run(r) for r in rows]


def next_number(conn: Connection, scope: str, system: str, table: str) -> int:
    top = conn.execute(
        text(
            f"SELECT MAX(run_number) FROM {RUN_TABLE} WHERE scope = :s AND source_system = :sys "
            "AND source_table = :tab"
        ),
        {"s": scope, "sys": system, "tab": table},
    ).scalar()
    return int(top or 0) + 1
