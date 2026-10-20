"""The document marts built from silver tables (brief 28.2, 28.4; P1-I8-T08).

The silver tables are made by hand here, with the columns the marts read, in a throw-away lake: the
marts are SQL over silver and need no ledger.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_lake import LakeConfig
from tl_lake.doc_marts import (
    ISSUES_TABLE,
    MARTS,
    STATUS_TABLE,
    TURNAROUND_TABLE,
    build_document_marts,
)
from tl_lake.duck import Duck, lake_tables, open_lake

P1, P2 = "project:P1", "project:P2"


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        opened.execute("CREATE TABLE lake.main.cur_core_record (id VARCHAR, voided BOOLEAN)")
        opened.execute(
            "CREATE TABLE lake.main.cur_documents_document (id VARCHAR, scope VARCHAR, "
            "discipline VARCHAR, doc_type VARCHAR, current_revision_status VARCHAR, "
            "current_revision_issued_on VARCHAR)"
        )
        opened.execute(
            "CREATE TABLE lake.main.cur_documents_revision (id VARCHAR, scope VARCHAR, "
            "document_id VARCHAR, ordinal BIGINT, issued_on VARCHAR)"
        )
        yield opened


def doc(
    con: Duck,
    doc_id: str,
    scope: str = P1,
    discipline: str | None = "PIP",
    doc_type: str | None = "ISO",
    status: str | None = "IFC",
    issued: str | None = "2026-01-10",
    voided: bool = False,
) -> None:
    con.execute("INSERT INTO lake.main.cur_core_record VALUES (?, ?)", [doc_id, voided])
    con.execute(
        "INSERT INTO lake.main.cur_documents_document VALUES (?, ?, ?, ?, ?, ?)",
        [doc_id, scope, discipline, doc_type, status, issued],
    )


def rev(con: Duck, doc_id: str, ordinal: int, issued: str | None, scope: str = P1) -> None:
    con.execute(
        "INSERT INTO lake.main.cur_documents_revision VALUES (?, ?, ?, ?, ?)",
        [f"{doc_id}-{ordinal}", scope, doc_id, ordinal, issued],
    )


def rows(con: Duck, table: str) -> list[tuple[Any, ...]]:
    return con.execute(f"SELECT * FROM lake.main.{table}").fetchall()


def test_no_document_means_no_mart(con: Duck) -> None:
    build_document_marts(con)
    assert not set(MARTS) & set(lake_tables(con))


def test_a_stale_mart_is_dropped_when_the_documents_are_gone(con: Duck) -> None:
    doc(con, "d1")
    build_document_marts(con)
    assert set(MARTS) <= set(lake_tables(con))
    con.execute("DELETE FROM lake.main.cur_documents_document")
    build_document_marts(con)
    assert not set(MARTS) & set(lake_tables(con))


def test_a_lake_with_only_some_of_the_silver_tables_builds_nothing(con: Duck) -> None:
    doc(con, "a")
    con.execute("DROP TABLE lake.main.cur_documents_revision")
    build_document_marts(con)
    assert not set(MARTS) & set(lake_tables(con))
    con.execute("CREATE TABLE lake.main.cur_documents_revision (id VARCHAR)")
    con.execute("DROP TABLE lake.main.cur_core_record")
    build_document_marts(con)
    assert not set(MARTS) & set(lake_tables(con))


def test_a_lake_without_the_document_tables_builds_nothing() -> None:
    # nothing to open: the function reads lake_tables, so a connection with no tables is enough
    class Bare:
        def __init__(self) -> None:
            self.sql: list[str] = []

        def execute(self, sql: str, *args: Any) -> Any:
            self.sql.append(sql)
            return self

        def fetchall(self) -> list[Any]:
            return []

        def fetchone(self) -> None:
            return None

    bare = Bare()
    build_document_marts(bare)  # type: ignore[arg-type]
    assert not any("CREATE TABLE" in s for s in bare.sql)


def test_the_status_mart_counts_documents_by_project_discipline_type_and_status(con: Duck) -> None:
    doc(con, "a", status="IFC", issued="2026-01-10")
    doc(con, "b", status="IFC", issued="2026-02-01")
    doc(con, "c", status="AFC", issued="2026-03-05")
    doc(con, "d", discipline="PRO", doc_type="PID", status="IFC", issued=None)
    doc(con, "e", scope=P2, status="IFC", issued="2026-04-01")
    build_document_marts(con)
    assert rows(con, STATUS_TABLE) == [
        (P1, "PIP", "ISO", "AFC", 1, "2026-03-05", "2026-03-05"),
        (P1, "PIP", "ISO", "IFC", 2, "2026-01-10", "2026-02-01"),
        (P1, "PRO", "PID", "IFC", 1, None, None),
        (P2, "PIP", "ISO", "IFC", 1, "2026-04-01", "2026-04-01"),
    ]


def test_missing_discipline_type_and_status_are_a_dash_and_an_empty_date_is_none(
    con: Duck,
) -> None:
    doc(con, "a", discipline=None, doc_type=None, status=None, issued="")
    build_document_marts(con)
    assert rows(con, STATUS_TABLE) == [(P1, "-", "-", "-", 1, None, None)]


def test_a_voided_document_is_in_no_mart(con: Duck) -> None:
    doc(con, "a")
    doc(con, "gone", voided=True)
    rev(con, "a", 1, "2026-01-01")
    rev(con, "gone", 1, "2026-01-02")
    build_document_marts(con)
    assert rows(con, STATUS_TABLE) == [(P1, "PIP", "ISO", "IFC", 1, "2026-01-10", "2026-01-10")]
    assert rows(con, TURNAROUND_TABLE) == [(P1, "PIP", 1, 1, None, None)]
    assert rows(con, ISSUES_TABLE) == [(P1, "2026-01", 1, 1)]


def test_turnaround_is_the_gap_between_a_documents_consecutive_issues(con: Duck) -> None:
    doc(con, "a")
    rev(con, "a", 1, "2026-01-01")
    rev(con, "a", 2, "2026-01-11")
    rev(con, "a", 3, "2026-02-10")
    rev(con, "a", 4, None)  # never issued: no gap
    doc(con, "b")
    rev(con, "b", 1, "2026-03-01")
    rev(con, "b", 2, "2026-03-05")
    build_document_marts(con)
    # gaps: a 10 and 30 days, b 4 days
    assert rows(con, TURNAROUND_TABLE) == [(P1, "PIP", 2, 5, 14.7, 30)]


def test_the_gap_follows_the_ordinal_not_the_order_of_the_rows(con: Duck) -> None:
    doc(con, "a")
    rev(con, "a", 2, "2026-01-21")
    rev(con, "a", 1, "2026-01-01")
    build_document_marts(con)
    assert rows(con, TURNAROUND_TABLE) == [(P1, "PIP", 1, 2, 20.0, 20)]


def test_an_issue_date_that_is_not_a_date_is_ignored_and_a_time_is_cut(con: Duck) -> None:
    doc(con, "a")
    rev(con, "a", 1, "not a date")
    rev(con, "a", 2, "2026-02-01T09:30:00")
    rev(con, "a", 3, "")
    build_document_marts(con)
    assert rows(con, TURNAROUND_TABLE) == [(P1, "PIP", 1, 1, None, None)]
    assert rows(con, ISSUES_TABLE) == [(P1, "2026-02", 1, 1)]


def test_projects_and_disciplines_are_kept_apart(con: Duck) -> None:
    doc(con, "a", scope=P1, discipline="PIP")
    doc(con, "b", scope=P1, discipline="PRO")
    doc(con, "c", scope=P2, discipline="PIP")
    for doc_id, scope in (("a", P1), ("b", P1), ("c", P2)):
        rev(con, doc_id, 1, "2026-01-01", scope)
        rev(con, doc_id, 2, "2026-01-06", scope)
    build_document_marts(con)
    assert rows(con, TURNAROUND_TABLE) == [
        (P1, "PIP", 1, 2, 5.0, 5),
        (P1, "PRO", 1, 2, 5.0, 5),
        (P2, "PIP", 1, 2, 5.0, 5),
    ]


def test_the_issue_trend_counts_revisions_and_documents_per_month(con: Duck) -> None:
    doc(con, "a")
    doc(con, "b")
    rev(con, "a", 1, "2026-01-02")
    rev(con, "a", 2, "2026-01-20")
    rev(con, "b", 1, "2026-01-25")
    rev(con, "b", 2, "2026-03-01")
    build_document_marts(con)
    assert rows(con, ISSUES_TABLE) == [(P1, "2026-01", 3, 2), (P1, "2026-03", 1, 1)]


def test_building_again_gives_the_same_marts_and_follows_a_change(con: Duck) -> None:
    doc(con, "a")
    rev(con, "a", 1, "2026-01-02")
    build_document_marts(con)
    first = {t: rows(con, t) for t in MARTS}
    build_document_marts(con)
    assert {t: rows(con, t) for t in MARTS} == first
    doc(con, "b", status="AFC")
    build_document_marts(con)
    assert len(rows(con, STATUS_TABLE)) == 2
