"""`tl xer compare|look-ahead|trend` (P1-I4-T09c)."""

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


# --- compare ------------------------------------------------------------------------------------


def test_compare_shows_the_week_between_the_last_two_snapshots(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "compare", *P, *SCHED, "--limit", "3") == [
        "compare MAIN#2 (2026-10-12T08:00) with MAIN#1 (2026-10-05T08:00)",
        "data date shift +7d",
        "latest finish 2026-12-03T16:00 -> 2026-12-04T16:00  +1d",
        "summary added 1  removed 1  date shifts 9  float changes 8  logic changes 3  "
        "progress changes 1  duration changes 0  critical changes 3",
        "added A2500  Weld inspection hold point",
        "removed A1990  Temporary fencing",
        "shift A1110  start -  finish +7d  largest 7d  Fabricate valves",
        "shift A1120  start +7d  finish +7d  largest 7d  Deliver valves to site",
        "shift A1140  start -  finish -  largest 7d  Fabricate pipe spools",
        "... date_shifts 6 more not shown",
        "float A1110  4d -> -1d  eroded  Fabricate valves",
        "float A1120  4d -> -1d  eroded  Deliver valves to site",
        "float A1230  9d -> 4d  eroded  Install pipe rack supports",
        "... float_changes 5 more not shown",
        "logic removed A1200 -> A1990  FS -> -",
        "logic added A1120 -> A1290  - -> FS",
        "logic added A1230 -> A2500  - -> FS",
        "progress A1140  60% -> 80%  in_progress -> in_progress  Fabricate pipe spools",
        "critical A1110  entered  float 4d -> -1d  Fabricate valves",
        "critical A1120  entered  float 4d -> -1d  Deliver valves to site",
        "critical A1290  entered  float 1d -> 0d  Insulate lines",
    ]


