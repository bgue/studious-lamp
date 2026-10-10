"""Query plans on SQLite: the indexes of the P0-I8 performance pass are the ones the planner picks.

Without them the default page, a sort by key, created_at or updated_at, and a filter on a pset
value read and sorted the whole table (P0-I8-perf: 40 to 400 ms at 100k records). The plans are
checked on a small database; the planner's choice for these shapes does not depend on the size.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.db import create_schema
from tl_core.query import QuerySpec, parse
from tl_core.query.compiler import compile_query

SCOPE = "project:P123"


@pytest.fixture
def con(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "plans.db"
    create_schema(path)
    connection = sqlite3.connect(path)
    connection.executemany(
        "INSERT INTO cur_core_record (id, key, type, scope, title, status, psets_json, voided, "
        "version, last_seq, created_at, updated_at) VALUES (?, ?, 'core.Record', ?, 't', NULL, "
        "'{}', 0, 1, 1, ?, ?)",
        [
            (f"id{i:03d}", f"K-{i:03d}", SCOPE, f"2026-01-01T00:{i:02d}", f"2026-01-02T00:{i:02d}")
            for i in range(60)
        ],
    )
    connection.executemany(
        "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, "
        "value_type, value_text, last_seq, updated_at) VALUES (?, ?, 'psets.v.m', 'v', 'm', "
        "'standard', 'string', ?, 1, 'x')",
        [(f"id{i:03d}", SCOPE, "SS" if i % 5 == 0 else "CS") for i in range(60)],
    )
    connection.execute("ANALYZE")
    yield connection
    connection.close()


def plan(con: sqlite3.Connection, text: str, order: list[tuple[str, str]] | None = None) -> str:
    spec = QuerySpec(scope=SCOPE, where=parse(text), order_by=order or [], limit=50)  # type: ignore[arg-type]
    compiled = compile_query(spec)
    rows = con.execute("EXPLAIN QUERY PLAN " + compiled.sql, compiled.params).fetchall()
    return "\n".join(str(row[3]) for row in rows)


def test_the_default_page_reads_the_created_at_index_and_sorts_nothing(
    con: sqlite3.Connection,
) -> None:
    found = plan(con, "")
    assert "ix_cur_core_record_scope_voided_created" in found
    assert "TEMP B-TREE" not in found


@pytest.mark.parametrize(
    ("column", "direction", "index"),
    [
        ("created_at", "desc", "ix_cur_core_record_scope_voided_created"),
        ("updated_at", "asc", "ix_cur_core_record_scope_voided_updated"),
        ("updated_at", "desc", "ix_cur_core_record_scope_voided_updated"),
        ("key", "asc", "ix_cur_core_record_scope_voided_key_asc"),
        ("key", "desc", "ix_cur_core_record_scope_voided_key_desc"),
    ],
)
def test_the_common_sorts_are_served_by_an_index(
    con: sqlite3.Connection, column: str, direction: str, index: str
) -> None:
    found = plan(con, "", [(column, direction)])
    assert index in found, found
    assert "TEMP B-TREE FOR ORDER BY" not in found, found


def test_a_pset_value_filter_reads_the_set_from_the_value_index(con: sqlite3.Connection) -> None:
    found = plan(con, "psets.v.m=SS")
    assert "ix_cur_pset_values_path_text" in found, found


def test_a_link_filter_with_a_relation_reads_the_relation_indexes(con: sqlite3.Connection) -> None:
    found = plan(con, "linked(references)")
    assert found.count("COVERING INDEX ix_cur_links_relation_status_") == 2, found
