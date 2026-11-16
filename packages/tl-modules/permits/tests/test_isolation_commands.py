"""The five isolation commands: apply, verify, remove, link, unlink (P2-PTW S3)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from permit_world import SCOPE, World
from pydantic import ValidationError
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits.errors import IsolationInUseError, IsolationRuleError, IsolationStateError
from tl_mod_permits.guards import dependent_permits
from tl_mod_permits.handlers.isolation import (
    MSG_ALREADY_LINKED,
    MSG_HIDDEN_PERMIT,
    MSG_IN_USE,
    MSG_LINK_LIVE,
    MSG_LINK_REMOVED,
    MSG_NOT_LINKED,
    MSG_SELF_VERIFY,
)
from tl_mod_permits.iso_commands import ApplyIsolation

FIELDS: dict[str, Any] = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def apply(world: World, who: str = "uma", **more: Any) -> str:
    return str(world.call(who, "ApplyIsolation", **{**FIELDS, **more}).stream_id)


def linked(world: World, permit: str, isolation: str) -> None:
    world.call("uma", "LinkIsolation", permit=permit, isolation=isolation)


def key_of(world: World, record: str) -> str:
    return str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))


def events_of(world: World, stream: str, kind: str) -> int:
    return int(
        world.scalar(
            "SELECT count(*) FROM events WHERE stream_id = :s AND event_type = :k", s=stream, k=kind
        )
    )


# --- apply -------------------------------------------------------------------------------------


def test_apply_makes_an_applied_isolation_numbered_per_project(world: World) -> None:
    made = world.call("uma", "ApplyIsolation", **FIELDS)
    assert made.key == "P123-ISL-0001"
    assert world.state(made.stream_id) == "Applied"
    row = world.rows("SELECT * FROM cur_permits_isolation WHERE id = :i", i=made.stream_id)[0]
    assert (row["point_text"], row["energy"], row["method"]) == (
        "Pump P-101 breaker",
        "electrical",
        "Lock and tag",
    )
    assert (row["lock_number"], row["tag_number"], row["applied_by"]) == (
        "L-12",
        "T-12",
        "user:uma",
    )
    assert str(row["applied_at"])[:19].replace(" ", "T") == "2026-12-01T07:00:00"
    assert row["verified_by"] is None and row["removed_by"] is None
    assert world.call("rob", "ApplyIsolation", **FIELDS).key == "P123-ISL-0002"


def test_apply_models_are_strict() -> None:
    base: dict[str, Any] = {"actor": "user:uma", "source": "t", "scope": SCOPE, **FIELDS}
    ApplyIsolation(**base)
    for bad in (
        {"applied_by": "user:x"},
        {"energy": "heat"},
        {"point_text": "x" * 121},
        {"method": "x" * 121},
        {"point_text": "  "},
        {"lock_number": ""},
        {"tag_number": ""},
    ):
        with pytest.raises(ValidationError):
            ApplyIsolation(**{**base, **bad})
    ApplyIsolation(**{**base, "point_text": "x" * 120, "method": "y" * 120})


def test_apply_with_a_readable_point_record_keeps_it(world: World) -> None:
    point = world.record("awp.IWP", "TAG-1")
    made = apply(world, point_record_id=point)
    assert (
        world.rows("SELECT * FROM cur_permits_isolation WHERE id = :i", i=made)[0][
            "point_record_id"
        ]
        == point
    )


def test_apply_with_a_hidden_missing_or_foreign_point_answers_one_text(world: World) -> None:
    secret = world.hidden_record()
    other = world.record("awp.IWP", "IWP-9", scope="project:P999")
    texts = {
        raises(RecordNotFoundError, world, "uma", "ApplyIsolation", **FIELDS, point_record_id=ref)
        for ref in (secret, "01JXXXXXXXXXXXXXXXXXXXXXXX", other)
    }
    assert texts == {"no record with that id"}
    assert world.count("cur_permits_isolation") == 0


def test_apply_needs_a_project_scope(world: World) -> None:
    from tl_adapters.db import open_uow
    from tl_mod_permits.errors import PermitScopeError
    from tl_mod_permits.handlers.isolation import handle_apply_isolation

    cmd = ApplyIsolation(actor="user:uma", source="t", scope="company", **FIELDS)
    with open_uow(world.db) as uow, pytest.raises(PermitScopeError):
        handle_apply_isolation(uow, cmd)


def test_a_viewer_may_not_apply(world: World) -> None:
    raises(ForbiddenError, world, "vera", "ApplyIsolation", **FIELDS)
    assert world.count("cur_permits_isolation") == 0


# --- verify ------------------------------------------------------------------------------------


def test_a_controller_other_than_the_applier_verifies(world: World) -> None:
    isolation = apply(world, "uma")
    world.at += timedelta(minutes=20)
    made = world.call("sue", "VerifyIsolation", isolation=isolation)
    assert made.key == "P123-ISL-0001" and world.state(isolation) == "Verified"
    row = world.rows("SELECT * FROM cur_permits_isolation WHERE id = :i", i=isolation)[0]
    assert row["verified_by"] == "user:sue"
    assert str(row["verified_at"])[:19].replace(" ", "T") == "2026-12-01T07:20:00"


def test_the_applier_may_not_verify_their_own_isolation(world: World) -> None:
    isolation = apply(world, "sue")
    message = raises(ForbiddenError, world, "sue", "VerifyIsolation", isolation=isolation)
    assert message == MSG_SELF_VERIFY
    assert world.state(isolation) == "Applied"
    assert events_of(world, isolation, "Isolation.Verified") == 0
    world.call("pam", "VerifyIsolation", isolation=isolation)
    assert world.state(isolation) == "Verified"


def test_verifying_needs_the_controller_word(world: World) -> None:
    isolation = apply(world, "uma")
    raises(ForbiddenError, world, "rob", "VerifyIsolation", isolation=isolation)
    assert world.state(isolation) == "Applied"


def test_only_an_applied_isolation_is_verified(world: World) -> None:
    isolation = apply(world, "uma")
    world.call("sue", "VerifyIsolation", isolation=isolation)
    assert "needs Applied" in raises(
        IsolationStateError, world, "pam", "VerifyIsolation", isolation=isolation
    )
    world.call("uma", "RemoveIsolation", isolation=isolation)
    assert "Removed" in raises(
        IsolationStateError, world, "pam", "VerifyIsolation", isolation=isolation
    )


def test_a_stale_expected_version_is_refused(world: World) -> None:
    from tl_mod_permits.errors import StaleVersionError

    isolation = apply(world, "uma")
    version = world.version(isolation)
    raises(
        StaleVersionError,
        world,
        "sue",
        "VerifyIsolation",
        isolation=isolation,
        expected_version=version + 3,
    )
    world.call("sue", "VerifyIsolation", isolation=isolation, expected_version=version)


# --- remove ------------------------------------------------------------------------------------


def test_remove_an_applied_or_verified_isolation_nobody_needs(world: World) -> None:
    applied, verified = apply(world), apply(world)
    world.call("sue", "VerifyIsolation", isolation=verified)
    world.at += timedelta(minutes=5)
    for isolation in (applied, verified):
        world.call("rob", "RemoveIsolation", isolation=isolation)
        assert world.state(isolation) == "Removed"
    row = world.rows("SELECT * FROM cur_permits_isolation WHERE id = :i", i=applied)[0]
    assert row["removed_by"] == "user:rob"
    assert str(row["removed_at"])[:19].replace(" ", "T") == "2026-12-01T07:05:00"
    assert "needs Applied or Verified" in raises(
        IsolationStateError, world, "rob", "RemoveIsolation", isolation=applied
    )


def _depends(world: World, state: str) -> tuple[str, str]:
    """An isolation and a general permit that links it, brought to ``state``."""
    permit = world.approved("general")
    isolation = apply(world)
    linked(world, permit, isolation)
    if state in ("Active", "Lapsed", "Suspended"):
        world.issue(permit)
    if state == "Lapsed":
        world.at = world.at.replace(hour=19)
    if state == "Suspended":
        world.call("uma", "SuspendPermit", permit=permit, reason="Stop")
    return permit, isolation


@pytest.mark.parametrize("state", ["Approved", "Active", "Suspended", "Lapsed"])
def test_remove_is_refused_while_a_permit_in_use_depends_on_it(world: World, state: str) -> None:
    permit, isolation = _depends(world, state)
    message = raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    assert message == MSG_IN_USE + "P123-PTW-0001"
    assert world.state(isolation) == "Applied"
    assert events_of(world, isolation, "Isolation.Removed") == 0


def test_remove_is_allowed_after_the_permit_is_closed(world: World) -> None:
    permit, isolation = _depends(world, "Active")
    raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    world.call("rob", "HandBackPermit", permit=permit, handback_note="Site clear")
    world.call("pam", "ClosePermit", permit=permit)
    world.call("uma", "RemoveIsolation", isolation=isolation)
    assert world.state(isolation) == "Removed"


def test_remove_is_allowed_once_the_permit_is_handed_back(world: World) -> None:
    """Handed back is not in the list that holds an isolation (Approved, Active, Suspended)."""
    permit, isolation = _depends(world, "Suspended")
    raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    world.call("rob", "HandBackPermit", permit=permit, handback_note="Site clear")
    world.call("uma", "RemoveIsolation", isolation=isolation)
    assert world.state(isolation) == "Removed"


@pytest.mark.parametrize("ending", ["Cancelled", "Rejected"])
def test_remove_is_allowed_after_the_permit_ends_unissued(world: World, ending: str) -> None:
    permit = world.request()
    isolation = apply(world)
    linked(world, permit, isolation)
    if ending == "Cancelled":
        world.call("pam", "CancelPermit", permit=permit, reason="Moved")
    else:
        world.call("sue", "RejectPermit", permit=permit, reason="No")
    world.call("uma", "RemoveIsolation", isolation=isolation)
    assert world.state(isolation) == "Removed"


def test_remove_is_allowed_for_a_requested_permit_and_after_an_unlink(world: World) -> None:
    requested = world.request()
    first = apply(world)
    linked(world, requested, first)
    world.call("uma", "RemoveIsolation", isolation=first)  # a Requested permit needs nothing yet
    permit = world.approved("general")
    second = apply(world)
    linked(world, permit, second)
    raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=second)
    world.call("uma", "UnlinkIsolation", permit=permit, isolation=second)
    world.call("uma", "RemoveIsolation", isolation=second)
    assert world.state(second) == "Removed"


def test_an_isolation_is_found_by_the_events_of_each_permit_that_links_it(world: World) -> None:
    from tl_adapters.db import open_uow

    isolation, other = apply(world), apply(world)
    ids = []
    for _ in range(2):
        permit = world.approved("general")
        linked(world, permit, isolation)
        ids.append(permit)
    unlinked = world.approved("general")
    linked(world, unlinked, isolation)
    world.call("uma", "UnlinkIsolation", permit=unlinked, isolation=isolation)
    with open_uow(world.db, readonly=True) as uow:
        found = dependent_permits(uow.conn(), isolation)
        none = dependent_permits(uow.conn(), other)
    assert [str(r["id"]) for r in found] == ids and none == []
    assert {r["status"] for r in found} == {"Approved"}
    assert [r["key"] for r in found] == ["P123-PTW-0001", "P123-PTW-0002"]


def _hidden_permit(world: World) -> str:
    """An Approved permit whose record is restricted (cleared people only read and decide it)."""
    secret = world.hidden_record()
    permit = world.request("dora", for_record_id=secret)
    world.call("dan", "ApprovePermit", permit=permit)
    return permit


def test_a_hidden_dependent_permit_is_named_only_as_one_you_cannot_see(world: World) -> None:
    world.person("dan", ("user", "document_controller"), grant="superuser")
    isolation = apply(world)
    hidden = [_hidden_permit(world)]
    world.link(hidden[0], isolation)
    one = raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    for _ in range(2):
        hidden.append(_hidden_permit(world))
        world.link(hidden[-1], isolation)
    three = raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    assert one == three == MSG_IN_USE + MSG_HIDDEN_PERMIT
    keys = [key_of(world, p) for p in hidden]
    assert not any(key in three for key in keys) and "PTW" not in three
    assert not any(ch.isdigit() for ch in three)
    # a permit the reader can see is named, the hidden ones stay one phrase
    visible = world.approved("general")
    world.link(visible, isolation)
    mixed = raises(IsolationInUseError, world, "uma", "RemoveIsolation", isolation=isolation)
    assert mixed == f"{MSG_IN_USE}P123-PTW-0004 and {MSG_HIDDEN_PERMIT}"
    # the cleared reader sees each by key
    cleared = raises(IsolationInUseError, world, "dora", "RemoveIsolation", isolation=isolation)
    assert "a permit you cannot see" not in cleared and "P123-PTW-0001" in cleared


# --- link and unlink ---------------------------------------------------------------------------


def test_link_and_unlink_each_append_one_event_on_the_permits_stream(world: World) -> None:
    permit = world.approved("isolation")
    isolation = apply(world)
    made = world.call("uma", "LinkIsolation", permit=permit, isolation=isolation)
    assert made.stream_id == permit and made.key == "P123-PTW-0001"
    assert events_of(world, permit, "Permit.IsolationLinked") == 1
    assert events_of(world, isolation, "Permit.IsolationLinked") == 0
    world.call("rob", "UnlinkIsolation", permit=permit, isolation=isolation)
    assert events_of(world, permit, "Permit.IsolationUnlinked") == 1
    assert world.state(permit) == "Approved"
    world.call("uma", "LinkIsolation", permit=permit, isolation=isolation)  # again after unlink
    assert events_of(world, permit, "Permit.IsolationLinked") == 2


def test_a_linked_isolation_is_what_the_issue_guards_read(world: World) -> None:
    from tl_mod_permits.errors import PermitBlockedError

    permit = world.approved("isolation")
    ticks = ["points_listed", "locks_tags_applied", "zero_energy_proven"]
    assert "isolation_missing" in raises(
        PermitBlockedError, world, "pam", "IssuePermit", permit=permit, precautions=ticks
    )
    isolation = apply(world, "uma")
    linked(world, permit, isolation)
    assert "isolation_unverified" in raises(
        PermitBlockedError, world, "pam", "IssuePermit", permit=permit, precautions=ticks
    )
    world.call("sue", "VerifyIsolation", isolation=isolation)
    world.call("pam", "IssuePermit", permit=permit, precautions=ticks)
    assert world.state(permit) == "Active"


@pytest.mark.parametrize("name", ["LinkIsolation", "UnlinkIsolation"])
@pytest.mark.parametrize("lapsed", [False, True])
def test_no_link_change_while_the_permit_is_active_or_lapsed(
    world: World, name: str, lapsed: bool
) -> None:
    permit = world.approved("general")
    isolation = apply(world)
    linked(world, permit, isolation)
    world.issue(permit)
    if lapsed:
        world.at = world.at.replace(hour=19)
    before = world.count()
    assert raises(IsolationRuleError, world, "uma", name, permit=permit, isolation=isolation) == (
        MSG_LINK_LIVE
    )
    assert world.count() == before


def test_a_permit_taken_back_to_suspended_takes_link_changes(world: World) -> None:
    permit = world.approved("general")
    isolation = apply(world)
    linked(world, permit, isolation)
    world.issue(permit)
    world.call("uma", "SuspendPermit", permit=permit, reason="Stop")
    world.call("uma", "UnlinkIsolation", permit=permit, isolation=isolation)
    assert events_of(world, permit, "Permit.IsolationUnlinked") == 1


def test_no_link_to_a_removed_isolation(world: World) -> None:
    permit = world.approved("general")
    isolation = apply(world)
    world.call("uma", "RemoveIsolation", isolation=isolation)
    message = raises(
        IsolationStateError, world, "uma", "LinkIsolation", permit=permit, isolation=isolation
    )
    assert message == MSG_LINK_REMOVED
    assert events_of(world, permit, "Permit.IsolationLinked") == 0


def test_linking_twice_and_unlinking_an_unlinked_one_are_fixed_messages_not_events(
    world: World,
) -> None:
    permit = world.approved("general")
    isolation = apply(world)
    assert raises(
        IsolationRuleError, world, "uma", "UnlinkIsolation", permit=permit, isolation=isolation
    ) == (MSG_NOT_LINKED)
    linked(world, permit, isolation)
    assert raises(
        IsolationRuleError, world, "uma", "LinkIsolation", permit=permit, isolation=isolation
    ) == (MSG_ALREADY_LINKED)
    assert events_of(world, permit, "Permit.IsolationLinked") == 1
    assert events_of(world, permit, "Permit.IsolationUnlinked") == 0


def test_a_hidden_or_missing_permit_or_isolation_answers_one_text(world: World) -> None:
    world.person("dan", ("user", "document_controller"), grant="superuser")
    permit = world.approved("general")
    isolation = apply(world)
    hidden = _hidden_permit(world)
    secret_point = apply(world, "dora", point_record_id=world.hidden_record())
    seen = {
        raises(RecordNotFoundError, world, "uma", name, permit=p, isolation=i)
        for name in ("LinkIsolation", "UnlinkIsolation")
        for p, i in (
            (hidden, isolation),
            ("01JXXXXXXXXXXXXXXXXXXXXXXX", isolation),
            (permit, secret_point),
            (permit, "01JXXXXXXXXXXXXXXXXXXXXXXX"),
            (isolation, isolation),  # an isolation is not a permit
            (permit, permit),  # a permit is not an isolation
        )
    }
    assert seen == {"no record with that id"}
    assert events_of(world, permit, "Permit.IsolationLinked") == 0
    assert events_of(world, hidden, "Permit.IsolationLinked") == 0
