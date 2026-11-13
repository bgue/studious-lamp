"""A punch item is hidden when its source record is; ``open_punch_for`` and the actions table."""

from __future__ import annotations

import pytest
from punch_world import IWP, World
from sqlalchemy import Connection
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.actions import Level
from tl_core.auth.module_roles import normalise_word
from tl_core.confidentiality import SUBJECT_LINKS
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import api
from tl_mod_quality.actions import RULES, punch_actions, states_for
from tl_mod_quality.errors import PunchRuleError
from tl_mod_quality.handlers.punch import MSG_SOURCE_LINKED, SOURCE_REFUSED
from tl_mod_quality.module import PUNCH_COMMANDS, spec

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def read(world: World, *args: object, **kw: object) -> list[api.PunchRef]:
    with open_uow(world.db, readonly=True) as uow:
        conn: Connection = uow.conn()
        return api.open_punch_for(conn, *args, **kw)  # type: ignore[arg-type]


def test_an_item_raised_from_a_restricted_record_is_hidden_from_the_default_viewer(
    world: World,
) -> None:
    secret = world.hidden_record()
    item = str(
        world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret).stream_id
    )
    assert read(world, secret) == []
    assert [r.id for r in read(world, secret, viewer=CLEARED)] == [item]
    with pytest.raises(RecordNotFoundError, match="no record with that id"):
        world.call("uma", "ClearPunchItem", punch_item=item, note="n")
    assert world.state(item) == "Open"
    world.call("dora", "ClearPunchItem", punch_item=item, note="n")
    assert world.state(item) == "Cleared"


def test_an_item_with_no_or_a_dangling_source_falls_back_to_its_own_class(world: World) -> None:
    free = world.raise_item()
    iwp = world.record(IWP, "IWP-1")
    mine = world.raise_item(from_record_id=iwp)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        for item in (free, mine):
            assert cf.is_hidden(conn, item) is False


def test_a_constraint_on_a_punch_item_is_hidden_when_its_source_is(world: World) -> None:
    secret = world.hidden_record()
    item = str(
        world.call("dora", "RaisePunchItem", subject="From secret", from_record_id=secret).stream_id
    )
    constraint = world.advisory(item, who="dora")
    free = world.raise_item()
    open_one = world.advisory(free)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        assert cf.is_hidden(conn, item) and cf.is_hidden(conn, constraint)
        assert not cf.is_hidden(conn, open_one)
        with cf.use_viewer(CLEARED):
            assert not cf.is_hidden(conn, constraint)


def test_open_punch_for_returns_only_open_and_cleared_items(world: World) -> None:
    iwp = world.record(IWP, "IWP-1")
    ids = [world.raise_item(from_record_id=iwp, category=c) for c in ("A", "B", "B", "C", "A")]
    world.call("rob", "ClearPunchItem", punch_item=ids[1], note="n")
    world.call("rob", "ClearPunchItem", punch_item=ids[2], note="n")
    world.call("sue", "VerifyPunchItem", punch_item=ids[2])
    world.call("sue", "VoidPunchItem", punch_item=ids[3], reason="r")
    found = read(world, iwp)
    assert [r.id for r in found] == [ids[0], ids[1], ids[4]]
    assert [r.state for r in found] == ["Open", "Cleared", "Open"]
    assert [r.id for r in read(world, iwp, categories=["A"])] == [ids[0], ids[4]]
    assert found[0].key == "P123-PUN-0001" and found[0].due_on is None
    with pytest.raises(ValueError, match="unknown punch category"):
        read(world, iwp, categories=["Z"])


def test_open_punch_for_refuses_more_than_the_limit(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    iwp = world.record(IWP, "IWP-1")
    for _ in range(3):
        world.raise_item(from_record_id=iwp)
    monkeypatch.setattr(api, "MAX_ROWS", 2)
    with pytest.raises(ValueError, match="more than 500"):
        read(world, iwp)


def test_every_rule_level_equals_the_table_word_of_its_command() -> None:
    words = {c.model.__name__: c.access for c in PUNCH_COMMANDS}
    for rule in RULES:
        assert rule.level == normalise_word(words[rule.command]), rule.command
    assert [r.command for r in RULES] == [
        "EditPunchItem",
        "ClearPunchItem",
        "VerifyPunchItem",
        "ReopenPunchItem",
        "VoidPunchItem",
    ]
    assert states_for("ReopenPunchItem") == ("Cleared", "Verified")
    assert set(spec().actions) == {"quality.PunchItem"}


def test_the_actions_hook_offers_what_the_state_and_level_allow(world: World) -> None:
    item = world.raise_item()

    def offered(level: set[str]) -> list[str]:
        def holds(wanted: Level) -> bool:
            return wanted in level

        with open_uow(world.db, readonly=True) as uow:
            return [o.command for o in punch_actions(uow.conn(), item, holds)]

    assert offered({"user", "controller"}) == ["EditPunchItem", "ClearPunchItem", "VoidPunchItem"]
    assert offered({"user"}) == ["EditPunchItem", "ClearPunchItem"]
    world.call("rob", "ClearPunchItem", punch_item=item, note="n")
    assert offered({"user", "controller"}) == [
        "VerifyPunchItem",
        "ReopenPunchItem",
        "VoidPunchItem",
    ]
    assert offered({"user"}) == []
    world.call("sue", "VoidPunchItem", punch_item=item, reason="r")
    assert offered({"user", "controller"}) == []


# --- the source rule (SR3): a punch item is never raised from a record that names a subject ---


def _refused(world: World, who: str, source: str) -> None:
    with pytest.raises(PunchRuleError) as caught:
        world.call(who, "RaisePunchItem", subject="Leaky", from_record_id=source)
    assert str(caught.value) == MSG_SOURCE_LINKED


def test_a_punch_item_is_not_raised_from_a_constraint_on_a_hidden_record(world: World) -> None:
    secret = world.hidden_record()
    constraint = world.advisory(secret, who="dora")
    before = world.count()
    _refused(world, "dora", constraint)
    assert world.count() == before


def test_a_punch_item_is_not_raised_from_another_punch_item(world: World) -> None:
    first = world.raise_item(from_record_id=world.record(IWP, "IWP-1"))
    before = world.count()
    _refused(world, "uma", first)
    assert world.count() == before


@pytest.mark.parametrize("record_type", ["requisitions.LaborRequisition", "requisitions.WorkOrder"])
def test_a_punch_item_is_not_raised_from_a_requisition_or_work_order(
    world: World, record_type: str
) -> None:
    _refused(world, "uma", world.record(record_type, "SRC-1"))


def test_a_hidden_source_still_answers_as_a_missing_one(world: World) -> None:
    secret = world.hidden_record()
    with pytest.raises(RecordNotFoundError) as hidden:
        world.call("uma", "RaisePunchItem", subject="X", from_record_id=secret)
    with pytest.raises(RecordNotFoundError) as missing:
        world.call("uma", "RaisePunchItem", subject="X", from_record_id="no-such-id")
    assert str(hidden.value) == str(missing.value)


def test_the_refused_source_types_derive_from_the_subject_links() -> None:
    assert SOURCE_REFUSED == {"core.Constraint"} | {row[0] for row in SUBJECT_LINKS}
    assert "quality.PunchItem" in SOURCE_REFUSED
