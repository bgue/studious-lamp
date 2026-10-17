"""`tl xer ls|show|activities|activity|resolve|health` (P1-I4-T09b)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from xercli_support import Cast, P, published_pair, tl, xer_env

AUTO_SIGN_IN = False  # this module signs in as three different people itself
SCHED = ("--schedule", "MAIN")


@pytest.fixture
def cast(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cast:
    return Cast(xer_env(new_db, monkeypatch, tmp_path), tmp_path)


def lines(cast: Cast, *args: str) -> list[str]:
    """What a plain user (who may only read) sees for one command."""
    return tl(cast.ursula, "xer", *args, ok=True).stdout.splitlines()


def refused(cast: Cast, *args: str) -> str:
    return tl(cast.ursula, "xer", *args, ok=False).output


# --- ls and show --------------------------------------------------------------------------------


def test_ls_says_so_when_there_is_no_schedule(cast: Cast) -> None:
    assert lines(cast, "ls", *P) == ["no schedules in project P123"]


def test_ls_lists_a_schedule_before_its_snapshots(cast: Cast) -> None:
    tl(cast.dora, "xer", "define", "MAIN", *P, "--name", "Main schedule", ok=True)
    assert lines(cast, "ls", *P) == [
        "MAIN  current  current -  data date -  snapshots 0  Main schedule"
    ]


def test_ls_lists_a_schedule_with_its_current_snapshot_in_its_own_project(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "ls", *P) == [
        "MAIN  current  current 2  data date 2026-10-12T08:00  snapshots 2  Main schedule"
    ]
    assert lines(cast, "ls", "--project", "P999") == ["no schedules in project P999"]


def test_show_prints_the_schedule_and_its_snapshots_newest_first(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "show", *P, *SCHED) == [
        "schedule MAIN",
        "title Main schedule",
        "type current",
        "p6 project DEMO-RACK",
        "owner Planning",
        "current 2  data date 2026-10-12T08:00",
        "snapshot 2  Published  current  data date 2026-10-12T08:00  activities 21  errors 0  "
        "warnings 0  update-2.xer",
        "snapshot 1  Superseded  data date 2026-10-05T08:00  activities 21  errors 0  "
        "warnings 0  update-1.xer",
    ]


def test_show_says_while_the_links_are_still_being_checked(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path, worker_after=False)
    window = lines(cast, "show", *P, *SCHED)
    assert window[6] == "links being checked"
    assert len(window) == 9
    tl(cast.boss, "xer", "worker", "--once", ok=True)
    assert "links being checked" not in lines(cast, "show", *P, *SCHED)


def test_a_schedule_that_is_not_there_is_an_error_not_a_trace(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert "error: no schedule 'NOPE' in project:P123" in refused(
        cast, "show", *P, "--schedule", "NOPE"
    )
    # another project cannot read this one's schedule
    assert "error: no schedule 'MAIN' in project:P999" in refused(
        cast, "show", "--project", "P999", *SCHED
    )


# --- activities and activity --------------------------------------------------------------------


def test_activities_lists_the_current_snapshot_in_file_order(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "activities", *P, *SCHED, "--limit", "2") == [
        "MAIN#2  data date 2026-10-12T08:00  showing 2 of 21 from 0",
        "A1000  completed  start 2026-08-03T08:00  finish 2026-08-14T16:00  float -  100%  ok  "
        "Issue P&IDs IFC",
        "A1010  completed  start 2026-08-17T08:00  finish 2026-09-04T16:00  float -  100%  ok  "
        "Issue piping isometrics IFC",
    ]


def test_activities_pages_filters_and_picks_a_snapshot(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    page = lines(cast, "activities", *P, *SCHED, "--limit", "2", "--offset", "2")
    assert page[0] == "MAIN#2  data date 2026-10-12T08:00  showing 2 of 21 from 2"
    assert [x.split()[0] for x in page[1:]] == ["A1020", "A1100"]

    critical = lines(cast, "activities", *P, *SCHED, "--critical")
    assert critical[0] == "MAIN#2  data date 2026-10-12T08:00  showing 10 of 10 from 0"
    assert all("  critical  " in x for x in critical[1:])
    assert critical[1].startswith("A1110  in_progress  start 2026-08-24T08:00  finish ")
    assert "float -8h  65%  critical  Fabricate valves" in critical[1]

    done = lines(cast, "activities", *P, *SCHED, "--status", "completed", "--limit", "100")
    assert done[0] == "MAIN#2  data date 2026-10-12T08:00  showing 8 of 8 from 0"
    assert all("  completed  " in x for x in done[1:])

    found = lines(cast, "activities", *P, *SCHED, "--search", "valves")
    assert found[0] == "MAIN#2  data date 2026-10-12T08:00  showing 4 of 4 from 0"
    assert [x.split()[0] for x in found[1:]] == ["A1100", "A1110", "A1120", "A1250"]

    first = lines(cast, "activities", *P, *SCHED, "--snapshot", "1", "--limit", "1")
    assert first[0] == "MAIN#1  data date 2026-10-05T08:00  showing 1 of 21 from 0"


def test_activities_refuses_a_bad_option_and_an_unknown_snapshot(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert tl(cast.ursula, "xer", "activities", *P, *SCHED, "--limit", "0").exit_code == 2
    assert tl(cast.ursula, "xer", "activities", *P, *SCHED, "--offset", "-1").exit_code == 2
    assert "error: schedule MAIN has no snapshot 7" in refused(
        cast, "activities", *P, *SCHED, "--snapshot", "7"
    )


def test_activity_shows_one_activity_with_its_neighbours(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "activity", "A1230", *P, *SCHED) == [
        "activity A1230 in MAIN#2",
        "name Install pipe rack supports",
        "wbs DEMO > CON",
        "type task  status in_progress  percent 40",
        "early 2026-09-24T08:00 -> 2026-10-19T16:00",
        "late 2026-10-16T08:00 -> 2026-10-23T16:00",
        "actual 2026-09-24T08:00 -> -",
        "float total 32h  free 0h  ok",
        "predecessors 1",
        "  A1220  FS  lag 0h",
        "successors 2",
        "  A1240  FS  lag 0h",
        "  A2500  FS  lag 0h",
    ]
    earlier = lines(cast, "activity", "A1230", *P, *SCHED, "--snapshot", "1")
    assert earlier[0] == "activity A1230 in MAIN#1"
    assert earlier[4] == "early 2026-09-24T08:00 -> 2026-10-12T16:00"
    assert earlier[7] == "float total 72h  free 72h  ok"
    assert earlier[10:] == ["successors 1", "  A1240  FS  lag 0h"]


def test_activity_that_is_not_in_the_snapshot_is_an_error(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert "error: snapshot MAIN#2 has no activity 'A1990'" in refused(
        cast, "activity", "A1990", *P, *SCHED
    )
    # another project cannot read this one's schedule through an activity either
    assert "error: no schedule 'MAIN' in project:P999" in refused(
        cast, "activity", "A1230", "--project", "P999", *SCHED
    )
    assert lines(cast, "activity", "A1990", *P, *SCHED, "--snapshot", "1")[0] == (
        "activity A1990 in MAIN#1"
    )


# --- resolve and health -------------------------------------------------------------------------


def test_resolve_says_what_an_activity_is_now_and_as_of_an_earlier_snapshot(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "resolve", "A1230", *P, *SCHED) == [
        "A1230  current  MAIN#2  data date 2026-10-12T08:00",
        "name Install pipe rack supports  start 2026-09-24T08:00  "
        "finish 2026-10-19T16:00  float 32h",
    ]
    assert lines(cast, "resolve", "A1230", *P, *SCHED, "--as-of", "current")[0] == (
        "A1230  current  MAIN#2  data date 2026-10-12T08:00"
    )
    assert lines(cast, "resolve", "A1230", *P, *SCHED, "--as-of", "1") == [
        "A1230  as_of  MAIN#1  data date 2026-10-05T08:00",
        "name Install pipe rack supports  start 2026-09-24T08:00  "
        "finish 2026-10-12T16:00  float 72h",
    ]
    # a date names the latest published snapshot on or before it
    assert lines(cast, "resolve", "A1230", *P, *SCHED, "--as-of", "2026-10-08")[0] == (
        "A1230  as_of  MAIN#1  data date 2026-10-05T08:00"
    )


def test_resolve_finds_nothing_in_another_project(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert "error: no schedule 'MAIN' in project:P999" in refused(
        cast, "resolve", "A1230", "--project", "P999", *SCHED
    )


def test_resolve_names_an_activity_that_left_and_one_that_never_was(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "resolve", "A1990", *P, *SCHED) == [
        "A1990  orphaned  MAIN#2  data date 2026-10-12T08:00"
    ]
    assert lines(cast, "resolve", "A9999", *P, *SCHED) == [
        "A9999  unknown_activity  MAIN#2  data date 2026-10-12T08:00"
    ]
    assert lines(cast, "resolve", "A1230", *P, *SCHED, "--as-of", "2020-01-01") == [
        "A1230  no_snapshot  -  data date -"
    ]


def test_health_lists_the_links_the_publication_flagged(cast: Cast, tmp_path: Path) -> None:
    _, orphan = published_pair(cast, tmp_path)
    [head, line] = lines(cast, "health", *P, *SCHED)
    assert head == "orphaned links: 1"
    assert line.startswith(f"{orphan}  record ") and line.endswith("  activity A1990  last seen 1")


def test_health_is_empty_until_the_flagging_job_has_run(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path, worker_after=False)
    assert lines(cast, "health", *P, *SCHED) == ["orphaned links: 0"]
    tl(cast.boss, "xer", "worker", "--once", ok=True)
    assert lines(cast, "health", *P, *SCHED)[0] == "orphaned links: 1"


# --- reads write nothing ------------------------------------------------------------------------


def test_no_read_writes_to_the_ledger(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)

    def count() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    before = count()
    for command in (
        ("ls", *P),
        ("show", *P, *SCHED),
        ("activities", *P, *SCHED),
        ("activity", "A1230", *P, *SCHED),
        ("resolve", "A1230", *P, *SCHED),
        ("health", *P, *SCHED),
    ):
        lines(cast, *command)
    assert count() == before


def test_every_read_looks_only_in_its_own_project(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    for command in (
        ("show",),
        ("activities",),
        ("activity", "A1230"),
        ("resolve", "A1230"),
        ("health",),
    ):
        out = refused(cast, *command, "--project", "P999", *SCHED)
        assert "error: no schedule 'MAIN' in project:P999" in out, command
