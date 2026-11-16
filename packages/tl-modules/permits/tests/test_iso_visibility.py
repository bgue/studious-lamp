"""Isolations and gas tests are hidden through the records they name; five readers walk the six
commands (P2-PTW S3, ADR-0016).

Readers: nobody (the default), an agent, a viewer, an ordinary user and the foreman; the cleared
reader sees it all. A reader who may run a command (uma, rob, sue, pam) is refused a hidden id in
the words of a missing one; the viewer is refused by the access word before any lookup.
"""

from __future__ import annotations

from typing import Any

import pytest
from permit_world import World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits.errors import IsolationInUseError
from tl_mod_permits.names import GAS_TEST, ISOLATION

READERS = {
    "nobody": cf.LOWEST,
    "agent": cf.Viewer(actor="agent:bot", level=0, account=""),
    "viewer": cf.Viewer(actor="user:vera", level=0, account="user:vera"),
    "user": cf.Viewer(actor="user:uma", level=0, account="user:uma"),
    "foreman": cf.Viewer(actor="user:rob", level=0, account="user:rob"),
}
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
MISSING = "no record with that id"
GHOST = "01JXXXXXXXXXXXXXXXXXXXXXXX"
FIELDS: dict[str, Any] = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


class Set:
    """A restricted point and what hangs on it, and an open counterpart of each."""

    def __init__(self, world: World) -> None:
        world.person("dan", ("user", "document_controller"), grant="superuser")
        self.secret = world.hidden_record()
        self.hid_iso = str(
            world.call("dora", "ApplyIsolation", **FIELDS, point_record_id=self.secret).stream_id
        )
        self.open_iso = str(
            world.call(
                "uma",
                "ApplyIsolation",
                **FIELDS,
                point_record_id=world.record("awp.IWP", "TAG-1"),
            ).stream_id
        )
        self.hid_permit = world.request("dora", "hot_work", for_record_id=self.secret)
        world.call("dan", "ApprovePermit", permit=self.hid_permit)
        self.open_permit = world.approved("hot_work")
        self.hid_gas = str(
            world.call(
                "dora",
                "RecordGasTest",
                permit=self.hid_permit,
                instrument_text="MX6",
                o2_pct="20.9",
            ).stream_id
        )
        self.open_gas = str(
            world.call(
                "uma",
                "RecordGasTest",
                permit=self.open_permit,
                instrument_text="MX6",
                o2_pct="20.9",
            ).stream_id
        )


@pytest.fixture
def seen(world: World) -> Set:
    return Set(world)


