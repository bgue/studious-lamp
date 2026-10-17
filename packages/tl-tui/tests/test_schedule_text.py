"""What the schedule screens say, as text (P1-I4). Pure functions, no terminal."""

from __future__ import annotations

from dataclasses import replace

from fakes import FakeClient
from tl_mod_schedule.compare import CriticalChange
from tl_tui import schedule_text as st


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def test_small_formats() -> None:
    assert (st.short(None), st.short(""), st.short("a\n b")) == ("-", "-", "a b")
    assert st.short("x" * 70) == "x" * 59 + "…" and len(st.short("x" * 70)) == 60
    assert st.short("x" * 60) == "x" * 60  # exactly as long as allowed: not cut
    assert st.short("x" * 61) == "x" * 59 + "…"
    assert (st.date_only("2026-10-12T08:00"), st.date_only(None), st.date_only("")) == (
        "2026-10-12",
        "-",
        "-",
    )
    assert (st.hours(40.0), st.hours(-8.5), st.hours(None)) == ("40h", "-8.5h", "-")
    assert (st.days(4.0), st.days(-1.5), st.days(None)) == ("4d", "-1.5d", "-")
    assert (st.shift(7), st.shift(-2), st.shift(0), st.shift(None)) == ("+7d", "-2d", "+0d", "-")


def test_schedule_and_snapshot_rows() -> None:
    client = world()
    [listed] = client.list_schedules("P123")
    assert st.schedule_cells(listed) == (
        "MAIN",
        "current",
        "2",
        "2026-10-12",
        "2",
        "MAIN schedule",
    )
    assert len(st.SCHEDULE_COLUMNS) == len(st.schedule_cells(listed))
    current, older = client.get_schedule("P123", "MAIN").snapshots
    assert st.snapshot_cells(current) == (
        "2*",
        "Published (current)",
        "2026-10-12",
        "5",
        "0",
        "0",
        "MAIN-2.xer",
    )
    assert st.snapshot_cells(older)[:2] == ("1", "Superseded")  # no marker: not the current one
    assert len(st.SNAPSHOT_COLUMNS) == len(st.snapshot_cells(current))


def test_the_schedule_panel_warns_while_the_links_are_being_checked() -> None:
    detail = world().get_schedule("P123", "MAIN")
    assert st.schedule_detail_lines(detail) == [
        "MAIN  MAIN schedule",
        "type current  |  owner -  |  P6 project MAIN",
        "current snapshot 2  |  data date 2026-10-12  |  2 snapshots",
    ]
    checking = st.schedule_detail_lines(detail.model_copy(update={"links_being_checked": True}))
    assert checking[3].startswith("! links to activities are being checked")
    assert "may still read as current" in checking[3]


def test_the_snapshot_panel_names_the_file_the_previous_snapshot_and_what_failed() -> None:
    current = world().get_schedule("P123", "MAIN").snapshots[0]
    assert st.snapshot_detail_lines(current) == [
        "MAIN#2  Published (current)  |  data date 2026-10-12T08:00  |  P6 20.12",
        "activities 5  relationships 4  WBS 2  calendars 1  codes 0  user fields 0",
        "errors 0  warnings 0  |  file MAIN-2.xer  |  requested by user:dev",
        "compares with snapshot 1",
    ]
    waiting = current.model_copy(update={"state": "Processing", "is_current": False})
    assert "waiting for the worker (`tl xer worker`)" in st.snapshot_detail_lines(waiting)
    failed = current.model_copy(update={"state": "Invalid", "last_error": "e\n" * 200})
    last = st.snapshot_detail_lines(failed)[-1]
    assert last.startswith("last error: e e e") and len(last) == len("last error: ") + 200


def test_the_schedule_status_line() -> None:
    assert st.schedules_summary(1, 3, text="") == "1 of 3 schedules"
    assert st.schedules_summary(1, 3, text=" ma ") == '1 of 3 schedules  filter "ma"'


def test_the_comparison_header_tabs_and_each_section() -> None:
    cmp = world().compare_snapshots("P123", "MAIN")
    assert st.compare_header_lines(cmp) == [
        "MAIN#2 (2026-10-12) against MAIN#1 (2026-10-05)",
        "data date +7d  |  latest finish 2026-10-16 to 2026-10-23 (+7d)",
    ]
    assert st.compare_tabs(cmp) == [
        "Added 1",
        "Removed 1",
        "Date shifts 1",
        "Float 1",
        "Logic 1",
        "Progress 0",
        "Durations 0",
        "Critical 0",
    ]
    assert [name for name, _ in st.COMPARE_SECTIONS] == [
        "added",
        "removed",
        "date_shifts",
        "float_changes",
        "logic_changes",
        "progress_changes",
        "duration_changes",
        "critical_changes",
    ]
    assert st.compare_section_lines(cmp, "added") == [
        "+ A2500  Weld inspection hold point  (P > W)"
    ]
    assert st.compare_section_lines(cmp, "removed") == ["- A1990  Temporary fencing  (P > W)"]
    assert st.compare_section_lines(cmp, "date_shifts") == [
        "~ A1230  start -  finish +7d  largest 7d  Install pipe rack supports"
    ]
    assert st.compare_section_lines(cmp, "float_changes") == [
        "~ A1230  float 9d to 4d  ERODED  Install pipe rack supports"
    ]
    assert st.compare_section_lines(cmp, "logic_changes") == ["added   A1230 -> A2500  - to FS"]
    for empty in ("progress_changes", "duration_changes", "critical_changes"):
        assert st.compare_section_lines(cmp, empty) == ["none"]
    assert st.compare_section_lines(cmp, "nonsense") == []


