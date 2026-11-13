"""The punch read views (P2-PUNCH T01). Every row of the ledger is made by a real command."""

from __future__ import annotations

from typing import Any

import pytest
from punch_world import IWP, SCOPE, World
from sqlalchemy import event
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_quality.views import (
    PunchDetail,
    PunchPage,
    punch_counts,
    punch_detail,
    punch_list,
)

TODAY = "2026-12-01"
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
Built = dict[int, tuple[str, str]]  # n -> (record id, key)


def key(n: int) -> str:
    return f"P123-PUN-{n:04d}"


def lst(world: World, **kw: Any) -> PunchPage:
    with open_uow(world.db, readonly=True) as uow:
        return punch_list(uow.conn(), SCOPE, **kw)


def det(world: World, number: str, scope: str = SCOPE, **kw: Any) -> PunchDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return punch_detail(uow.conn(), scope, number, **kw)


def need(world: World, number: str, **kw: Any) -> PunchDetail:
    found = det(world, number, **kw)
    assert found is not None
    return found


def counts(world: World, **kw: Any) -> dict[str, int]:
    with open_uow(world.db, readonly=True) as uow:
        return punch_counts(uow.conn(), SCOPE, **kw)


def keys(page: PunchPage) -> list[str]:
    return [r.key for r in page.rows]


def raise_one(world: World, built: Built, n: int, who: str = "uma", **fields: Any) -> None:
    made = world.call(who, "RaisePunchItem", **fields)
    assert made.key == key(n)
    built[n] = (str(made.stream_id), str(made.key))


@pytest.fixture
def built(world: World) -> Built:
    """Five items: 1 Cleared, 2 Verified, 3 Open (overdue), 4 Void, 5 Open again after a reopen."""
    iwp1 = world.record(IWP, "IWP-1")
    iwp2 = world.record(IWP, "IWP-2")
    b: Built = {}
    raise_one(
        world, b, 1, subject="Guard missing", description="Pump P-101", area="A1",
        system="47-01", due_on="2026-11-20", category="A", assignee="user:rob",
        from_record_id=iwp1,
    )  # fmt: skip
    raise_one(
        world, b, 2, subject="Label faded", area="A2", system="47-02", due_on="2026-12-20",
        assignee="user:rob", from_record_id=iwp2,
    )  # fmt: skip
    raise_one(
        world, b, 3, subject="Paint chip", area="A1", system="47-01", due_on="2026-11-25",
        category="C", assignee="user:uma",
    )  # fmt: skip
    raise_one(world, b, 4, subject="Valve tag", area="A1")
    raise_one(world, b, 5, subject="Hose clamp", area="A3", due_on="2026-11-01")
    world.call("rob", "ClearPunchItem", punch_item=b[1][0], note="Guard fitted")
    world.call("rob", "ClearPunchItem", punch_item=b[2][0], note="Relabelled")
    world.call("sue", "VerifyPunchItem", punch_item=b[2][0])
    world.call("sue", "VoidPunchItem", punch_item=b[4][0], reason="Duplicate")
    world.call("rob", "ClearPunchItem", punch_item=b[5][0], note="Clamp fitted")
    world.call("sue", "ReopenPunchItem", punch_item=b[5][0], reason="Wrong size")
    return b


def test_a_list_is_ordered_by_key_and_total_is_the_row_count(world: World, built: Built) -> None:
    page = lst(world)
    assert keys(page) == [key(n) for n in range(1, 6)]
    assert page.total == 5
    first = page.rows[0]
    assert (first.subject, first.state, first.category) == ("Guard missing", "Cleared", "A")
    assert (first.area, first.system, first.due_on) == ("A1", "47-01", "2026-11-20")
    assert (first.assignee, first.raised_by, first.source_key) == ("user:rob", "user:uma", "IWP-1")
    assert [r.state for r in page.rows] == ["Cleared", "Verified", "Open", "Void", "Open"]
    assert [r.category for r in page.rows] == ["A", "B", "C", "B", "B"]


def test_each_filter_narrows(world: World, built: Built) -> None:
    assert keys(lst(world, state="Open")) == [key(3), key(5)]
    assert keys(lst(world, state="Void")) == [key(4)]
    assert keys(lst(world, area="A1")) == [key(1), key(3), key(4)]
    assert keys(lst(world, system="47-01")) == [key(1), key(3)]
    assert keys(lst(world, assignee="user:rob")) == [key(1), key(2)]
    assert keys(lst(world, category="A")) == [key(1)]
    assert keys(lst(world, source_key="IWP-1")) == [key(1)]
    assert keys(lst(world, state="Open", area="A1")) == [key(3)]
    nothing = lst(world, source_key="NOPE-1")
    assert (nothing.rows, nothing.total) == ([], 0)
    for kw in ({"state": "Open"}, {"area": "A1"}, {"category": "B"}):
        page = lst(world, **kw)
        assert page.total == len(page.rows)


