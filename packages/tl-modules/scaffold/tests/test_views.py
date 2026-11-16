"""The scaffold read views (P2-I4B T01). Every row of the ledger is made by a real command."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from scaffold_world import IWP, SCOPE, World
from sqlalchemy import event, text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_scaffold.views import (
    EXPORT_COLUMNS,
    ScaffoldDetail,
    ScaffoldPage,
    ScaffoldRow,
    due_list,
    export_rows,
    scaffold_detail,
    scaffold_list,
)

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
FAR = "2099-01-01"
PAST = "2000-01-01"
Built = dict[int, tuple[str, str]]  # n -> (scaffold id, key of its request)


def key(n: int) -> str:
    return f"P123-SCF-{n:04d}"


def key_of(world: World, record: str) -> str:
    return str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))


def lst(world: World, **kw: Any) -> ScaffoldPage:
    with open_uow(world.db, readonly=True) as uow:
        return scaffold_list(uow.conn(), SCOPE, **kw)


def det(world: World, number: str, scope: str = SCOPE, **kw: Any) -> ScaffoldDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return scaffold_detail(uow.conn(), scope, number, **kw)


def need(world: World, number: str, **kw: Any) -> ScaffoldDetail:
    found = det(world, number, **kw)
    assert found is not None
    return found


def due(world: World, today: str, **kw: Any) -> list[ScaffoldRow]:
    with open_uow(world.db, readonly=True) as uow:
        return due_list(uow.conn(), SCOPE, today, **kw)


def keys(found: ScaffoldPage | list[ScaffoldRow]) -> list[str]:
    rows = found.rows if isinstance(found, ScaffoldPage) else found
    return [r.key for r in rows]


def make(world: World, built: Built, n: int, to: str | None = None, **more: Any) -> str:
    """Scaffold number ``n``: registered from its own request, driven to ``to`` if given."""
    request = world.request(**more)
    sid = world.register(request, location_text=f"Unit {n}")
    assert key_of(world, sid) == key(n)
    built[n] = (sid, key_of(world, request))
    if to is not None:
        world.advance(sid, to)
    return sid


@pytest.fixture
def built(world: World) -> Built:
    """Five scaffolds: 1 Requested, 2 Designed (its request serves an IWP), 3 Erecting,
    4 Inspected (green), 5 In Use after a conditional inspection (yellow)."""
    b: Built = {}
    iwp = world.record(IWP, "IWP-1")
    make(world, b, 1)
    make(world, b, 2, "Designed", for_record_id=iwp)
    make(world, b, 3, "Erecting")
    make(world, b, 4, "Inspected")
    five = make(world, b, 5, "In Use")
    world.call("uma", "InspectScaffold", scaffold=five, result="conditional", note="Toe boards")
    return b


def hidden_scaffold(world: World) -> str:
    """A scaffold, Inspected, whose request serves a restricted record (the subject is set by a
    projection write: an IWP is not confidential today and the rule is generic in the subject)."""
    request = world.request()
    subject = world.hidden_record()
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_requisitions_scaffold_request SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": request},
        )
    sid = world.register(request, who="dora")
    world.advance_as(sid, "Erecting", "dora")
    world.call("dora", "TagScaffoldGreen", scaffold=sid)
    return sid


# --- the list ---


def test_the_list_is_ordered_by_key_and_carries_the_row(world: World, built: Built) -> None:
    page = lst(world)
    assert keys(page) == [key(n) for n in range(1, 6)] and page.total == 5
    one, four, five = page.rows[0], page.rows[3], page.rows[4]
    assert (four.id, four.state, four.tag, four.subject) == (
        built[4][0],
        "Inspected",
        "green",
        "Scaffold A",
    )
    assert four.location == "Unit 4" and four.request_key == built[4][1]
    assert four.last_inspected_on == four.tagged_on and four.next_due_on is not None
    assert (one.state, one.tag, one.tagged_on, one.last_inspected_on) == (
        "Requested",
        None,
        None,
        None,
    )
    assert (one.elevation, one.gridline, one.load_class) == ("+12.0", "C-4", "Light")
    assert (five.state, five.tag) == ("In Use", "yellow")


def test_filters_by_state_and_tag(world: World, built: Built) -> None:
    assert keys(lst(world, state="Requested")) == [key(1)]
    assert keys(lst(world, state="In Use")) == [key(5)]
    assert keys(lst(world, tag="green")) == [key(4)]
    assert keys(lst(world, tag="yellow")) == [key(5)]
    assert keys(lst(world, tag="red")) == []
    assert lst(world, state="Erecting", tag="green").total == 0
    with pytest.raises(ValueError):
        lst(world, state="Standing")
    with pytest.raises(ValueError):
        lst(world, tag="blue")


def test_overdue_needs_today_and_means_a_standing_scaffold_past_its_day(
    world: World, built: Built
) -> None:
    with pytest.raises(ValueError):
        lst(world, overdue=True)
    assert keys(lst(world, overdue=True, today=FAR)) == [key(4), key(5)]
    assert keys(lst(world, overdue=True, today=PAST)) == []
    assert lst(world, overdue=True, today=FAR).total == 2


def test_total_counts_before_the_limit_and_the_limit_is_clamped(world: World, built: Built) -> None:
    page = lst(world, limit=2)
    assert keys(page) == [key(1), key(2)] and page.total == 5
    assert len(lst(world, limit=0).rows) == 1
    assert len(lst(world, limit=100000).rows) == 5


# --- the detail ---


def test_detail_has_the_row_the_counts_and_the_inspections(world: World, built: Built) -> None:
    four = need(world, key(4))
    assert four.row.id == built[4][0] and four.row.state == "Inspected"
    assert four.inspection_count == 1 and four.version >= 1
    assert four.for_key is None and four.modify_reason is None and four.dismantle_reason is None
    (found,) = four.inspections
    assert (found.key, found.result, found.tag, found.inspector) == (
        "P123-SCI-0001",
        "pass",
        "green",
        "user:sue",
    )
    assert found.inspected_on == four.row.last_inspected_on and found.note is None
    five = need(world, key(5))
    assert [(i.result, i.tag, i.note) for i in five.inspections] == [
        ("pass", "green", None),
        ("conditional", "yellow", "Toe boards"),
    ]
    assert five.inspection_count == 2


def test_detail_names_the_record_the_request_serves_and_the_reasons(
    world: World, built: Built
) -> None:
    assert need(world, key(2)).for_key == "IWP-1"
    assert need(world, key(1)).inspections == []
    world.call("uma", "ModifyScaffold", scaffold=built[5][0], reason="Add a lift")
    assert need(world, key(5)).modify_reason == "Add a lift"
    world.call("uma", "DismantleScaffold", scaffold=built[4][0], reason="Work done")
    found = need(world, key(4))
    assert found.dismantle_reason == "Work done" and found.row.state == "Dismantle"


def test_an_unknown_key_and_a_key_of_another_project_give_none(world: World, built: Built) -> None:
    assert det(world, "P123-SCF-0099") is None
    assert det(world, key(1), scope="project:P999") is None


# --- the due list ---


def test_the_due_list_holds_standing_scaffolds_due_on_or_before_today(
    world: World, built: Built
) -> None:
    day = need(world, key(4)).row.next_due_on
    assert day is not None
    before = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    assert keys(due(world, day)) == [key(4), key(5)]
    assert keys(due(world, before)) == []
    assert keys(due(world, FAR)) == [key(4), key(5)]  # never Requested, Designed or Erecting
    assert keys(due(world, FAR, limit=1)) == [key(4)]
    world.call("uma", "ModifyScaffold", scaffold=built[5][0], reason="Add a lift")
    assert keys(due(world, FAR)) == [key(4), key(5)]  # Modify stands too
    world.call("uma", "DismantleScaffold", scaffold=built[4][0], reason="Work done")
    assert keys(due(world, FAR)) == [key(5)]  # a scaffold being taken down is not inspected


# --- confidentiality: hidden looks like missing ---


def test_a_hidden_scaffold_is_absent_for_the_lowest_viewer_and_present_for_a_cleared_one(
    world: World, built: Built
) -> None:
    number = key_of(world, hidden_scaffold(world))
    assert number == key(6)
    page = lst(world)
    assert key(6) not in keys(page) and page.total == 5
    assert key(6) not in keys(lst(world, overdue=True, today=FAR))
    assert key(6) not in keys(due(world, FAR))
    assert det(world, number) is None
    seen = lst(world, viewer=CLEARED)
    assert keys(seen)[-1] == key(6) and seen.total == 6
    assert key(6) in keys(due(world, FAR, viewer=CLEARED))
    assert len(need(world, number, viewer=CLEARED).inspections) == 1
    assert det(world, key(1), viewer=CLEARED) is not None


# --- bounds ---


def count_statements(world: World, run: Callable[[Any], object]) -> int:
    seen: list[str] = []

    def listen(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
        seen.append(statement)

    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        event.listen(conn, "before_cursor_execute", listen)
        try:
            run(conn)
        finally:
            event.remove(conn, "before_cursor_execute", listen)
    return len(seen)


def test_each_read_runs_a_fixed_number_of_statements(world: World, built: Built) -> None:
    assert count_statements(world, lambda c: scaffold_list(c, SCOPE)) <= 2
    assert count_statements(world, lambda c: scaffold_detail(c, SCOPE, key(5))) <= 2
    assert count_statements(world, lambda c: due_list(c, SCOPE, FAR)) <= 1


# --- the export ---


def row(**more: Any) -> ScaffoldRow:
    fields: dict[str, Any] = dict.fromkeys(EXPORT_COLUMNS)
    fields.update(id="01JX", key="P123-SCF-0042", subject="Scaffold A", state="Erecting")
    fields.update(more)
    return ScaffoldRow(**fields)


def test_csv_has_the_header_and_one_line_per_row_and_never_the_id(
    world: World, built: Built
) -> None:
    out = export_rows(lst(world).rows, "csv")
    lines = out.split("\n")
    assert lines[0] == ",".join(EXPORT_COLUMNS) and lines[-1] == ""
    assert len(lines) == 7 and "\r" not in out
    assert built[4][0] not in out
    parsed = list(csv.DictReader(io.StringIO(out)))
    assert [p["key"] for p in parsed] == [key(n) for n in range(1, 6)]
    four = parsed[3]
    assert (four["state"], four["tag"], four["location"]) == ("Inspected", "green", "Unit 4")
    assert four["request_key"] == built[4][1] and parsed[0]["tag"] == ""
    assert list(parsed[0]) == list(EXPORT_COLUMNS)


def test_csv_quotes_and_guards_against_formulas() -> None:
    out = export_rows(
        [row(subject="Unit 4, north", location="=1+1"), row(subject="@cmd", tag="-1")], "csv"
    )
    parsed = list(csv.DictReader(io.StringIO(out)))
    assert parsed[0]["subject"] == "Unit 4, north"
    assert parsed[0]["location"] == "'=1+1"
    assert parsed[1]["subject"] == "'@cmd" and parsed[1]["tag"] == "'-1"
    assert parsed[0]["state"] == "Erecting"


def test_csv_guards_a_leading_tab_or_carriage_return() -> None:
    out = export_rows([row(location="\t=1+1", subject="\r=2")], "csv")
    parsed = list(csv.DictReader(io.StringIO(out, newline="")))
    assert parsed[0]["location"] == "'\t=1+1" and parsed[0]["subject"] == "'\r=2"


def test_jsonl_is_one_object_per_line_with_the_same_columns() -> None:
    out = export_rows([row(location="=1+1"), row(key="P123-SCF-0043", tag="green")], "jsonl")
    lines = out.split("\n")
    assert lines[-1] == "" and len(lines) == 3
    first, second = (json.loads(line) for line in lines[:2])
    assert list(first) == list(EXPORT_COLUMNS)
    assert first["tag"] is None and first["location"] == "=1+1"  # no csv guard in json
    assert second["key"] == "P123-SCF-0043" and second["tag"] == "green"


def test_an_empty_export_and_an_unknown_format() -> None:
    assert export_rows([], "csv") == ",".join(EXPORT_COLUMNS) + "\n"
    assert export_rows([], "jsonl") == ""
    for bad in ("xlsx", "CSV", ""):
        with pytest.raises(ValueError):
            export_rows([], bad)
