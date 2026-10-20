"""The schedule history mart built from the silver schedule tables (brief 28.2; P1-I8-T08)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_lake import LakeConfig
from tl_lake.duck import Duck, open_lake
from tl_lake.xer_marts import SCHEDULE_HISTORY_TABLE, build_schedule_history

P1, P2 = "project:P1", "project:P2"


@pytest.fixture
def con(tmp_path: Path) -> Iterator[Duck]:
    with open_lake(LakeConfig.at(tmp_path / "lake"), write=True) as opened:
        opened.execute(
            "CREATE TABLE lake.main.schedule_snapshot (snapshot_id VARCHAR, scope VARCHAR, "
            "schedule_code VARCHAR, number BIGINT, state VARCHAR, data_date TIMESTAMP)"
        )
        opened.execute(
            "CREATE TABLE lake.main.schedule_activity (snapshot_id VARCHAR, activity_id VARCHAR, "
            "critical BOOLEAN, percent_complete DOUBLE, early_finish TIMESTAMP)"
        )
        yield opened


def snap(
    con: Duck, snapshot_id: str, number: int, state: str = "Published",
    scope: str = P1, code: str = "MAIN", data_date: str = "2026-09-01 00:00:00",
) -> None:  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.schedule_snapshot VALUES (?, ?, ?, ?, ?, ?)",
        [snapshot_id, scope, code, number, state, data_date],
    )


def act(
    con: Duck, snapshot_id: str, activity_id: str, finish: str,
    critical: bool = False, percent: float = 0.0,
) -> None:  # fmt: skip
    con.execute(
        "INSERT INTO lake.main.schedule_activity VALUES (?, ?, ?, ?, ?)",
        [snapshot_id, activity_id, critical, percent, finish],
    )


def history(con: Duck) -> list[tuple[Any, ...]]:
    return con.execute(
        "SELECT scope, schedule_code, snapshot_number, state, activities, critical_activities, "
        "complete_activities, avg_percent_complete, CAST(latest_early_finish AS VARCHAR), "
        "finish_slip_days, activities_added, activities_removed "
        f"FROM lake.main.{SCHEDULE_HISTORY_TABLE}"
    ).fetchall()


def test_the_first_snapshot_has_no_slip_and_no_added_or_removed(con: Duck) -> None:
    snap(con, "s1", 1)
    act(con, "s1", "A1", "2026-10-01 00:00:00", critical=True, percent=100)
    act(con, "s1", "A2", "2026-11-01 00:00:00", percent=50)
    build_schedule_history(con)
    assert history(con) == [
        (P1, "MAIN", 1, "Published", 2, 1, 1, 75.0, "2026-11-01 00:00:00", None, None, None)
    ]


def test_a_later_snapshot_slips_adds_and_removes_against_the_one_before(con: Duck) -> None:
    snap(con, "s1", 1, "Superseded")
    act(con, "s1", "A1", "2026-10-01 00:00:00")
    act(con, "s1", "A2", "2026-11-01 00:00:00")
    act(con, "s1", "A3", "2026-10-15 00:00:00")
    snap(con, "s2", 2)
    act(con, "s2", "A1", "2026-10-08 00:00:00", critical=True, percent=100)
    act(con, "s2", "A2", "2026-11-08 00:00:00", critical=True, percent=20)
    act(con, "s2", "A4", "2026-11-03 00:00:00")
    act(con, "s2", "A5", "2026-11-04 00:00:00")
    build_schedule_history(con)
    assert history(con) == [
        (P1, "MAIN", 1, "Superseded", 3, 0, 0, 0.0, "2026-11-01 00:00:00", None, None, None),
        (P1, "MAIN", 2, "Published", 4, 2, 1, 30.0, "2026-11-08 00:00:00", 7, 2, 1),
    ]


def test_a_finish_that_moves_earlier_is_a_negative_slip(con: Duck) -> None:
    snap(con, "s1", 1, "Superseded")
    act(con, "s1", "A1", "2026-11-10 00:00:00")
    snap(con, "s2", 2)
    act(con, "s2", "A1", "2026-11-03 00:00:00")
    build_schedule_history(con)
    assert [row[9] for row in history(con)] == [None, -7]


def test_only_published_and_superseded_snapshots_are_in_the_mart(con: Duck) -> None:
    for number, state in enumerate(("Valid", "Published", "Void", "Invalid", "Superseded"), 1):
        snap(con, f"s{number}", number, state)
        act(con, f"s{number}", "A1", "2026-10-01 00:00:00")
    build_schedule_history(con)
    assert [(row[2], row[3]) for row in history(con)] == [(2, "Published"), (5, "Superseded")]


def test_the_snapshot_before_is_the_previous_published_one_not_the_previous_number(
    con: Duck,
) -> None:
    snap(con, "s1", 1, "Superseded")
    act(con, "s1", "A1", "2026-10-01 00:00:00")
    snap(con, "s2", 2, "Void")
    act(con, "s2", "A1", "2026-10-20 00:00:00")
    snap(con, "s3", 3)
    act(con, "s3", "A1", "2026-10-04 00:00:00")
    build_schedule_history(con)
    assert [(row[2], row[9]) for row in history(con)] == [(1, None), (3, 3)]


def test_projects_and_schedules_are_kept_apart(con: Duck) -> None:
    snap(con, "p1a", 1, "Superseded", scope=P1)
    act(con, "p1a", "A1", "2026-10-01 00:00:00")
    snap(con, "p2a", 1, "Published", scope=P2)
    act(con, "p2a", "A1", "2026-12-01 00:00:00")
    snap(con, "p1b", 2, "Published", scope=P1)
    act(con, "p1b", "A1", "2026-10-06 00:00:00")
    snap(con, "x1", 1, "Published", scope=P1, code="SHUT")
    act(con, "x1", "A1", "2027-01-01 00:00:00")
    build_schedule_history(con)
    assert [(row[0], row[1], row[2], row[9]) for row in history(con)] == [
        (P1, "MAIN", 1, None),
        (P1, "MAIN", 2, 5),
        (P1, "SHUT", 1, None),
        (P2, "MAIN", 1, None),
    ]


def test_a_snapshot_without_activities_is_left_out(con: Duck) -> None:
    snap(con, "s1", 1)
    build_schedule_history(con)
    assert history(con) == []


def test_building_again_replaces_the_mart(con: Duck) -> None:
    snap(con, "s1", 1)
    act(con, "s1", "A1", "2026-10-01 00:00:00")
    build_schedule_history(con)
    build_schedule_history(con)
    assert len(history(con)) == 1
    act(con, "s1", "A2", "2026-10-02 00:00:00")
    build_schedule_history(con)
    assert history(con)[0][4] == 2


def test_the_average_percent_complete_has_one_decimal(con: Duck) -> None:
    snap(con, "s1", 1)
    for number, percent in enumerate((10, 20, 25), 1):
        act(con, "s1", f"A{number}", "2026-10-01 00:00:00", percent=percent)
    build_schedule_history(con)
    assert history(con)[0][7] == 18.3


def test_a_published_snapshot_without_activities_is_skipped_as_the_one_before(con: Duck) -> None:
    """Decision (P1-I8): the snapshot before is the previous published one *that has activity
    rows*. An empty one has no finish to compare with and would show every activity as added."""
    snap(con, "s1", 1, "Superseded")
    act(con, "s1", "A1", "2026-10-01 00:00:00")
    act(con, "s1", "A2", "2026-10-02 00:00:00")
    snap(con, "s2", 2, "Superseded")  # published once, but its rows are not in the lake
    snap(con, "s3", 3)
    act(con, "s3", "A1", "2026-10-04 00:00:00")
    act(con, "s3", "A2", "2026-10-02 00:00:00")
    build_schedule_history(con)
    assert [(r[2], r[9], r[10], r[11]) for r in history(con)] == [
        (1, None, None, None),
        (3, 3, 0, 0),
    ]