def test_a_critical_change_is_marked_in_text_and_a_cut_list_says_so() -> None:
    cmp = world().compare_snapshots("P123", "MAIN")
    entered = CriticalChange("A9", "Pour slab", "entered", 4.0, -1.0)
    left = CriticalChange("A8", "Pour pad", "left", 0.0, 3.0)
    marked = replace(
        cmp, critical_changes=(entered, left), totals={**cmp.totals, "critical_changes": 5}
    )
    assert st.compare_section_lines(marked, "critical_changes") == [
        "! A9  entered the critical set  float 4d to -1d  Pour slab",
        "  A8  left the critical set  float 0d to 3d  Pour pad",
        "... 3 more not shown",
    ]
    assert (
        st.compare_section_lines(marked, "critical_changes", limit=1)[-1] == "... 4 more not shown"
    )
    assert st.compare_tabs(marked)[-1] == "Critical 5"  # the full count, not the rows kept


def test_the_activity_table_rows_and_status_line() -> None:
    client = world()
    page = client.list_activities("P123", "MAIN", limit=2)
    assert [st.activity_cells(a) for a in page.rows] == [
        (
            "A1220",
            "completed",
            "2026-10-05",
            "2026-10-16",
            "0h",
            "100",
            "critical",
            "Set rack foundations",
        ),
        (
            "A1230",
            "not_started",
            "2026-10-05",
            "2026-10-23",
            "32h",
            "0",
            "",
            "Install pipe rack supports",
        ),
    ]
    assert len(st.ACTIVITY_COLUMNS) == 8
    assert st.page_line(page, critical=False, text="") == (
        "MAIN#2  data date 2026-10-12  |  1-2 of 4 activities"
    )
    later = client.list_activities("P123", "MAIN", limit=2, offset=2)
    assert st.page_line(later, critical=True, text=" rack ") == (
        'MAIN#2  data date 2026-10-12  |  3-4 of 4 activities  |  critical only  |  filter "rack"'
    )
    none = client.list_activities("P123", "MAIN", q="nothing like this")
    assert st.page_line(none, critical=False, text="") == (
        "MAIN#2  data date 2026-10-12  |  0-0 of 0 activities"
    )


def test_one_activity_with_its_neighbours_and_its_float_trend() -> None:
    client = world()
    detail = client.get_schedule_activity("P123", "MAIN", "A1230")
    assert st.activity_detail_lines(detail) == [
        "A1230  Install pipe rack supports  |  MAIN#2",
        "task  not_started  0% (CP_Drtn)  |  WBS P > W",
        "early 2026-10-05 to 2026-10-23  |  late 2026-10-12 to 2026-10-23  |  actual - to -",
        "float total 32h  free 40h",
        "predecessors 1",
        "  A1220  FS  lag 0h",
        "successors 2",
        "  A1240  FS  lag 0h",
        "  A2500  FS  lag 0h",
    ]
    assert "constraint" not in st.activity_detail_lines(detail)[3]
    constrained = replace(
        detail,
        activity=replace(
            detail.activity, constraint_type="start_on_or_after", constraint_date="2026-10-20T08:00"
        ),
    )
    assert st.activity_detail_lines(constrained)[3] == (
        "float total 32h  free 40h  |  constraint start_on_or_after 2026-10-20"
    )
    critical = client.get_schedule_activity("P123", "MAIN", "A1220")
    assert st.activity_detail_lines(critical)[3].endswith("  CRITICAL")
    assert st.activity_detail_lines(critical)[4:] == [
        "predecessors 0",
        "successors 1",
        "  A1230  FS  lag 0h",
    ]
    assert st.trend_lines(client.get_activity_trend("P123", "MAIN", "A1230")) == [
        "float trend:",
        "  #1  2026-10-05  Superseded  float 9d  2026-10-05 to 2026-10-16  0%",
        "  #2  2026-10-12  Published  float 4d  2026-10-05 to 2026-10-23  0%",
    ]


def test_the_look_ahead_lines() -> None:
    from tl_mod_schedule.lookahead import LookAhead, LookAheadRow

    row = LookAheadRow(
        "A1110", "Fabricate valves", "P > W", "in_progress", "in_progress",
        "2026-08-24T08:00", "2026-11-09T16:00", -1.0, True, 65.0,
    )  # fmt: skip
    answer = LookAhead(
        "MAIN#2", 2, "2026-10-12T08:00", "2026-10-12", "2026-11-09", 4, (row,),
        {"in_progress": 1, "critical": 1, "total": 1},
    )  # fmt: skip
    assert st.look_ahead_lines(answer) == [
        "look-ahead MAIN#2: 2026-10-12 to 2026-11-09 (4 weeks)",
        "in progress 1  late start 0  starting 0  critical 1  total 1",
        "  A1110  in_progress  2026-08-24 to 2026-11-09  float -1d  65%  CRITICAL  "
        "Fabricate valves",
    ]


def test_the_orphaned_links_lines() -> None:
    from tl_mod_schedule.resolver import OrphanedLink

    assert st.orphan_lines([]) == [
        "no orphaned links: every activity that is linked to is in the current snapshot"
    ]
    links = [
        OrphanedLink("L1", "R1", "A1990", 1, "gone"),
        OrphanedLink("L2", "R2", "A2000", None, "gone"),
    ]
    assert st.orphan_lines(links) == [
        "orphaned links: 2",
        "  A1990  last seen in snapshot 1  record R1  link L1",
        "  A2000  last seen in snapshot -  record R2  link L2",
    ]
