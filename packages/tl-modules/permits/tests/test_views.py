"""The permit read views (P2-PTW T01). Every row of the ledger is made by a real command.

The clock is a parameter: ``now`` is passed to every view, and the world's clock stands at 07:00
when the permits are issued (valid to 18:00 on the same day).
"""

from __future__ import annotations

import csv
import inspect
import io
import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from permit_world import IWP, SCOPE, START, World
from sqlalchemy import event
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_permits import views
from tl_mod_permits.views import (
    EXPORT_COLUMNS,
    PermitBoard,
    PermitDetail,
    PermitPage,
    PermitRow,
    export_rows,
    permit_board,
    permit_counts,
    permit_detail,
    permit_list,
    permits_for,
)

EARLY = START + timedelta(hours=1)  # 08:00, inside the shift
LATE = START + timedelta(hours=12)  # 19:00, after valid_until
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
Built = dict[int, tuple[str, str]]  # n -> (record id, key); 0 is the IWP the first permit is for


def key(n: int) -> str:
    return f"P123-PTW-{n:04d}"


def lst(world: World, now: datetime = EARLY, **kw: Any) -> PermitPage:
    with open_uow(world.db, readonly=True) as uow:
        return permit_list(uow.conn(), SCOPE, now=now, **kw)


def det(world: World, number: str, now: datetime = EARLY, **kw: Any) -> PermitDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return permit_detail(uow.conn(), SCOPE, number, now=now, **kw)


def counts(world: World, now: datetime = EARLY, **kw: Any) -> dict[str, int]:
    with open_uow(world.db, readonly=True) as uow:
        return permit_counts(uow.conn(), SCOPE, now=now, **kw)


def board(world: World, area: str | None = None, now: datetime = EARLY, **kw: Any) -> PermitBoard:
    with open_uow(world.db, readonly=True) as uow:
        return permit_board(uow.conn(), SCOPE, area, now=now, **kw)


def keys(page: PermitPage) -> list[str]:
    return [r.key for r in page.rows]


def make(world: World, built: Built, n: int, who: str = "rob", **fields: Any) -> str:
    made = world.call(who, "RequestPermit", **fields)
    assert made.key == key(n)
    built[n] = (str(made.stream_id), str(made.key))
    return str(made.stream_id)


def fields(**more: Any) -> dict[str, Any]:
    return {
        "permit_type": "general",
        "area": "A1",
        "location_text": "Pump room",
        "work_description": "Weld repair",
        "holder": "Rob",
        "needed_from": "2026-12-01",
        "needed_until": "2026-12-03",
        **more,
    }


@pytest.fixture
def built(world: World) -> Built:
    """Six permits (0 is the IWP): 1 Active (A1), 2 Active (A2), 3 Suspended (A1), 4 Requested
    (A1), 5 Closed (A3), 6 Active and hidden (A1: its record is restricted)."""
    iwp = world.record(IWP, "IWP-1")
    secret = world.hidden_record()
    b: Built = {0: (iwp, "IWP-1")}
    make(world, b, 1, **fields(for_record_id=iwp))
    make(world, b, 2, **fields(area="A2", holder="Ann"))
    make(world, b, 3, **fields())
    make(world, b, 4, **fields(work_description="Trench"))
    make(world, b, 5, **fields(area="A3"))
    make(world, b, 6, "dora", **fields(for_record_id=secret))
    for n in (1, 2, 3, 5):
        world.call("sue", "ApprovePermit", permit=b[n][0])
        world.call("pam", "IssuePermit", permit=b[n][0], precautions=["jha_attached"])
    world.call("ada", "ApprovePermit", permit=b[6][0])
    world.call("ada", "IssuePermit", permit=b[6][0], precautions=["jha_attached"])
    world.call("uma", "SuspendPermit", permit=b[3][0], reason="Stop work")
    world.call("rob", "HandBackPermit", permit=b[5][0], handback_note="Site clear")
    world.call("pam", "ClosePermit", permit=b[5][0])
    return b


# --- list ----------------------------------------------------------------------------------------


