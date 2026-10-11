"""Fixes from the final security re-review: dirty ids and event names in the last three services."""

from __future__ import annotations

import pytest
from authworld import GOOD, OTHER, World
from tl_core.auth import audit, sessions
from tl_core.auth.errors import InvalidAccountError, InvalidCredentialsError

DIRTY = ["a\x00b", "\ud800", "x" * 70_000]


@pytest.mark.parametrize("bad", DIRTY)
def test_sign_out_all_refuses_a_dirty_account_id_and_the_pool_survives(
    world: World, bad: str
) -> None:
    bob = world.create("bob")
    with pytest.raises(InvalidAccountError):
        sessions.sign_out_all(world.factory, account_id=bad)
    sessions.sign_out_all(world.factory, account_id=bob.account_id)  # a good one still works


@pytest.mark.parametrize("bad", DIRTY)
def test_change_own_password_answers_a_dirty_account_id_like_an_unknown_one(
    world: World, bad: str
) -> None:
    bob = world.create("bob")
    with pytest.raises(InvalidCredentialsError, match="current password is incorrect"):
        sessions.change_own_password(
            world.factory, account_id=bad, current_password=GOOD, new_password=OTHER,
            clock=world.clock,
        )  # fmt: skip
    sessions.change_own_password(
        world.factory, account_id=bob.account_id, current_password=GOOD, new_password=OTHER,
        clock=world.clock,
    )  # fmt: skip


@pytest.mark.parametrize("bad", [*DIRTY, "not_an_event", "SIGN_IN", ""])
def test_list_audit_takes_only_known_event_names(world: World, bad: str) -> None:
    world.create("bob")
    with world.factory(readonly=True) as uow, pytest.raises(InvalidAccountError):
        audit.list_audit(uow.conn(), event=bad, clock=world.clock)
    with world.factory(readonly=True) as uow:
        rows = audit.list_audit(uow.conn(), event=audit.EVENTS[0], clock=world.clock)
        assert isinstance(rows, list)  # a known one is fine, and the connection still works
