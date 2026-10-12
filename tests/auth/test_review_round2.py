"""Fixes from the re-review of F1 to F4: dirty text in services, audit keys, the reserved slot."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from authworld import GOOD, OTHER, World
from tl_core.auth import accounts, audit, queries, seed, sessions
from tl_core.auth import password as pw
from tl_core.auth.errors import (
    AccountNotFoundError,
    AgentTokenNotFoundError,
    AuthBusyError,
    InvalidAccountError,
    InvalidCredentialsError,
)
from tl_core.auth.names import INVALID_KEY

WRONG = "this is not the password"
DIRTY = ["a\x00b", "\ud800", "x" * 70_000]


# --- item 2: every service that takes text from a caller checks it ---------------------------


@pytest.mark.parametrize("bad", DIRTY)
def test_lookups_by_a_dirty_name_or_id_find_nothing_and_the_pool_survives(
    world: World, bad: str
) -> None:
    root = world.admin("root")
    with world.factory(readonly=True) as uow:
        assert queries.find_account(uow.conn(), username=bad) is None
        assert queries.find_account(uow.conn(), account_id=bad) is None
        assert queries.list_agent_tokens(uow.conn(), account_id=bad) == []
        with pytest.raises(AccountNotFoundError):
            queries.get_account(uow.conn(), bad)
    with world.factory(readonly=True) as uow:  # the connection still works
        assert queries.get_account(uow.conn(), root.account_id).username == "root"


@pytest.mark.parametrize("bad", DIRTY)
def test_unlock_refuses_a_dirty_username_with_a_422_class_error(world: World, bad: str) -> None:
    with world.factory() as uow, pytest.raises(InvalidAccountError):
        accounts.unlock(uow, username=bad, by="svc:cli")
    world.admin("root")  # and the pool still works for a write afterwards


@pytest.mark.parametrize("bad", DIRTY)
def test_every_account_service_refuses_dirty_ids_and_reasons(world: World, bad: str) -> None:
    root = world.admin("root")
    bob = world.create("bob")
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        _, token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
        view = queries.list_agent_tokens(uow.conn())[0]
    assert token
    calls: list[Any] = [
        lambda u: accounts.disable(u, account_id=bad, by="user:root", reason=None),
        lambda u: accounts.enable(u, account_id=bad, by="user:root", reason=None),
        lambda u: accounts.set_roles(
            u, account_id=bad, roles=["user"], by="user:root", reason=None
        ),
        lambda u: accounts.issue_agent_token(u, account_id=bad, label="x", expires_at=None, by="u"),
    ]
    for call in calls:
        with world.factory() as uow, pytest.raises(AccountNotFoundError):
            call(uow)
    with world.factory() as uow, pytest.raises(AgentTokenNotFoundError):
        accounts.revoke_agent_token(uow, token_id=bad, by="user:root", reason=None)
    reasons: list[Any] = [
        lambda u: accounts.disable(u, account_id=bob.account_id, by="user:root", reason=bad),
        lambda u: accounts.set_roles(
            u, account_id=bob.account_id, roles=["admin"], by="user:root", reason=bad
        ),
        lambda u: accounts.revoke_agent_token(
            u, token_id=view.token_id, by="user:root", reason=bad
        ),
    ]
    for call in reasons:
        with world.factory() as uow, pytest.raises(InvalidAccountError):
            call(uow)
    with world.factory() as uow:  # nothing was half-done, and the pool works
        assert (
            accounts.disable(uow, account_id=bob.account_id, by="user:root", reason="ok").status
            == "disabled"
        )
    assert root.username == "root"


def test_a_blank_reason_is_the_same_as_none(world: World) -> None:
    world.admin("root")
    bob = world.create("bob")
    with world.factory() as uow:
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason="   ")
    assert '"reason":null' in world.events()[-1][3].replace(" ", "")


# --- item 3: audit keys are never what was typed, and repeats collapse -----------------------


def test_what_was_typed_as_a_username_is_never_stored(world: World) -> None:
    typed = "hunter2 my real password"
    for name in (typed, "a" * 100, "\x00", "\ud800", " bob"):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in(name, WRONG)
    keys = {r[0] for r in world.rows("SELECT username_key FROM auth_audit")}
    counters = {r[0] for r in world.rows("SELECT username_key FROM auth_attempt")}
    assert keys == {INVALID_KEY}  # NUL and surrogates write nothing at all
    assert counters <= {INVALID_KEY}
    dump = " ".join(
        str(r)
        for r in world.rows("SELECT * FROM auth_audit") + world.rows("SELECT * FROM auth_attempt")
    )
    assert "hunter2" not in dump and "password" not in dump


def test_garbage_names_share_one_counter_so_they_lock_together_and_harm_no_real_name(
    world: World,
) -> None:
    world.create("alice")
    for n in range(5):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in(f"not a name {n}", WRONG)
    from tl_core.auth.errors import AccountLockedError

    with pytest.raises(AccountLockedError):
        world.sign_in("another garbage name", GOOD)
    world.sign_in("alice")  # a real name is untouched


def test_repeated_failures_of_one_name_share_one_audit_row_with_a_count(world: World) -> None:
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("ghost", WRONG)
    [row] = world.rows("SELECT event, username_key, detail, count FROM auth_audit")
    assert row == ("sign_in_failed", "ghost", "bad_credentials", 4)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("other", WRONG)  # another name: its own row
    assert world.rows("SELECT COUNT(*) FROM auth_audit") == [(2,)]


def test_a_failure_after_the_collapse_window_is_a_new_row(world: World) -> None:
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("ghost", WRONG)
    world.clock.advance(minutes=16)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("ghost", WRONG)
    assert world.rows("SELECT COUNT(*) FROM auth_audit") == [(2,)]
    with world.factory(readonly=True) as uow:
        listed = audit.list_audit(uow.conn(), clock=world.clock)
    assert [e.count for e in listed] == [1, 1]


def test_a_flood_of_one_name_is_a_handful_of_rows_not_thousands(world: World) -> None:
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("victim", WRONG)
    from tl_core.auth.errors import AccountLockedError

    for _ in range(50):  # locked: refused before any write
        with pytest.raises(AccountLockedError):
            world.sign_in("victim", WRONG)
    assert world.rows("SELECT COUNT(*) FROM auth_audit") == [(2,)]  # one failure row, one lock row


# --- item 4: the reserved hash slot ----------------------------------------------------------


def test_a_sign_in_flood_cannot_take_the_slot_kept_for_admin_operations(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.create("alice")
    monkeypatch.setattr(pw, "GATE_TIMEOUT_S", 0.05)
    held = [pw._gate.acquire(public=True) for _ in range(pw.PUBLIC_HASH_SLOTS)]  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(AuthBusyError):
            world.sign_in("alice", GOOD)  # every public slot is taken
        prepared = pw.prepare_password(OTHER)  # an admin operation still gets its slot
        assert prepared.hash.startswith("scrypt$")
        assert seed.seed_demo(world.factory, env="dev") is not None
        with world.factory() as uow:
            accounts.create_account(
                uow, username="dave", display_name="D", kind="person", roles=["user"],
                password=prepared, by="user:root",
            )  # fmt: skip
    finally:
        for _ in held:
            pw._gate.release(public=True)  # pyright: ignore[reportPrivateUsage]


def test_one_admin_hash_in_flight_does_not_stop_sign_ins(world: World) -> None:
    world.create("alice")
    assert pw._gate.acquire()  # pyright: ignore[reportPrivateUsage]
    try:
        world.sign_in("alice", GOOD)  # three public slots are still free
    finally:
        pw._gate.release()  # pyright: ignore[reportPrivateUsage]


def test_the_gate_lanes_add_up_to_four_and_public_stops_at_three() -> None:
    gate = pw.HashGate(4, 3)
    assert [gate.acquire(0.01, public=True) for _ in range(4)] == [True, True, True, False]
    assert gate.acquire(0.01) is True  # the reserved slot
    assert gate.acquire(0.01) is False
    for _ in range(3):
        gate.release(public=True)
    gate.release()
    assert gate.acquire(0.01, public=True)


def test_a_waiting_hash_gets_the_slot_when_one_is_freed() -> None:
    gate = pw.HashGate(1, 1)
    assert gate.acquire(0.01, public=True)
    got: list[bool] = []
    waiter = threading.Thread(
        target=lambda: got.append(gate.acquire(2.0, public=True)), daemon=True
    )
    waiter.start()
    gate.release(public=True)
    waiter.join(timeout=5)
    assert got == [True]


def test_self_service_password_changes_use_the_public_lane(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    lanes: list[bool] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]

    def spying(password: str, salt: bytes, params: pw.ScryptParams) -> bytes:
        lanes.append(pw._PUBLIC_LANE.get())  # pyright: ignore[reportPrivateUsage]
        return real(password, salt, params)

    bob = world.create("bob")
    monkeypatch.setattr(pw, "_scrypt", spying)
    sessions.change_own_password(
        world.factory, account_id=bob.account_id, current_password=GOOD, new_password=OTHER,
        clock=world.clock,
    )  # fmt: skip
    assert lanes and all(lanes)  # verify and the new hash are both public