def test_a_list_is_ordered_by_key_and_total_is_the_row_count(world: World, built: Built) -> None:
    page = lst(world)
    assert keys(page) == [key(n) for n in range(1, 6)]  # the sixth is hidden
    assert page.total == 5
    first = page.rows[0]
    assert (first.subject, first.permit_type, first.state) == ("Weld repair", "general", "Active")
    assert (first.area, first.holder, first.for_key) == ("A1", "Rob", "IWP-1")
    assert first.issued_at == START and first.valid_until == START.replace(hour=18)
    assert first.valid_until is not None and first.valid_until.tzinfo is not None
    assert (first.revalidation_count, first.closed_by) == (0, None)
    assert [r.state for r in page.rows] == ["Active", "Active", "Suspended", "Requested", "Closed"]
    assert page.rows[4].closed_by == "user:pam"
    assert page.rows[3].issued_at is None and page.rows[3].valid_until is None


def test_lapsed_is_shown_in_place_of_active_through_the_clock_parameter(
    world: World, built: Built
) -> None:
    assert [r.state for r in lst(world, EARLY).rows][:2] == ["Active", "Active"]
    late = lst(world, LATE)
    assert [r.state for r in late.rows] == ["Lapsed", "Lapsed", "Suspended", "Requested", "Closed"]
    at_the_edge = lst(world, START.replace(hour=18))  # valid_until is exclusive
    assert at_the_edge.rows[0].state == "Lapsed"
    just_before = lst(world, START.replace(hour=17, minute=59))
    assert just_before.rows[0].state == "Active"


def test_each_filter_narrows(world: World, built: Built) -> None:
    assert keys(lst(world, state="Active")) == [key(1), key(2)]
    assert keys(lst(world, state="Lapsed")) == []
    assert keys(lst(world, LATE, state="Lapsed")) == [key(1), key(2)]
    assert keys(lst(world, LATE, state="Active")) == []
    assert keys(lst(world, state="Suspended")) == [key(3)]
    assert keys(lst(world, state="Requested")) == [key(4)]
    assert keys(lst(world, area="A1")) == [key(1), key(3), key(4)]
    assert keys(lst(world, holder="Ann")) == [key(2)]
    assert keys(lst(world, permit_type="general", area="A3")) == [key(5)]
    assert keys(lst(world, permit_type="hot_work")) == []
    narrowings: list[dict[str, Any]] = [{"state": "Active"}, {"area": "A1"}, {"holder": "Rob"}]
    for kw in narrowings:
        page = lst(world, **kw)
        assert page.total == len(page.rows)


def test_limit_and_offset_page_the_rows_and_total_stays_whole(world: World, built: Built) -> None:
    page = lst(world, limit=2, offset=1)
    assert keys(page) == [key(2), key(3)]
    assert page.total == 5  # the hidden one is in neither the rows nor the total
    assert lst(world, limit=2, offset=4).total == 5
    assert keys(lst(world, limit=2, offset=4)) == [key(5)]


# --- detail --------------------------------------------------------------------------------------


def test_a_detail_has_the_row_and_the_trail_fields(world: World, built: Built) -> None:
    found = det(world, key(1))
    assert found is not None
    assert found.row.key == key(1) and found.row.state == "Active"
    assert (found.description, found.location_text) == ("Weld repair", "Pump room")
    assert (found.requested_by, found.approved_by, found.issued_by) == (
        "user:rob",
        "user:sue",
        "user:pam",
    )
    assert (found.needed_from, found.needed_until) == ("2026-12-01", "2026-12-03")
    assert found.precautions == ["jha_attached"] and found.version > 1
    suspended = det(world, key(3))
    assert suspended is not None and suspended.suspend_reason == "Stop work"
    closed = det(world, key(5))
    assert closed is not None and closed.handback_note == "Site clear"
    assert closed.row.state == "Closed"


def test_a_detail_shows_lapsed_and_is_none_for_an_unknown_or_foreign_number(
    world: World, built: Built
) -> None:
    lapsed = det(world, key(1), LATE)
    assert lapsed is not None and lapsed.row.state == "Lapsed"
    assert det(world, "P123-PTW-9999") is None
    with open_uow(world.db, readonly=True) as uow:
        assert permit_detail(uow.conn(), "project:P999", key(1), now=EARLY) is None