def hidden(world: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def listed(world: World, viewer: cf.Viewer, record_type: str) -> list[str]:
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
        return [r["id"] for r in queries.list_records(uow, "project:P123", record_type=record_type)]


def refused(world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(RecordNotFoundError) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def test_a_restricted_isolation_and_gas_test_are_hidden_for_five_readers(
    world: World, seen: Set
) -> None:
    with open_uow(world.db, readonly=True) as uow:
        rows = [
            dict(r)
            for r in uow.conn()
            .execute(text("SELECT event_id, stream_id, stream_type, payload FROM events"))
            .mappings()
        ]
    own = {r["event_id"] for r in rows if r["stream_id"] in (seen.hid_iso, seen.hid_gas)}
    assert own
    for name, viewer in READERS.items():
        for record in (seen.hid_iso, seen.hid_gas):
            assert hidden(world, record, viewer), (name, record)
        for record in (seen.open_iso, seen.open_gas):
            assert not hidden(world, record, viewer), (name, record)
        assert listed(world, viewer, ISOLATION) == [seen.open_iso], name
        assert listed(world, viewer, GAS_TEST) == [seen.open_gas], name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            assert queries.get_record_by_id(uow, seen.hid_iso) is None
            assert queries.record_history(uow, seen.hid_iso) == queries.record_history(uow, GHOST)
            assert cf.hidden_row_ids(uow.conn(), rows) & own == own, name
    for record in (seen.hid_iso, seen.hid_gas):
        assert not hidden(world, record, CLEARED)
    assert sorted(listed(world, CLEARED, ISOLATION)) == sorted([seen.hid_iso, seen.open_iso])


@pytest.mark.parametrize("who", ["uma", "rob", "sue", "pam"])
def test_each_reader_who_may_run_the_commands_is_told_a_hidden_id_is_missing(
    world: World, seen: Set, who: str
) -> None:
    secret = seen.secret
    answers = {
        refused(world, who, "ApplyIsolation", **FIELDS, point_record_id=secret),
        refused(world, who, "RemoveIsolation", isolation=seen.hid_iso),
        refused(world, who, "LinkIsolation", permit=seen.hid_permit, isolation=seen.open_iso),
        refused(world, who, "LinkIsolation", permit=seen.open_permit, isolation=seen.hid_iso),
        refused(world, who, "UnlinkIsolation", permit=seen.hid_permit, isolation=seen.open_iso),
        refused(world, who, "UnlinkIsolation", permit=seen.open_permit, isolation=seen.hid_iso),
        refused(
            world, who, "RecordGasTest", permit=seen.hid_permit, instrument_text="MX6", o2_pct="20"
        ),
    }
    if who in ("sue", "pam"):  # the controllers hold the verify word; the others are refused it
        answers.add(refused(world, who, "VerifyIsolation", isolation=seen.hid_iso))
    ghosts = {
        refused(world, who, "RemoveIsolation", isolation=GHOST),
        refused(world, who, "LinkIsolation", permit=GHOST, isolation=seen.open_iso),
        refused(world, who, "UnlinkIsolation", permit=seen.open_permit, isolation=GHOST),
        refused(world, who, "RecordGasTest", permit=GHOST, instrument_text="MX6", o2_pct="20"),
    }
    if who in ("sue", "pam"):
        ghosts.add(refused(world, who, "VerifyIsolation", isolation=GHOST))
    assert answers == ghosts == {MISSING}
    for text_ in answers:
        assert seen.secret not in text_ and seen.hid_iso not in text_
    assert world.state(seen.hid_iso) == "Applied"


def test_a_viewer_is_refused_every_command_by_the_access_word(world: World, seen: Set) -> None:
    calls: list[tuple[str, dict[str, Any]]] = [
        ("ApplyIsolation", dict(FIELDS)),
        ("VerifyIsolation", {"isolation": seen.open_iso}),
        ("RemoveIsolation", {"isolation": seen.open_iso}),
        ("LinkIsolation", {"permit": seen.open_permit, "isolation": seen.open_iso}),
        ("UnlinkIsolation", {"permit": seen.open_permit, "isolation": seen.open_iso}),
        (
            "RecordGasTest",
            {"permit": seen.open_permit, "instrument_text": "MX6", "o2_pct": "20.9"},
        ),
    ]
    before = world.count()
    for name, fields in calls:
        with pytest.raises(ForbiddenError):
            world.call("vera", name, **fields)
    assert world.count() == before


def test_a_cleared_controller_sees_and_verifies_the_restricted_isolation(
    world: World, seen: Set
) -> None:
    with pytest.raises(ForbiddenError, match="applied an isolation"):
        world.call("dora", "VerifyIsolation", isolation=seen.hid_iso)
    world.call("dan", "VerifyIsolation", isolation=seen.hid_iso)
    assert world.state(seen.hid_iso) == "Verified"
    world.call("dan", "LinkIsolation", permit=seen.hid_permit, isolation=seen.hid_iso)
    world.call("dora", "RecordGasTest", permit=seen.hid_permit, instrument_text="MX6", lel_pct="1")


def test_a_hidden_permit_that_depends_on_an_isolation_is_not_named_to_any_reader(
    world: World, seen: Set
) -> None:
    world.call("dan", "LinkIsolation", permit=seen.hid_permit, isolation=seen.open_iso)
    key = str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=seen.hid_permit))
    messages = set()
    for who in ("uma", "rob", "sue", "pam"):
        with pytest.raises(IsolationInUseError) as caught:
            world.call(who, "RemoveIsolation", isolation=seen.open_iso)
        messages.add(str(caught.value))
    assert messages == {"the isolation is still needed by a permit you cannot see"}
    assert all(key not in m for m in messages)
    assert world.state(seen.open_iso) == "Applied"
    with pytest.raises(IsolationInUseError) as cleared:
        world.call("dora", "RemoveIsolation", isolation=seen.open_iso)
    assert key in str(cleared.value)
