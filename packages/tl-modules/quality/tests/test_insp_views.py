"""The inspection and checklist read views (P2-INSP T01). Every row is made by a real command."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from insp_world import IWP, QUESTIONS, InspWorld, answers
from sqlalchemy import event
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_quality import insp_views
from tl_mod_quality.insp_views import (
    EXPORT_COLUMNS,
    ChecklistDetail,
    ChecklistPage,
    InspectionDetail,
    InspectionPage,
    InspectionRow,
    checklist_detail,
    checklist_list,
    export_rows,
    inspection_counts,
    inspection_detail,
    inspection_list,
    inspections_for,
)

SCOPE = "project:P123"
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
STATEMENTS = ("BEGIN", "COMMIT", "ROLLBACK")


def key(n: int) -> str:
    return f"P123-INS-{n:04d}"


def chk(n: int) -> str:
    return f"P123-CHK-{n:04d}"


class Built:
    """Seven visible inspections and one on a restricted record (number 4)."""

    def __init__(self, world: InspWorld) -> None:
        self.world = world
        self.iwp1 = world.record(IWP, "IWP-1")
        self.iwp2 = world.record(IWP, "IWP-2")
        self.secret = world.hidden_record()
        self.c1 = world.checklist(discipline="Piping")  # CHK-0001, Published
        world.checklist(publish=False, discipline="Civil", questions=[])  # CHK-0002, Draft
        world.call("sue", "ReviseChecklist", checklist=self.c1)  # CHK-0003, Draft, version 2
        self.i1 = world.scheduled(self.iwp1, self.c1, point="hold", area="A1")
        world.recorded(self.i1, answers=answers(q1="no", note="Gauge missing"))
        self.i2 = world.plan(self.iwp1, point="witness", area="A2")
        self.i3 = world.scheduled(self.iwp2, self.c1, point="surveillance", area="A1",
                                  for_iwp_id=self.iwp1)  # fmt: skip
        self.i4 = world.scheduled(self.secret, self.c1, who="dora", point="hold")
        self.i5 = world.plan(self.iwp2, point="review")
        world.call("sue", "CancelInspection", inspection=self.i5, reason="Work moved")
        self.i6 = str(world.call("uma", "ReinspectInspection", inspection=self.i1).stream_id)
        self.i7 = world.plan(self.iwp2, who="dora", for_iwp_id=self.secret, point="review")
        self.i8 = world.scheduled(self.iwp2, self.c1, point="witness")
        world.recorded(self.i8, answers=answers())
        world.call("sue", "VerifyInspection", inspection=self.i8)


@pytest.fixture
def built(insp: InspWorld) -> Built:
    return Built(insp)


def lst(world: InspWorld, **kw: Any) -> InspectionPage:
    with open_uow(world.db, readonly=True) as uow:
        return inspection_list(uow.conn(), SCOPE, **kw)


def det(world: InspWorld, number: str, scope: str = SCOPE, **kw: Any) -> InspectionDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return inspection_detail(uow.conn(), scope, number, **kw)


def need(world: InspWorld, number: str, **kw: Any) -> InspectionDetail:
    found = det(world, number, **kw)
    assert found is not None
    return found


def counts(world: InspWorld, scope: str = SCOPE, **kw: Any) -> dict[str, int]:
    with open_uow(world.db, readonly=True) as uow:
        return inspection_counts(uow.conn(), scope, **kw)


def for_record(world: InspWorld, record: str, **kw: Any) -> list[InspectionRow]:
    with open_uow(world.db, readonly=True) as uow:
        return inspections_for(uow.conn(), record, **kw)


def keys(page: InspectionPage) -> list[str]:
    return [r.key for r in page.rows]


def clists(world: InspWorld, scope: str = SCOPE, **kw: Any) -> ChecklistPage:
    with open_uow(world.db, readonly=True) as uow:
        return checklist_list(uow.conn(), scope, **kw)


def cdet(world: InspWorld, number: str, scope: str = SCOPE, **kw: Any) -> ChecklistDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return checklist_detail(uow.conn(), scope, number, **kw)


# --- lists -------------------------------------------------------------------------------------


def test_a_list_is_ordered_by_key_and_total_is_the_row_count(insp: InspWorld, built: Built) -> None:
    page = lst(insp)
    assert keys(page) == [key(n) for n in (1, 2, 3, 5, 6, 7, 8)]
    assert page.total == 7
    first = page.rows[0]
    assert (first.title, first.subject_key, first.for_key) == ("Flange make-up", "IWP-1", "IWP-1")
    assert (first.state, first.point, first.area) == ("Done", "hold", "A1")
    assert (first.scheduled_for, first.inspector, first.result) == (
        "2026-12-01",
        "M. Okafor",
        "reject",
    )
    assert first.done_on is not None and len(first.done_on) == 10 and first.punch_count == 1
    assert first.id == built.i1 and first.planned_on is None
    assert [r.state for r in page.rows] == [
        "Done",
        "Planned",
        "Scheduled",
        "Cancelled",
        "Planned",
        "Planned",
        "Verified",
    ]
    by_key = {r.key: r for r in page.rows}
    assert (by_key[key(3)].subject_key, by_key[key(3)].for_key) == ("IWP-2", "IWP-1")
    assert (by_key[key(2)].inspector, by_key[key(2)].result, by_key[key(2)].done_on) == (
        None,
        None,
        None,
    )
    assert (by_key[key(8)].result, by_key[key(8)].punch_count) == ("accept", 0)


def test_each_filter_narrows(insp: InspWorld, built: Built) -> None:
    assert keys(lst(insp, state="Planned")) == [key(2), key(6), key(7)]
    assert keys(lst(insp, state="Cancelled")) == [key(5)]
    assert keys(lst(insp, point="hold")) == [key(1), key(6)]
    assert keys(lst(insp, area="A1")) == [key(1), key(3), key(6)]
    assert keys(lst(insp, inspector="M. Okafor")) == [key(1), key(3), key(8)]
    assert keys(lst(insp, subject_key="IWP-2")) == [key(3), key(5), key(7), key(8)]
    assert keys(lst(insp, for_key="IWP-1")) == [key(1), key(2), key(3), key(6)]
    assert keys(lst(insp, state="Planned", point="review")) == [key(7)]
    nothing = lst(insp, subject_key="NOPE-1")
    assert (nothing.rows, nothing.total) == ([], 0)
    for kw in ({"state": "Planned"}, {"point": "hold"}, {"area": "A1"}):
        page = lst(insp, **kw)
        assert page.total == len(page.rows)


def test_an_unknown_state_or_point_is_a_value_error(insp: InspWorld, built: Built) -> None:
    with pytest.raises(ValueError):
        lst(insp, state="Bogus")
    with pytest.raises(ValueError):
        lst(insp, point="spot")


def test_limit_clamps_and_total_counts_before_it(insp: InspWorld, built: Built) -> None:
    page = lst(insp, limit=2)
    assert keys(page) == [key(1), key(2)] and page.total == 7
    assert len(lst(insp, limit=0).rows) == 1
    assert len(lst(insp, limit=-5).rows) == 1
    assert len(lst(insp, limit=100000).rows) == 7


def test_another_project_has_no_rows(insp: InspWorld, built: Built) -> None:
    with open_uow(insp.db, readonly=True) as uow:
        page = inspection_list(uow.conn(), "project:P999")
    assert (page.rows, page.total) == ([], 0)
    assert det(insp, key(1), scope="project:P999") is None


# --- detail and counts -------------------------------------------------------------------------


def test_detail_carries_the_answers_the_checklist_and_the_punch_items(
    insp: InspWorld, built: Built
) -> None:
    one = need(insp, key(1))
    assert one.row.key == key(1) and one.row.state == "Done"
    assert (one.checklist_key, one.checklist_version) == (chk(1), 1)
    assert [a["q"] for a in one.answers] == ["q1", "q2", "q3"]
    assert one.answers[0] == {"q": "q1", "value": "no", "note": "Gauge missing"}
    assert (one.recorded_by, one.verified_by, one.cancel_reason) == ("user:rob", None, None)
    assert one.done_at is not None and one.verified_on is None and one.note is None
    assert one.punch_keys == ["P123-PUN-0001"] and one.reinspection_of_key is None
    assert one.version == insp.version(built.i1)
    two = need(insp, key(2))
    assert (two.checklist_key, two.checklist_version, two.answers) == (None, None, [])
    assert (two.punch_keys, two.recorded_by, two.done_at) == ([], None, None)
    assert need(insp, key(6)).reinspection_of_key == key(1)
    assert need(insp, key(5)).cancel_reason == "Work moved"
    eight = need(insp, key(8))
    assert (eight.verified_by, eight.recorded_by) == ("user:sue", "user:rob")
    assert eight.verified_on is not None and eight.row.result == "accept"


def test_a_failing_required_answer_is_listed_by_question_text_and_note(
    insp: InspWorld, built: Built
) -> None:
    # i1 is Done with q1 = "no" (required, fails when "no") and the note "Gauge missing"
    assert need(insp, key(1)).failed == [
        insp_views.FailedAnswer(question="Gauge fitted?", note="Gauge missing")
    ]


def test_a_passing_or_unrecorded_inspection_has_no_failed_answers(
    insp: InspWorld, built: Built
) -> None:
    assert need(insp, key(8)).failed == []  # Verified, every answer passes
    assert need(insp, key(2)).failed == []  # Planned, no answers recorded


def test_an_unknown_key_gives_none(insp: InspWorld, built: Built) -> None:
    assert det(insp, key(9999)) is None


def test_counts_hold_all_five_states(insp: InspWorld, built: Built) -> None:
    assert counts(insp) == {"Planned": 3, "Scheduled": 1, "Done": 1, "Verified": 1, "Cancelled": 1}
    assert counts(insp, scope="project:P999") == dict.fromkeys(
        ("Planned", "Scheduled", "Done", "Verified", "Cancelled"), 0
    )


# --- hidden looks like missing -----------------------------------------------------------------


def test_an_inspection_on_a_restricted_record_looks_like_a_key_that_never_existed(
    insp: InspWorld, built: Built
) -> None:
    assert key(4) not in keys(lst(insp)) and lst(insp).total == 7
    assert det(insp, key(4)) is None
    assert det(insp, key(4)) == det(insp, key(9999))
    assert sum(counts(insp).values()) == 7 and counts(insp)["Scheduled"] == 1
    assert keys(lst(insp, state="Scheduled")) == [key(3)]
    assert keys(lst(insp, point="hold")) == [key(1), key(6)]
    assert lst(insp, state="Scheduled").total == 1
    # a cleared viewer sees it everywhere
    page = lst(insp, viewer=CLEARED)
    assert keys(page) == [key(n) for n in range(1, 9)] and page.total == 8
    seen = need(insp, key(4), viewer=CLEARED)
    assert seen.row.state == "Scheduled" and seen.row.id == built.i4
    assert counts(insp, viewer=CLEARED)["Scheduled"] == 2
    assert lst(insp, state="Scheduled", limit=1, viewer=CLEARED).total == 2


def test_hidden_inspections_go_before_limit_and_count(insp: InspWorld, built: Built) -> None:
    page = lst(insp, limit=4)
    assert keys(page) == [key(1), key(2), key(3), key(5)] and page.total == 7
    assert keys(lst(insp, limit=4, viewer=CLEARED)) == [key(1), key(2), key(3), key(4)]


def test_the_default_viewer_is_the_lowest_clearance_everywhere() -> None:
    for name in (
        "inspection_list",
        "inspection_detail",
        "inspection_counts",
        "inspections_for",
        "checklist_list",
        "checklist_detail",
    ):
        parameter = inspect.signature(getattr(insp_views, name)).parameters["viewer"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is cf.LOWEST, name


def test_a_work_package_the_viewer_may_not_read_has_no_key_in_a_row(
    insp: InspWorld, built: Built
) -> None:
    # number 7 is about an open record, for a restricted work package: visible, but not its key
    seven = next(r for r in lst(insp).rows if r.key == key(7))
    assert seven.subject_key == "IWP-2" and seven.for_key is None
    assert need(insp, key(7)).row.for_key is None
    assert keys(lst(insp, for_key=insp.rows("SELECT key FROM cur_core_record WHERE id = :i",
                                            i=built.secret)[0]["key"])) == []  # fmt: skip
    cleared = next(r for r in lst(insp, viewer=CLEARED).rows if r.key == key(7))
    assert cleared.for_key == insp.rows("SELECT key FROM cur_core_record WHERE id = :i",
                                        i=built.secret)[0]["key"]  # fmt: skip


# --- inspections for a record ------------------------------------------------------------------


def test_inspections_for_a_record_are_those_that_name_it_as_subject_or_work_package(
    insp: InspWorld, built: Built
) -> None:
    rows = for_record(insp, built.iwp1)
    assert [r.key for r in rows] == [key(1), key(2), key(3), key(6)]
    assert [r.key for r in for_record(insp, built.iwp2)] == [key(3), key(5), key(7), key(8)]
    assert for_record(insp, "no-such-id") == []
    assert rows[0] == lst(insp).rows[0]


def test_inspections_for_a_restricted_record_read_as_none_until_cleared(
    insp: InspWorld, built: Built
) -> None:
    assert for_record(insp, built.secret) == []
    assert [r.key for r in for_record(insp, built.secret, viewer=CLEARED)] == [key(4), key(7)]


# --- checklists --------------------------------------------------------------------------------


def test_the_checklist_list_is_ordered_by_key_with_the_question_count(
    insp: InspWorld, built: Built
) -> None:
    page = clists(insp)
    assert [r.key for r in page.rows] == [chk(1), chk(2), chk(3)] and page.total == 3
    one, two, three = page.rows
    assert (one.title, one.discipline, one.version, one.state, one.question_count) == (
        "Hydrotest pre-check",
        "Piping",
        1,
        "Published",
        3,
    )
    assert (two.discipline, two.state, two.question_count) == ("Civil", "Draft", 0)
    assert (three.version, three.state, three.question_count) == (2, "Draft", 3)
    assert one.id == built.c1
    assert [r.key for r in clists(insp, state="Draft").rows] == [chk(2), chk(3)]
    assert [r.key for r in clists(insp, discipline="Piping").rows] == [chk(1), chk(3)]
    assert clists(insp, limit=1).total == 3 and len(clists(insp, limit=1).rows) == 1
    assert clists(insp, scope="project:P999").total == 0
    with pytest.raises(ValueError):
        clists(insp, state="Bogus")


def test_checklist_detail_has_the_questions_and_the_chain_of_versions(
    insp: InspWorld, built: Built
) -> None:
    one = cdet(insp, chk(1))
    assert one is not None and one.row.key == chk(1)
    assert one.questions == QUESTIONS
    assert (one.published_by, one.retired_on, one.supersedes_key) == ("user:sue", None, None)
    assert one.published_on is not None and one.record_version == insp.version(built.c1)
    three = cdet(insp, chk(3))
    assert three is not None and three.supersedes_key == chk(1) and three.published_by is None
    assert cdet(insp, chk(9999)) is None and cdet(insp, chk(1), scope="project:P999") is None


# --- exports -----------------------------------------------------------------------------------


def test_csv_and_jsonl_have_the_same_rows_as_the_list(insp: InspWorld, built: Built) -> None:
    rows = lst(insp).rows
    lines = export_rows(rows, "csv").splitlines()
    assert lines[0] == ",".join(EXPORT_COLUMNS)
    assert len(lines) == 1 + len(rows) == 8
    assert lines[1].startswith(f"{key(1)},IWP-1,IWP-1,hold,Done,reject,2026-12-01,")
    assert lines[1].endswith(",M. Okafor,1")
    records = [json.loads(line) for line in export_rows(rows, "jsonl").splitlines()]
    assert [r["number"] for r in records] == [r.key for r in rows]
    assert all(list(r) == list(EXPORT_COLUMNS) for r in records)
    assert records[0]["subject"] == "IWP-1" and records[0]["punch_count"] == 1
    assert records[1]["result"] is None and records[1]["inspector"] is None
    assert export_rows(rows, "jsonl").endswith("\n")
    assert key(4) not in export_rows(rows, "csv")


def test_an_export_of_nothing_is_the_header_or_empty_and_a_format_is_checked(
    insp: InspWorld, built: Built
) -> None:
    assert export_rows([], "csv") == ",".join(EXPORT_COLUMNS) + "\n"
    assert export_rows([], "jsonl") == ""
    with pytest.raises(ValueError):
        export_rows([], "xlsx")


def test_a_cell_that_starts_like_a_formula_is_neutralised_in_csv_only(
    insp: InspWorld, built: Built
) -> None:
    row = replace(lst(insp).rows[0], inspector="=HYPERLINK(1)", area="+1", subject_key="@a")
    csv_line = export_rows([row], "csv").splitlines()[1]
    assert "'=HYPERLINK(1)" in csv_line and "'@a" in csv_line
    assert json.loads(export_rows([row], "jsonl"))["inspector"] == "=HYPERLINK(1)"


# --- statements --------------------------------------------------------------------------------


def test_a_read_runs_at_most_two_statements(insp: InspWorld, built: Built) -> None:
    seen: list[str] = []

    def spy(*args: Any) -> None:
        text = str(args[2]).lstrip()
        if not text.upper().startswith(STATEMENTS):
            seen.append(text)

    calls: list[Callable[[Any], object]] = [
        lambda c: inspection_list(c, SCOPE),
        lambda c: inspection_list(c, SCOPE, state="Planned", viewer=CLEARED),
        lambda c: inspection_detail(c, SCOPE, key(1)),
        lambda c: inspection_counts(c, SCOPE),
        lambda c: inspections_for(c, built.iwp1),
        lambda c: checklist_list(c, SCOPE),
        lambda c: checklist_detail(c, SCOPE, chk(1)),
    ]
    with open_uow(insp.db, readonly=True) as uow:
        conn = uow.conn()
        event.listen(conn, "before_cursor_execute", spy)
        try:
            for call in calls:
                seen.clear()
                call(conn)
                assert 1 <= len(seen) <= 2, seen
        finally:
            event.remove(conn, "before_cursor_execute", spy)