# --- counts and the board ------------------------------------------------------------------------


def test_counts_are_by_shown_state_with_zeros(world: World, built: Built) -> None:
    assert counts(world) == {
        "Requested": 1,
        "Approved": 0,
        "Active": 2,
        "Lapsed": 0,
        "Suspended": 1,
        "Handed back": 0,
        "Closed": 1,
        "Rejected": 0,
        "Cancelled": 0,
    }
    late = counts(world, LATE)
    assert (late["Active"], late["Lapsed"]) == (0, 2)
    assert list(late) == list(views.SHOWN_STATES)


def test_the_board_groups_live_permits_by_area_with_lapsed_and_suspended_first(
    world: World, built: Built
) -> None:
    shown = board(world, now=LATE)
    assert [a.area for a in shown.areas] == ["A1", "A2"]
    assert [r.key for r in shown.areas[0].rows] == [key(1), key(3)]
    assert [r.state for r in shown.areas[0].rows] == ["Lapsed", "Suspended"]
    assert [r.key for r in shown.areas[1].rows] == [key(2)]
    assert shown.counts == {"Lapsed": 2, "Suspended": 1, "Active": 0}
    early = board(world)
    assert [r.state for r in early.areas[0].rows] == ["Suspended", "Active"]
    assert early.counts == {"Lapsed": 0, "Suspended": 1, "Active": 2}


def test_the_board_narrows_to_one_area_and_counts_follow(world: World, built: Built) -> None:
    shown = board(world, "A1")
    assert [a.area for a in shown.areas] == ["A1"]
    assert shown.counts == {"Lapsed": 0, "Suspended": 1, "Active": 1}
    nothing = board(world, "A9")
    assert nothing.areas == [] and nothing.counts == {"Lapsed": 0, "Suspended": 0, "Active": 0}


# --- the hidden filter ---------------------------------------------------------------------------


