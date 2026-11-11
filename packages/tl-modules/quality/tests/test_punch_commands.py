"""The six punch commands: effects, state table, actors, versions, valid time, intent, numbering."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from punch_world import IWP, SCOPE, World
from pydantic import ValidationError
from tl_adapters.db import DbTarget
from tl_core.auth.errors import ForbiddenError
from tl_core.intent import Intent, IntentInvalid
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_quality.commands import RaisePunchItem
from tl_mod_quality.errors import PunchRuleError, PunchStateError, StaleVersionError
from tl_mod_quality.guards import MSG_VOID
from tl_mod_quality.handlers.punch import MSG_NOT_PARTY, MSG_NOTHING, MSG_SELF_VERIFY


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: object) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def cleared(world: World, **more: Any) -> str:
    item = world.raise_item(**more)
    world.call("rob", "ClearPunchItem", punch_item=item, note="Guard fitted")
    return item


def test_raise_makes_an_open_item_with_the_actor_and_the_link(world: World) -> None:
    iwp = world.record(IWP, "IWP-1")
    made = world.call(
        "uma",
        "RaisePunchItem",
        subject="Guard missing",
        description="Pump P-101",
        area="A1",
        system="47-01",
        due_on="2026-12-20",
        assignee="user:rob",
        from_record_id=iwp,
    )
    item = made.stream_id
    assert made.key == "P123-PUN-0001"
    assert world.state(item) == "Open"
    row = world.row(item)
    assert (row["raised_by"], row["source_id"], row["category"]) == ("user:uma", iwp, "B")
    assert (row["area"], row["system"], row["due_on"], row["assignee"]) == (
        "A1",
        "47-01",
        "2026-12-20",
        "user:rob",
    )
    links = world.links_from(item)
    assert [(link["relation"], link["to_id"]) for link in links] == [("raised_against", iwp)]
    assert world.rows("SELECT title, description FROM cur_core_record WHERE id = :i", i=item) == [
        {"title": "Guard missing", "description": "Pump P-101"}
    ]


def test_a_free_standing_raise_has_no_source_and_no_link(world: World) -> None:
    item = world.raise_item(category="A")
    assert world.row(item)["source_id"] is None and world.row(item)["category"] == "A"
    assert world.links_from(item) == []


def test_raised_by_is_never_an_input() -> None:
    with pytest.raises(ValidationError):
        RaisePunchItem(
            actor="user:uma",
            source="t",
            scope=SCOPE,
            subject="x",
            raised_by="user:rob",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"subject": ""},
        {"subject": "x" * 201},
        {"subject": "bad\nline"},
        {"subject": "ok", "description": "x" * 1001},
        {"subject": "ok", "area": "x" * 65},
        {"subject": "ok", "system": "x" * 65},
        {"subject": "ok", "assignee": "x" * 121},
        {"subject": "ok", "category": "D"},
        {"subject": "ok", "due_on": "2026-02-30"},
    ],
)
def test_raise_bounds(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RaisePunchItem(actor="user:uma", source="t", scope=SCOPE, **fields)  # type: ignore[arg-type]


def test_an_unknown_and_a_hidden_source_answer_the_same_text_and_write_nothing(
    world: World,
) -> None:
    hidden = world.hidden_record()
    before = world.count()
    texts = {
        raises(RecordNotFoundError, world, "uma", "RaisePunchItem", subject="x", from_record_id=r)
        for r in (hidden, new_ulid())
    }
    assert texts == {"no record with that id"}
    assert world.count() == before


def test_edit_by_raiser_assignee_or_verifier_and_not_by_a_stranger(world: World) -> None:
    item = world.raise_item(assignee="user:rob", area="A1")
    assert raises(ForbiddenError, world, "dora", "EditPunchItem", punch_item=item, area="A2") == (
        MSG_NOT_PARTY
    )
    world.call("rob", "EditPunchItem", punch_item=item, area="A2", subject="Guard loose")
    world.call("uma", "EditPunchItem", punch_item=item, category="A", assignee=None)
    world.call("sue", "EditPunchItem", punch_item=item, due_on="2026-12-24")
    row = world.row(item)
    assert (row["area"], row["category"], row["assignee"], row["due_on"]) == (
        "A2",
        "A",
        None,
        "2026-12-24",
    )
    title = world.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=item)
    assert title == "Guard loose"
    changes = world.scalar(
        "SELECT payload FROM events WHERE event_type = 'PunchItem.Edited' AND stream_id = :i "
        "ORDER BY seq LIMIT 1",
        i=item,
    )
    assert json.loads(str(changes))["changes"] == {
        "area": ["A1", "A2"],
        "subject": ["Guard missing", "Guard loose"],
    }


def test_edit_needs_a_field_a_change_and_an_open_item(world: World) -> None:
    item = world.raise_item(area="A1")
    with pytest.raises(ValidationError):
        world.call("uma", "EditPunchItem", punch_item=item)
    with pytest.raises(ValidationError):
        world.call("uma", "EditPunchItem", punch_item=item, subject=None)
    assert raises(PunchRuleError, world, "uma", "EditPunchItem", punch_item=item, area="A1") == (
        MSG_NOTHING
    )
    world.call("rob", "ClearPunchItem", punch_item=item, note="done")
    message = raises(PunchStateError, world, "uma", "EditPunchItem", punch_item=item, area="A9")
    assert "Cleared" in message and "Open" in message


def test_clear_needs_a_note_and_stores_the_actor(world: World) -> None:
    item = world.raise_item()
    with pytest.raises(ValidationError):
        world.call("rob", "ClearPunchItem", punch_item=item, note="")
    with pytest.raises(ValidationError):
        world.call("rob", "ClearPunchItem", punch_item=item, note="x" * 301)
    world.call("rob", "ClearPunchItem", punch_item=item, note="Guard fitted")
    row = world.row(item)
    assert (row["cleared_by"], row["clear_note"]) == ("user:rob", "Guard fitted")
    assert world.state(item) == "Cleared"


def test_the_clearer_may_not_verify_and_a_user_is_forbidden(world: World) -> None:
    item = cleared(world)
    assert raises(ForbiddenError, world, "rob", "VerifyPunchItem", punch_item=item) == (
        MSG_SELF_VERIFY
    )
    assert world.state(item) == "Cleared"
    with pytest.raises(ForbiddenError):  # no verify word at all
        world.call("uma", "VerifyPunchItem", punch_item=item)
    world.call("sue", "VerifyPunchItem", punch_item=item)
    row = world.row(item)
    assert row["verified_by"] == "user:sue" and world.state(item) == "Verified"


def test_open_to_verified_is_refused(world: World) -> None:
    item = world.raise_item()
    message = raises(PunchStateError, world, "sue", "VerifyPunchItem", punch_item=item)
    assert "Open" in message and "Cleared" in message
    assert world.state(item) == "Open"


def test_reopen_needs_a_reason_resets_and_counts(world: World) -> None:
    item = cleared(world)
    with pytest.raises(ValidationError):
        world.call("sue", "ReopenPunchItem", punch_item=item, reason="")
    world.call("sue", "ReopenPunchItem", punch_item=item, reason="Guard loose")
    row = world.row(item)
    assert world.state(item) == "Open" and row["reopen_count"] == 1
    assert row["last_reopen_reason"] == "Guard loose"
    assert [row[c] for c in ("cleared_by", "cleared_on", "clear_note")] == [None] * 3
    message = raises(PunchStateError, world, "sue", "ReopenPunchItem", punch_item=item, reason="x")
    assert "Open" in message


def test_a_verified_item_can_be_reopened(world: World) -> None:
    item = cleared(world)
    world.call("sue", "VerifyPunchItem", punch_item=item)
    world.call("sue", "ReopenPunchItem", punch_item=item, reason="Failed walkdown")
    row = world.row(item)
    assert world.state(item) == "Open" and row["verified_by"] is None
    world.call("rob", "ClearPunchItem", punch_item=item, note="again")
    world.call("sue", "ReopenPunchItem", punch_item=item, reason="Again")
    assert world.row(item)["reopen_count"] == 2


def test_void_from_open_and_cleared_and_never_from_verified(world: World) -> None:
    first, second, third = world.raise_item(), cleared(world), cleared(world)
    world.call("sue", "VoidPunchItem", punch_item=first, reason="Raised twice")
    world.call("sue", "VoidPunchItem", punch_item=second, reason="Not ours")
    world.call("sue", "VerifyPunchItem", punch_item=third)
    assert raises(PunchStateError, world, "sue", "VoidPunchItem", punch_item=third, reason="x")
    assert (world.state(first), world.state(second)) == ("Void", "Void")
    assert world.row(first)["void_reason"] == "Raised twice"


@pytest.mark.parametrize(
    ("name", "fields", "who"),
    [
        ("EditPunchItem", {"area": "Z"}, "uma"),
        ("ClearPunchItem", {"note": "n"}, "rob"),
        ("VerifyPunchItem", {}, "sue"),
        ("ReopenPunchItem", {"reason": "r"}, "sue"),
        ("VoidPunchItem", {"reason": "r"}, "sue"),
    ],
)
def test_a_void_item_refuses_every_command_with_one_message(
    world: World, name: str, fields: dict[str, object], who: str
) -> None:
    item = world.raise_item()
    world.call("sue", "VoidPunchItem", punch_item=item, reason="gone")
    before = world.count()
    assert raises(PunchStateError, world, who, name, punch_item=item, **fields) == MSG_VOID
    assert world.count() == before


def test_a_stale_expected_version_is_refused_and_none_skips_the_check(world: World) -> None:
    item = world.raise_item()
    current = world.version(item)
    before = world.count()
    raises(
        StaleVersionError,
        world,
        "rob",
        "ClearPunchItem",
        punch_item=item,
        note="n",
        expected_version=current - 1,
    )
    assert world.count() == before
    world.call("rob", "ClearPunchItem", punch_item=item, note="n", expected_version=current)
    world.call("sue", "VerifyPunchItem", punch_item=item, expected_version=None)
    assert world.state(item) == "Verified"


def test_valid_time_is_not_in_the_future_nor_before_the_raise_day(world: World) -> None:
    item = world.raise_item()
    future = datetime.now(UTC) + timedelta(days=1)
    past = datetime.now(UTC) - timedelta(days=3)
    raises(PunchRuleError, world, "rob", "ClearPunchItem", punch_item=item, note="n", at=future)
    raises(PunchRuleError, world, "rob", "ClearPunchItem", punch_item=item, note="n", at=past)
    with pytest.raises(ValidationError):  # no zone
        world.call("rob", "ClearPunchItem", punch_item=item, note="n", at=datetime(2026, 1, 1))
    world.call(
        "rob",
        "ClearPunchItem",
        punch_item=item,
        note="n",
        at=datetime.now(UTC) - timedelta(hours=1),
    )
    raises(PunchRuleError, world, "sue", "VerifyPunchItem", punch_item=item, at=future)
    assert world.row(item)["cleared_on"] is not None


def test_an_unknown_item_and_a_hidden_one_answer_alike(world: World) -> None:
    hidden = world.hidden_record()
    texts = {
        raises(RecordNotFoundError, world, "rob", "ClearPunchItem", punch_item=i, note="n")
        for i in (hidden, new_ulid())
    }
    assert texts == {"no record with that id"}


def test_generic_commands_take_only_the_allowed_ones() -> None:
    from tl_mod_quality.module import spec

    allowed = spec().generic_commands["quality.PunchItem"]
    assert {"SetPsetValues", "AddLink", "AttachFile", "RetractLink"} <= allowed
    assert not {"UpdateRecord", "VoidRecord", "TransitionWorkflow"} & allowed


def test_a_void_item_takes_no_generic_command(world: World, db: DbTarget) -> None:
    from tl_adapters.db import open_uow
    from tl_core.services.errors import UnsupportedRecordTypeError
    from tl_mod_quality.guards import not_void

    item = world.raise_item()
    with open_uow(db) as uow:
        not_void(uow.conn(), item, None)
    world.call("sue", "VoidPunchItem", punch_item=item, reason="gone")
    with open_uow(db) as uow, pytest.raises(UnsupportedRecordTypeError, match="no further"):
        not_void(uow.conn(), item, None)


def test_intent_is_stored_on_raise_and_verify_and_a_long_why_refuses(world: World) -> None:
    item = str(
        world.call("uma", "RaisePunchItem", subject="x", intent=Intent(why="Walkdown 14")).stream_id
    )
    world.call("rob", "ClearPunchItem", punch_item=item, note="done")
    world.call("sue", "VerifyPunchItem", punch_item=item, intent=Intent(why="Checked on site"))
    held = {
        r["event_type"]: r["intent"]
        for r in world.rows(
            "SELECT event_type, intent FROM events WHERE stream_id = :i "
            "AND event_type IN ('PunchItem.Raised', 'PunchItem.Verified')",
            i=item,
        )
    }
    assert "Walkdown 14" in held["PunchItem.Raised"]
    assert "Checked on site" in held["PunchItem.Verified"]
    before = world.count()
    with pytest.raises(IntentInvalid):
        world.call("uma", "RaisePunchItem", subject="y", intent=Intent(why="x" * 501))
    assert world.count() == before


def test_two_threads_raising_twenty_items_get_a_gap_free_run(db: DbTarget) -> None:
    w = World(db)
    w.people()
    gate = threading.Barrier(2)

    def ten(who: str) -> list[str]:
        gate.wait()
        return [str(w.call(who, "RaisePunchItem", subject="x").key) for _ in range(10)]

    with ThreadPoolExecutor(2) as pool:
        keys = [k for batch in pool.map(ten, ["uma", "rob"]) for k in batch]
    assert sorted(keys) == [f"P123-PUN-{n:04d}" for n in range(1, 21)]