def test_compare_with_the_default_limit_shows_every_row_and_no_cut_line(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    out = lines(cast, "compare", *P, *SCHED)
    assert out[3] == (
        "summary added 1  removed 1  date shifts 9  float changes 8  logic changes 3  "
        "progress changes 1  duration changes 0  critical changes 3"
    )
    assert not any(x.startswith("...") for x in out)
    kinds = [x.split()[0] for x in out[4:]]
    assert kinds.count("shift") == 9 and kinds.count("float") == 8
    assert kinds == sorted(
        kinds,
        key=[
            "added",
            "removed",
            "shift",
            "float",
            "logic",
            "progress",
            "duration",
            "critical",
        ].index,
    )


def test_compare_names_the_two_snapshots_it_is_given(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    same = lines(cast, "compare", *P, *SCHED, "--new", "2", "--old", "1", "--limit", "1")
    assert same[0] == "compare MAIN#2 (2026-10-12T08:00) with MAIN#1 (2026-10-05T08:00)"
    backwards = lines(cast, "compare", *P, *SCHED, "--new", "1", "--old", "2", "--limit", "1")
    assert backwards[0] == "compare MAIN#1 (2026-10-05T08:00) with MAIN#2 (2026-10-12T08:00)"
    assert backwards[1] == "data date shift -7d"
    assert backwards[4] == "added A1990  Temporary fencing"
    assert backwards[5] == "removed A2500  Weld inspection hold point"


def test_compare_says_improved_when_the_float_grew(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    backwards = lines(cast, "compare", *P, *SCHED, "--new", "1", "--old", "2")
    assert "float A1230  4d -> 9d  improved  Install pipe rack supports" in backwards
    assert not any(x.startswith("float ") and "eroded" in x for x in backwards[:4])


def test_compare_refuses_what_cannot_be_compared(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert "error: snapshot MAIN#1 has no earlier snapshot to compare" in refused(
        cast, "compare", *P, *SCHED, "--new", "1"
    )
    assert "error: schedule MAIN has no snapshot 5" in refused(
        cast, "compare", *P, *SCHED, "--old", "5"
    )
    assert tl(cast.ursula, "xer", "compare", *P, *SCHED, "--limit", "0").exit_code == 2
    assert "error: no schedule 'MAIN' in project:P999" in refused(
        cast, "compare", "--project", "P999", *SCHED
    )


# --- look-ahead ---------------------------------------------------------------------------------


def test_look_ahead_lists_what_is_under_way_and_what_starts_in_four_weeks(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "look-ahead", *P, *SCHED) == [
        "look-ahead MAIN#2  2026-10-12 to 2026-11-09  4 weeks",
        "in progress 3  late start 0  starting 3  critical 4  total 6",
        "A1110  in_progress  start 2026-08-24T08:00  finish 2026-11-09T16:00  float -1d  65%  "
        "critical  Fabricate valves",
        "A1140  in_progress  start 2026-09-14T08:00  finish 2026-10-16T16:00  float 0d  80%  "
        "critical  Fabricate pipe spools",
        "A1230  in_progress  start 2026-09-24T08:00  finish 2026-10-19T16:00  float 4d  40%  "
        "ok  Install pipe rack supports",
        "A1150  starting  start 2026-10-19T08:00  finish 2026-10-23T16:00  float 0d  0%  "
        "critical  Deliver pipe spools to site",
        "A2500  starting  start 2026-10-20T08:00  finish 2026-10-22T16:00  float 30d  0%  "
        "ok  Weld inspection hold point",
        "A1240  starting  start 2026-10-26T08:00  finish 2026-11-13T16:00  float 0d  0%  "
        "critical  Erect pipe spools on rack",
    ]


def test_look_ahead_takes_a_window_and_a_snapshot(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    one_week = lines(cast, "look-ahead", *P, *SCHED, "--weeks", "1")
    assert one_week[0] == "look-ahead MAIN#2  2026-10-12 to 2026-10-19  1 weeks"
    assert one_week[1] == "in progress 3  late start 0  starting 1  critical 3  total 4"
    assert [x.split()[0] for x in one_week[2:]] == ["A1110", "A1140", "A1230", "A1150"]
    earlier = lines(cast, "look-ahead", *P, *SCHED, "--snapshot", "1")
    assert earlier[0] == "look-ahead MAIN#1  2026-10-05 to 2026-11-02  4 weeks"


def test_look_ahead_refuses_a_window_outside_one_to_twenty_six_weeks(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    for weeks in ("0", "27", "-3"):
        assert "error: weeks must be between 1 and 26" in refused(
            cast, "look-ahead", *P, *SCHED, "--weeks", weeks
        )
    assert lines(cast, "look-ahead", *P, *SCHED, "--weeks", "26")[0].endswith("26 weeks")


# --- trend --------------------------------------------------------------------------------------


def test_trend_follows_one_activitys_float_through_the_snapshots(
    cast: Cast, tmp_path: Path
) -> None:
    published_pair(cast, tmp_path)
    assert lines(cast, "trend", "A1230", *P, *SCHED) == [
        "trend A1230 in MAIN",
        "MAIN#1  Superseded  data date 2026-10-05T08:00  float 9d  start 2026-09-24T08:00  "
        "finish 2026-10-12T16:00  40%  ok",
        "MAIN#2  Published  data date 2026-10-12T08:00  float 4d  start 2026-09-24T08:00  "
        "finish 2026-10-19T16:00  40%  ok",
    ]
    left = lines(cast, "trend", "A1990", *P, *SCHED)
    assert left[0] == "trend A1990 in MAIN" and len(left) == 2  # only snapshot 1 has it
    assert left[1].startswith("MAIN#1  Superseded  ") and "  float -  " in left[1]


def test_trend_of_an_activity_no_snapshot_has_is_an_error(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    assert "error: no schedule 'MAIN' in project:P999" in refused(
        cast, "trend", "A1230", "--project", "P999", *SCHED
    )
    assert "error: no published snapshot of MAIN has activity 'A9999'" in refused(
        cast, "trend", "A9999", *P, *SCHED
    )


# --- reads write nothing ------------------------------------------------------------------------


def test_no_comparison_read_writes_to_the_ledger(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)

    def count() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    before = count()
    for command in (
        ("compare", *P, *SCHED),
        ("look-ahead", *P, *SCHED),
        ("trend", "A1230", *P, *SCHED),
    ):
        lines(cast, *command)
    assert count() == before


def test_every_comparison_read_looks_only_in_its_own_project(cast: Cast, tmp_path: Path) -> None:
    published_pair(cast, tmp_path)
    for command in (("compare",), ("look-ahead",), ("trend", "A1230")):
        out = refused(cast, *command, "--project", "P999", *SCHED)
        assert "error: no schedule 'MAIN' in project:P999" in out, command