def test_the_viewer_defaults_to_the_lowest_clearance() -> None:
    for name in ("permit_list", "permit_detail", "permit_counts", "permit_board", "permits_for"):
        parameter = inspect.signature(getattr(views, name)).parameters["viewer"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is cf.LOWEST, name


def test_the_clock_is_a_required_parameter_never_read_by_the_views() -> None:
    for name in ("permit_list", "permit_detail", "permit_counts", "permit_board"):
        parameter = inspect.signature(getattr(views, name)).parameters["now"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is inspect.Parameter.empty, name


def test_a_hidden_permit_is_absent_from_every_read_for_the_default_viewer(
    world: World, built: Built
) -> None:
    assert key(6) not in keys(lst(world)) and lst(world).total == 5
    assert det(world, key(6)) is None
    assert counts(world)["Active"] == 2
    assert key(6) not in [r.key for a in board(world).areas for r in a.rows]
    assert board(world).counts["Active"] == 2
    assert board(world, "A1").counts == {"Lapsed": 0, "Suspended": 1, "Active": 1}


def test_a_cleared_viewer_reads_the_hidden_permit_everywhere(world: World, built: Built) -> None:
    page = lst(world, viewer=CLEARED)
    assert keys(page) == [key(n) for n in range(1, 7)] and page.total == 6
    found = det(world, key(6), viewer=CLEARED)
    assert found is not None and found.row.area == "A1"
    assert counts(world, viewer=CLEARED)["Active"] == 3
    assert board(world, viewer=CLEARED).counts["Active"] == 3
    a1 = board(world, "A1", viewer=CLEARED).areas[0]
    assert [r.key for r in a1.rows] == [key(3), key(1), key(6)]


def test_the_filter_comes_before_limit_and_before_counting(world: World, built: Built) -> None:
    page = lst(world, area="A1", limit=1, offset=2)
    assert keys(page) == [key(4)] and page.total == 3  # keys 1, 3, 4 once the hidden 6 is out
    assert keys(lst(world, area="A1", limit=3)) == [key(1), key(3), key(4)]


def test_a_hidden_record_reads_as_no_rows_and_zero_counts(world: World) -> None:
    secret = world.hidden_record()
    made = world.call("dora", "RequestPermit", **fields(for_record_id=secret))
    world.call("ada", "ApprovePermit", permit=made.stream_id)
    world.call("ada", "IssuePermit", permit=made.stream_id, precautions=["jha_attached"])
    only = lst(world)
    assert (only.rows, only.total) == ([], 0)
    assert det(world, str(made.key)) is None
    assert sum(counts(world).values()) == 0
    shown = board(world)
    assert shown.areas == [] and sum(shown.counts.values()) == 0
    with open_uow(world.db, readonly=True) as uow:
        assert permits_for(uow.conn(), secret) == []
        assert [p.key for p in permits_for(uow.conn(), secret, viewer=CLEARED)] == [made.key]


def test_permits_for_lists_the_permits_of_a_record_with_the_stored_state(
    world: World, built: Built
) -> None:
    with open_uow(world.db, readonly=True) as uow:
        refs = permits_for(uow.conn(), built[0][0])
        assert [(r.key, r.permit_type, r.state) for r in refs] == [(key(1), "general", "Active")]
        assert refs[0].valid_until == START.replace(hour=18) and refs[0].id == built[1][0]
        assert permits_for(uow.conn(), "01JXXXXXXXXXXXXXXXXXXXXXXX") == []


# --- export --------------------------------------------------------------------------------------


def test_csv_and_jsonl_carry_the_same_rows_as_the_list(world: World, built: Built) -> None:
    rows = lst(world).rows
    parsed = list(csv.reader(io.StringIO(export_rows(rows, "csv"))))
    assert tuple(parsed[0]) == EXPORT_COLUMNS
    assert [line[0] for line in parsed[1:]] == [r.key for r in rows]
    first = dict(zip(EXPORT_COLUMNS, parsed[1], strict=True))
    assert (first["type"], first["state"], first["area"], first["holder"]) == (
        "general",
        "Active",
        "A1",
        "Rob",
    )
    assert datetime.fromisoformat(first["valid_until"]) == START.replace(hour=18)
    assert first["revalidations"] == "0" and first["closed"] == ""
    lines = export_rows(rows, "jsonl").splitlines()
    objects = [json.loads(line) for line in lines]
    assert [o["number"] for o in objects] == [r.key for r in rows]
    assert all(set(o) == set(EXPORT_COLUMNS) for o in objects)
    assert objects[0]["state"] == "Active" and objects[4]["closed"] == "user:pam"
    assert objects[3]["issued"] is None


def test_an_export_of_no_rows_is_the_header_or_nothing_and_a_bad_format_is_refused() -> None:
    assert export_rows([], "csv").strip() == ",".join(EXPORT_COLUMNS)
    assert export_rows([], "jsonl") == ""
    with pytest.raises(ValueError, match="csv or jsonl"):
        export_rows([], "xml")


# --- statements ----------------------------------------------------------------------------------


def statements(world: World, call: Any) -> list[str]:
    seen: list[str] = []
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()

        def on_execute(_c: Any, _cur: Any, statement: str, *_a: Any) -> None:
            word = statement.lstrip().split(None, 1)[0].upper()
            if word not in ("BEGIN", "COMMIT", "ROLLBACK"):
                seen.append(statement)

        event.listen(conn, "before_cursor_execute", on_execute)
        try:
            call(conn)
        finally:
            event.remove(conn, "before_cursor_execute", on_execute)
    return seen


def test_each_view_is_at_most_two_statements(world: World, built: Built) -> None:
    calls = {
        "list": lambda c: permit_list(c, SCOPE, now=EARLY),
        "filtered": lambda c: permit_list(c, SCOPE, now=EARLY, state="Lapsed", area="A1"),
        "detail": lambda c: permit_detail(c, SCOPE, key(1), now=EARLY),
        "counts": lambda c: permit_counts(c, SCOPE, now=EARLY),
        "board": lambda c: permit_board(c, SCOPE, "A1", now=EARLY),
        "for": lambda c: permits_for(c, built[0][0]),
    }
    for name, call in calls.items():
        assert len(statements(world, call)) <= 2, name


def test_the_row_types_are_frozen_dataclasses() -> None:
    for kind in (PermitRow, PermitDetail, PermitPage):
        assert vars(kind)["__dataclass_params__"].frozen