def test_overdue_means_open_and_due_before_today(world: World, built: Built) -> None:
    # item 1 is past due but Cleared, item 2 is Verified and due later: only Open ones count
    assert keys(lst(world, overdue=True, today=TODAY)) == [key(3), key(5)]
    assert keys(lst(world, overdue=True, today="2026-11-10")) == [key(5)]
    assert lst(world, overdue=True, today="2026-10-01").rows == []
    assert lst(world, overdue=True, today=TODAY).total == 2
    with pytest.raises(ValueError):
        lst(world, overdue=True)


def test_limit_clamps_and_total_counts_before_it(world: World, built: Built) -> None:
    page = lst(world, limit=2)
    assert keys(page) == [key(1), key(2)] and page.total == 5
    assert len(lst(world, limit=0).rows) == 1
    assert len(lst(world, limit=-5).rows) == 1
    assert len(lst(world, limit=100000).rows) == 5


def test_an_unknown_state_or_category_is_a_value_error(world: World, built: Built) -> None:
    with pytest.raises(ValueError):
        lst(world, state="Bogus")
    with pytest.raises(ValueError):
        lst(world, category="Z")


def test_detail_after_clear_verify_reopen_and_void(world: World, built: Built) -> None:
    one = need(world, key(1))
    assert (one.row.key, one.row.state, one.description) == (key(1), "Cleared", "Pump P-101")
    assert (one.cleared_by, one.clear_note) == ("user:rob", "Guard fitted")
    assert one.cleared_on is not None and len(one.cleared_on) == 10
    assert (one.verified_by, one.verified_on, one.void_reason) == (None, None, None)
    assert (one.reopen_count, one.last_reopen_reason) == (0, None)
    assert one.source_type == IWP and one.row.source_key == "IWP-1"
    assert one.version == world.version(built[1][0])
    assert one.row.id == built[1][0] and lst(world).rows[0].id == built[1][0]
    two = need(world, key(2))
    assert (two.row.state, two.cleared_by, two.verified_by) == ("Verified", "user:rob", "user:sue")
    assert two.verified_on is not None
    five = need(world, key(5))
    assert (five.row.state, five.reopen_count, five.last_reopen_reason) == (
        "Open",
        1,
        "Wrong size",
    )
    assert (five.cleared_by, five.clear_note, five.cleared_on) == (None, None, None)
    four = need(world, key(4))
    assert (four.row.state, four.void_reason) == ("Void", "Duplicate")
    assert need(world, key(3)).description is None


def test_a_free_standing_item_has_no_source(world: World, built: Built) -> None:
    three = need(world, key(3))
    assert three.row.source_key is None and three.source_type is None
    assert lst(world).rows[2].source_key is None


def test_an_unknown_key_and_another_project_give_none(world: World, built: Built) -> None:
    assert det(world, key(9999)) is None
    assert det(world, key(1), scope="project:P999") is None
    assert lst_in(world, "project:P999").total == 0


def lst_in(world: World, scope: str) -> PunchPage:
    with open_uow(world.db, readonly=True) as uow:
        return punch_list(uow.conn(), scope)


def test_counts_hold_all_four_states(world: World, built: Built) -> None:
    assert counts(world) == {"Open": 2, "Cleared": 1, "Verified": 1, "Void": 1}
    with open_uow(world.db, readonly=True) as uow:
        assert punch_counts(uow.conn(), "project:P999") == {
            "Open": 0,
            "Cleared": 0,
            "Verified": 0,
            "Void": 0,
        }


def test_a_hidden_source_looks_like_a_key_that_never_existed(world: World, built: Built) -> None:
    secret = world.hidden_record()
    hidden = world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret)
    number = str(hidden.key)
    assert number == key(6)
    # the lowest clearance (the default): absent from list, detail and counts
    assert keys(lst(world)) == [key(n) for n in range(1, 6)]
    assert lst(world).total == 5
    assert det(world, number) is None
    assert det(world, number) == det(world, key(9999))
    assert counts(world) == {"Open": 2, "Cleared": 1, "Verified": 1, "Void": 1}
    assert keys(lst(world, state="Open")) == [key(3), key(5)]
    assert keys(lst(world, source_key=number)) == []
    # a cleared viewer sees it everywhere
    page = lst(world, viewer=CLEARED)
    assert keys(page)[-1] == number and page.total == 6
    seen = need(world, number, viewer=CLEARED)
    assert seen.row.subject == "From secret" and seen.row.source_key is not None
    assert counts(world, viewer=CLEARED)["Open"] == 3
    assert lst(world, state="Open", limit=1, viewer=CLEARED).total == 3


def test_hidden_items_go_before_limit_and_count(world: World, built: Built) -> None:
    secret = world.hidden_record()
    world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret)
    page = lst(world, limit=5)
    assert len(page.rows) == 5 and page.total == 5


def test_a_read_runs_at_most_two_statements(world: World, built: Built) -> None:
    seen: list[str] = []

    def spy(*args: Any) -> None:
        seen.append(str(args[2]))

    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        event.listen(conn, "before_cursor_execute", spy)
        try:
            punch_list(conn, SCOPE)
            assert len(seen) <= 2
            seen.clear()
            punch_counts(conn, SCOPE)
            assert len(seen) <= 2
            seen.clear()
            punch_detail(conn, SCOPE, key(1))
            assert len(seen) <= 2
        finally:
            event.remove(conn, "before_cursor_execute", spy)
