"""INS-A1: ``record_activity``, the page of what happened around a record (P2-INS-S1).

The world is ``dev/accept/P2-INS/s1_world.py``: one IWP with edits, moves, links in both
directions, a file, a thread post, two proposals, a raised and cleared constraint and a readiness
evaluation; a linked IWP that moved (related rows) and a restricted record that blocks it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-INS"
sys.path.insert(0, str(ACCEPT))
import s1_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from sqlalchemy import event as sa_event  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.insights import activity as act  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402
from tl_core.insights.types import ActivityPage  # noqa: E402
from tl_core.services import queries  # noqa: E402

ALL_KINDS = {"change", "move", "link", "file", "post", "proposal", "constraint", "check"}
CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> sw.World:
    root = tmp_path_factory.mktemp("s1")
    built = sw.build(root)
    sw.upload(built)
    sw.propose_link(built, accept=True)
    sw.propose_link(built, accept=False)
    sw.add_hidden(built)
    return built


def read(
    world: sw.World, viewer: cf.Viewer = cf.LOWEST, record: str | None = None, **kw: Any
) -> ActivityPage:
    with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(viewer):
        return record_activity(uow, record or world.iwp, **kw)


def seqs(page: ActivityPage) -> list[int]:
    return [r.event.seq for r in page.rows]


def test_every_kind_appears_newest_first_and_a_related_row_names_its_record(
    world: sw.World,
) -> None:
    page = read(world)
    assert {r.kind for r in page.rows} == ALL_KINDS
    assert seqs(page) == sorted(seqs(page), reverse=True) and page.next_before_seq is None
    related = [r for r in page.rows if r.related]
    assert related and {r.from_key for r in related} == {"P123-IWP-PIP-0002"}
    assert {r.from_id for r in related} == {world.ids["far"]}
    assert {r.event.event_type for r in related} <= {
        "Workflow.Transitioned",
        "Technical.Answered",
        "Correspondence.Responded",
        "ResponseClock.Met",
        "Constraint.Cleared",
        "Proposal.Accepted",
    }
    assert set(act.RELATED_EVENT_TYPES) == {
        "Workflow.Transitioned",
        "Technical.Answered",
        "Correspondence.Responded",
        "ResponseClock.Met",
        "Constraint.Cleared",
        "Proposal.Accepted",
    }
    assert all(r.from_key is None for r in page.rows if not r.related)
    proposals = {r.event.event_type: r for r in page.rows if r.kind == "proposal"}
    assert proposals["Proposal.Accepted"].decided_by == "user:user"
    assert proposals["Proposal.Rejected"].decided_by == "user:user"
    assert proposals["Proposal.Created"].decided_by is None
    check = next(r for r in page.rows if r.kind == "check")
    assert check.note is not None and check.note.endswith(" ready") and " of " in check.note
    assert all(r.why is None for r in page.rows)


def test_the_link_events_of_both_ends_and_the_constraint_events_are_in(world: sw.World) -> None:
    page = read(world)
    streams = {r.event.stream_id for r in page.rows if r.kind == "link"}
    with open_uow(world.w.db, readonly=True) as uow, cf.system_view():
        rows = uow.conn().execute(
            text(
                "SELECT link_id FROM cur_links WHERE (from_id = :i OR to_id = :i) "
                "AND from_id <> :h AND to_id <> :h"
            ),
            {"i": world.iwp, "h": world.ids["hidden"]},
        )
        mine = {str(r[0]) for r in rows}
    assert mine - streams == set()  # a link of this record is a row, from either end
    constraint = [
        r.event.event_type for r in page.rows if r.event.stream_id == world.ids["constraint"]
    ]
    assert {"Constraint.Raised", "Constraint.Cleared"} <= set(constraint)


def test_revisions_only_is_the_record_history(world: sw.World) -> None:
    page = read(world, revisions_only=True)
    with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
        history = queries.record_history(uow, world.iwp)
    assert [r.event for r in reversed(page.rows)] == history
    assert not any(r.related for r in page.rows)
    assert len(page.rows) < len(read(world).rows)


def test_related_false_leaves_the_related_rows_out(world: sw.World) -> None:
    assert not any(r.related for r in read(world, related=False).rows)
    assert any(r.related for r in read(world).rows)


def test_pages_chain_with_a_strict_cursor_and_equal_one_big_page(world: sw.World) -> None:
    whole = seqs(read(world))
    got: list[int] = []
    cursor: int | None = None
    for _ in range(100):
        page = read(world, before_seq=cursor, limit=4)
        got += seqs(page)
        if page.next_before_seq is None:
            break
        assert len(page.rows) == 4  # hidden rows never leave a short page
        cursor = page.next_before_seq
    assert got == whole
    assert read(world, before_seq=whole[3], limit=2).rows[0].event.seq == whole[4]  # strict


def test_a_hidden_or_unknown_record_answers_an_empty_page(world: sw.World) -> None:
    hidden = world.ids["hidden"]
    assert read(world, record=hidden).rows == []
    assert read(world, record="01JNOSUCHRECORD000000000A").rows == []
    assert read(world, CONTROLLER, record=hidden).rows  # the controller reads it


def test_a_link_to_a_hidden_record_is_dropped_in_sql_at_either_end(world: sw.World) -> None:
    hidden = world.ids["hidden"]
    with open_uow(world.w.db, readonly=True) as uow:
        with cf.use_viewer(cf.LOWEST):
            far = act._far_ends(uow.conn(), world.iwp)  # pyright: ignore[reportPrivateUsage]
        with cf.use_viewer(CONTROLLER):
            seen = act._far_ends(uow.conn(), world.iwp)  # pyright: ignore[reportPrivateUsage]
    assert hidden not in far and world.ids["far"] in far
    assert hidden in seen and world.ids["far"] in seen


def test_a_hidden_record_costs_one_statement_and_no_lookup_of_its_links(world: sw.World) -> None:
    verbs: list[str] = []
    with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
        engine = uow.conn().engine

        def count(conn: Any, cursor: Any, statement: str, *a: Any) -> None:
            verbs.append(statement)

        sa_event.listen(engine, "before_cursor_execute", count)
        try:
            record_activity(uow, world.ids["hidden"])
        finally:
            sa_event.remove(engine, "before_cursor_execute", count)
    assert len(verbs) == 1


def test_a_hidden_far_end_leaves_no_row_no_gap_and_no_key(world: sw.World) -> None:
    low, ctl = read(world), read(world, CONTROLLER)
    hidden = world.ids["hidden"]
    with open_uow(world.w.db, readonly=True) as uow, cf.system_view():
        key = (
            uow.conn()
            .execute(text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": hidden})
            .scalar_one()
        )
    assert not any(r.from_id == hidden or r.from_key == key for r in low.rows)
    assert not any(hidden in r.event.stream_id or hidden in str(r.event.payload) for r in low.rows)
    assert any(r.from_id == hidden for r in ctl.rows)
    assert set(seqs(low)) < set(seqs(ctl))
    assert [
        r.event.event_id
        for r in ctl.rows
        if r.event.event_id in {x.event.event_id for x in low.rows}
    ] == [r.event.event_id for r in low.rows]


def test_the_related_quota_ends_a_page_without_losing_a_row(
    world: sw.World, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = seqs(read(world, limit=200))
    monkeypatch.setattr(act, "MAX_RELATED_ROWS", 1)
    got: list[int] = []
    cursor: int | None = None
    for _ in range(100):
        page = read(world, before_seq=cursor, limit=200)
        assert sum(r.related for r in page.rows) <= 1
        got += seqs(page)
        if page.next_before_seq is None:
            break
        cursor = page.next_before_seq
    assert got == whole


def test_the_candidate_cap_stops_a_call_with_a_cursor(
    world: sw.World, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = seqs(read(world, limit=200))
    monkeypatch.setattr(act, "MAX_CANDIDATES", 6)
    page = read(world, limit=200)
    assert page.next_before_seq is not None and len(page.rows) <= 6
    rest = seqs(page)
    while page.next_before_seq is not None:
        page = read(world, before_seq=page.next_before_seq, limit=200)
        rest += seqs(page)
    assert rest == whole


@pytest.mark.parametrize("viewer", ["default", "user", "agent", "controller", "admin"])
def test_the_batched_filter_keeps_what_filter_events_keeps(world: sw.World, viewer: str) -> None:
    from c2_checks import VIEWERS  # pyright: ignore[reportMissingImports]

    with open_uow(world.w.db, readonly=True) as uow, cf.system_view():
        events = [r.event for r in record_activity(uow, world.iwp, limit=200).rows]
        events += [r.event for r in record_activity(uow, world.ids["hidden"], limit=200).rows]
    with open_uow(world.w.db, readonly=True) as uow:
        conn = uow.conn()
        want = cf.filter_events(conn, events, VIEWERS[viewer])
        with cf.use_viewer(VIEWERS[viewer]):
            got = act._visible(conn, events)  # pyright: ignore[reportPrivateUsage]
    assert [e.event_id for e in got] == [e.event_id for e in want]


def test_the_read_writes_nothing_and_the_statement_count_is_fixed(world: sw.World) -> None:
    verbs: list[str] = []
    with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
        engine = uow.conn().engine

        def count(conn: Any, cursor: Any, statement: str, *a: Any) -> None:
            verbs.append(statement.lstrip().split(None, 1)[0].upper())

        sa_event.listen(engine, "before_cursor_execute", count)
        try:
            record_activity(uow, world.iwp)
        finally:
            sa_event.remove(engine, "before_cursor_execute", count)
    assert set(verbs) == {"SELECT"} and 0 < len(verbs) <= 40


def test_the_page_has_the_same_shape_on_both_adapters(db: str | Path, tmp_path: Path) -> None:
    built = sw.build(tmp_path, db)
    page = read(built, CONTROLLER)
    assert {r.kind for r in page.rows} == ALL_KINDS - {"file", "proposal"}
    assert seqs(page) == sorted(seqs(page), reverse=True) and page.next_before_seq is None
    assert any(r.related and r.from_key == "P123-IWP-PIP-0002" for r in page.rows)
    assert read(built, revisions_only=True).rows[-1].event.event_type == "Record.Created"
