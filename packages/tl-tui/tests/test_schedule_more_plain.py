"""The compare and activity screens, look-ahead and orphaned links in plain words (P1-UX-T06b).

A snapshot is ``Snapshot 2`` in plain mode and ``MAIN#2`` in technical mode; a P6 status is its
words in plain mode and its code in technical mode; the record and link ids of an orphaned link
show in technical mode only. The two screens redraw when the mode switches (D14).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from textual.screen import ModalScreen
from tl_mod_schedule.compare import LogicChange, ProgressChange
from tl_mod_schedule.lookahead import LookAhead, LookAheadRow
from tl_mod_schedule.resolver import OrphanedLink
from tl_tui import schedule_text as st
from tl_tui.app import TlApp
from tl_tui.display import find_technical
from tl_tui.widgets.activity_screen import ActivityScreen
from tl_tui.widgets.compare_screen import CompareScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_schedule("P123")
    return client


def scenario(
    client: FakeClient,
    screen_for: Callable[[FakeClient], ModalScreen[None]],
    steps: Callable[[Pilot[None], TlApp], Awaitable[None]],
) -> None:
    """An admin, so that Ctrl+D (the technical toggle) works; the screen is pushed and shown."""
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=True)

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(screen_for(client))
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go)


def test_snapshot_name_plain_and_technical() -> None:
    assert st.snapshot_name("MAIN#2", technical=True) == "MAIN#2"
    assert st.snapshot_name("MAIN#2", technical=False) == "Snapshot 2"
    assert st.snapshot_name("SIDE#11", technical=False) == "Snapshot 11"
    assert st.snapshot_name("MAIN", technical=False) == "MAIN"  # no number: the key itself


def test_status_words() -> None:
    assert st.status_words("TK_Active") == "Active"
    assert st.status_words("TT_Task") == "Task"
    assert st.status_words("PCT_Physical") == "Physical"
    assert st.status_words("not_started") == "Not started"
    assert st.status_words(None) == "-" and st.status_words("") == "-"


def test_progress_rows_show_status_words_in_plain_and_codes_in_technical() -> None:
    cmp = world().compare_snapshots("P123", "MAIN")
    moved = ProgressChange(
        "A1230", "Install pipe rack supports", 0.0, 50.0, 50.0, "TK_Active", "TK_Complete", 9.0, 4.0
    )
    marked = replace(cmp, progress_changes=(moved,), totals={**cmp.totals, "progress_changes": 1})
    assert st.compare_section_lines(marked, "progress_changes", technical=False) == [
        "~ A1230  0% to 50%  Active to Complete  Install pipe rack supports"
    ]
    assert st.compare_section_lines(marked, "progress_changes") == [
        "~ A1230  0% to 50%  TK_Active to TK_Complete  Install pipe rack supports"
    ]


def test_compare_screen_plain_names_snapshots_and_has_no_technical_tokens() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        text = screen_text(app)
        assert "Comparison of Snapshot 2" in text
        assert "Snapshot 2 (2026-10-12) against Snapshot 1 (2026-10-05)" in text
        assert "MAIN#" not in text
        assert "A2500  Weld inspection hold point" in text  # an activity id stays in both modes
        assert find_technical(text) == []

    scenario(world(), lambda c: CompareScreen(c, "P123", "MAIN", 2), steps)


def test_activity_screen_plain_title_status_and_detail() -> None:
    async def steps(pilot: Pilot[None], app: TlApp) -> None:
        text = screen_text(app)
        assert "Activities of Snapshot 2" in text
        assert "Snapshot 2  data date 2026-10-12  |  1-4 of 4 activities" in text
        assert "A1220  Set rack foundations  |  Snapshot 2" in text
        assert "Completed" in text and "completed" not in text
        assert "TK_" not in text and "MAIN#" not in text
        await pilot.press("ctrl+d")  # technical on: the key and the raw status come back
        await settle(pilot)
        text = screen_text(app)
        assert "Activities of MAIN#2" in text and "completed" in text

    scenario(world(), lambda c: ActivityScreen(c, "P123", "MAIN"), steps)


def test_look_ahead_and_orphan_lines_plain_hide_ids() -> None:
    row = LookAheadRow(
        "A1110", "Fabricate valves", "P > W", "in_progress", "in_progress",
        "2026-08-24T08:00", "2026-11-09T16:00", -1.0, True, 65.0,
    )  # fmt: skip
    answer = LookAhead(
        "MAIN#2", 2, "2026-10-12T08:00", "2026-10-12", "2026-11-09", 4, (row,),
        {"in_progress": 1, "critical": 1, "total": 1},
    )  # fmt: skip
    plain = st.look_ahead_lines(answer, technical=False)
    assert plain[0] == "look-ahead Snapshot 2: 2026-10-12 to 2026-11-09 (4 weeks)"
    assert st.look_ahead_lines(answer)[0] == "look-ahead MAIN#2: 2026-10-12 to 2026-11-09 (4 weeks)"

    links = [
        OrphanedLink("L1", "R1", "A1990", 1, "gone"),
        OrphanedLink("L2", "R2", "A2000", None, "gone"),
    ]
    assert st.orphan_lines(links, technical=False) == [
        "orphaned links: 2",
        "  A1990  last seen in snapshot 1",
        "  A2000  last seen in snapshot -",
    ]
    assert st.orphan_lines(links, technical=True) == [
        "orphaned links: 2",
        "  A1990  last seen in snapshot 1  record R1  link L1",
        "  A2000  last seen in snapshot -  record R2  link L2",
    ]


def test_both_screens_redraw_on_the_mode_switch() -> None:
    client = world()

    async def compare_steps(pilot: Pilot[None], app: TlApp) -> None:
        assert "Snapshot 2 (2026-10-12) against Snapshot 1" in screen_text(app)
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert app.display_mode.technical is True
        assert "MAIN#2 (2026-10-12) against MAIN#1 (2026-10-05)" in screen_text(app)
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert "Snapshot 2 (2026-10-12) against Snapshot 1" in screen_text(app)
        assert "MAIN#" not in screen_text(app)

    scenario(client, lambda c: CompareScreen(c, "P123", "MAIN", 2), compare_steps)

    async def activity_steps(pilot: Pilot[None], app: TlApp) -> None:
        assert "Activities of Snapshot 2" in screen_text(app)
        await pilot.press("ctrl+d")
        await settle(pilot)
        text = screen_text(app)
        assert "Activities of MAIN#2" in text and "A1220  Set rack foundations  |  MAIN#2" in text
        await pilot.press("ctrl+d")
        await settle(pilot)
        text = screen_text(app)
        assert "Activities of Snapshot 2" in text and "MAIN#" not in text

    scenario(client, lambda c: ActivityScreen(c, "P123", "MAIN"), activity_steps)


def _look_ahead(phase: str) -> LookAhead:
    """A look-ahead of snapshot 2 with one critical activity in the given phase."""
    row = LookAheadRow(
        "A1110", "Fabricate valves", "P > W", "in_progress", phase,
        "2026-08-24T08:00", "2026-11-09T16:00", -1.0, True, 65.0,
    )  # fmt: skip
    return LookAhead(
        "MAIN#2", 2, "2026-10-12T08:00", "2026-10-12", "2026-11-09", 4, (row,),
        {"total": 1},
    )  # fmt: skip


def test_look_ahead_phase_words_plain_and_raw_technical() -> None:
    phases = {
        "in_progress": "In progress",
        "late_start": "Late start",
        "starting": "Starting",
        "not_started": "Not started",
        "completed": "Completed",
    }
    for code, words in phases.items():
        plain = st.look_ahead_lines(_look_ahead(code), technical=False)
        assert f"  A1110  {words}  2026-08-24 to 2026-11-09  float -1d  65%  CRITICAL" in plain[2]
        raw = st.look_ahead_lines(_look_ahead(code))
        assert f"  A1110  {code}  2026-08-24 to 2026-11-09  float -1d  65%  CRITICAL" in raw[2]


def test_percent_type_words_plain_and_raw_technical() -> None:
    detail = world().get_schedule_activity("P123", "MAIN", "A1230")
    for code, words in {"CP_Drtn": "Duration", "CP_Phys": "Physical", "CP_Units": "Units"}.items():
        changed = replace(detail, activity=replace(detail.activity, percent_type=code))
        plain = st.activity_detail_lines(changed, technical=False)
        assert plain[1] == f"Task  Not started  0% ({words})  |  WBS P > W"
        raw = st.activity_detail_lines(changed)
        assert raw[1] == f"task  not_started  0% ({code})  |  WBS P > W"


def test_relationship_words_plain_and_raw_technical() -> None:
    detail = world().get_schedule_activity("P123", "MAIN", "A1230")
    words = {
        "FS": "Finish to start",
        "SS": "Start to start",
        "FF": "Finish to finish",
        "SF": "Start to finish",
    }
    for code, label in words.items():
        changed = replace(
            detail,
            predecessors=[replace(detail.predecessors[0], relationship_type=code)],
        )
        plain = st.activity_detail_lines(changed, technical=False)
        assert f"  A1220  {label}  lag 0h" in plain
        assert f"  A1220  {code}  lag 0h" in st.activity_detail_lines(changed)
        cmp = world().compare_snapshots("P123", "MAIN")
        moved = LogicChange("changed", "A1230", "A2500", code, "SS", 0.0, 0.0)
        marked = replace(cmp, logic_changes=(moved,), totals={**cmp.totals, "logic_changes": 1})
        assert st.compare_section_lines(marked, "logic_changes", technical=False) == [
            f"changed A1230 -> A2500  {label} to Start to start"
        ]
        assert st.compare_section_lines(marked, "logic_changes") == [
            f"changed A1230 -> A2500  {code} to SS"
        ]


def test_schedule_screen_look_ahead_header_plain_then_technical() -> None:
    client = world()
    client.put_look_ahead("P123", "MAIN", _look_ahead("in_progress"))
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=True)

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f12")
        await settle(pilot)
        await pilot.press("l")
        await settle(pilot)
        text = screen_text(app)
        assert "look-ahead Snapshot 2: 2026-10-12 to 2026-11-09 (4 weeks)" in text
        assert "A1110  In progress" in text
        await pilot.press("ctrl+d")
        await settle(pilot)
        assert "look-ahead MAIN#2: 2026-10-12 to 2026-11-09 (4 weeks)" in screen_text(app)
        assert "A1110  in_progress" in screen_text(app)

    run_pilot(app, go)
