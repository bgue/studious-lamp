"""Sign-in, sessions, lockout and bearer resolution (ADR-0009 sections 4 to 7)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from authworld import GOOD, OTHER, World
from tl_core.auth import accounts, sessions
from tl_core.auth import password as pw
from tl_core.auth.errors import (
    INVALID_CREDENTIALS_MESSAGE,
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
)
from tl_core.auth.password import prepare_password
from tl_core.auth.provider import PasswordIdentityProvider

WRONG = "this is not the password"


@pytest.fixture
def scrypt_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[pw.ScryptParams]]:
    calls: list[pw.ScryptParams] = []
    real = pw._scrypt  # pyright: ignore[reportPrivateUsage]

    def counting(password: str, salt: bytes, params: pw.ScryptParams) -> bytes:
        calls.append(params)
        return real(password, salt, params)

    monkeypatch.setattr(pw, "_scrypt", counting)
    yield calls


def fail(world: World, username: str, times: int = 1, password: str = WRONG) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in(username, password)


def test_signing_in_gives_a_principal_and_an_opaque_session_token(world: World) -> None:
    created = world.create("Alice", roles=("user",))
    principal, token = world.sign_in("ALICE")
    assert principal.actor == "user:alice" and principal.account_id == created.account_id
    assert principal.roles == ["user"] and principal.via == "session" and not principal.is_admin
    assert token.startswith("tls_") and len(token) == 47


def test_only_the_hash_of_the_session_token_is_stored_and_it_expires_in_12_hours(
    world: World,
) -> None:
    world.create("alice")
    _, token = world.sign_in("alice")
    [(stored, created, expires)] = world.rows(
        "SELECT token_hash, created_at, expires_at FROM auth_session"
    )
    assert stored != token and token not in stored
    assert sessions.SESSION_TTL == timedelta(hours=12)
    assert datetime.fromisoformat(expires) - datetime.fromisoformat(created) == timedelta(hours=12)
    assert token not in str(world.rows("SELECT * FROM auth_session"))


def test_the_session_resolves_to_the_principal_until_it_ends(world: World) -> None:
    world.create("alice")
    _, token = world.sign_in("alice")
    found = sessions.principal_for_bearer(world.factory, token, clock=world.clock)
    assert found.actor == "user:alice" and found.via == "session"
    world.clock.advance(hours=11, minutes=59)
    sessions.principal_for_bearer(world.factory, token, clock=world.clock)
    world.clock.advance(minutes=2)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token, clock=world.clock)


def test_sign_out_ends_the_session_and_is_idempotent(world: World) -> None:
    world.create("alice")
    _, token = world.sign_in("alice")
    _, other = world.sign_in("alice")
    sessions.sign_out(world.factory, token=token)
    sessions.sign_out(world.factory, token=token)
    sessions.sign_out(world.factory, token="not a token")
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)
    sessions.principal_for_bearer(world.factory, other)  # the other session is untouched


def test_an_unknown_user_and_a_wrong_password_are_indistinguishable(world: World) -> None:
    world.create("alice")
    with pytest.raises(InvalidCredentialsError) as wrong:
        world.sign_in("alice", WRONG)
    with pytest.raises(InvalidCredentialsError) as unknown:
        world.sign_in("nobody", WRONG)
    assert type(wrong.value) is type(unknown.value)
    assert str(wrong.value) == str(unknown.value) == INVALID_CREDENTIALS_MESSAGE
    assert wrong.value.args == unknown.value.args


@pytest.mark.parametrize("username", ["alice", "nobody", "bot", "gone"])
def test_every_failed_sign_in_costs_exactly_one_scrypt(
    world: World, scrypt_calls: list[pw.ScryptParams], username: str
) -> None:
    world.create("alice")
    world.create("bot", kind="agent")
    bob = world.create("gone")
    with world.factory() as uow:
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason=None)
    scrypt_calls.clear()
    fail(world, username)
    assert len(scrypt_calls) == 1


def test_a_correct_sign_in_also_costs_one_scrypt(
    world: World, scrypt_calls: list[pw.ScryptParams]
) -> None:
    world.create("alice")
    scrypt_calls.clear()
    world.sign_in("alice")
    assert len(scrypt_calls) == 1


def test_an_agent_account_cannot_sign_in_with_any_password(world: World) -> None:
    world.create("bot", kind="agent")
    for attempt in ("", GOOD, "bot", WRONG):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("bot", attempt)


def test_five_failures_lock_the_name_even_against_the_right_password(world: World) -> None:
    world.create("alice")
    fail(world, "alice", 5)
    with pytest.raises(AccountLockedError) as locked:
        world.sign_in("alice", GOOD)
    assert locked.value.locked_until is not None and GOOD not in str(locked.value)
    assert world.sign_in is not None
    with world.factory(readonly=True) as uow:
        from tl_core.auth import queries

        [view] = [a for a in queries.list_accounts(uow.conn()) if a.username == "alice"]
    assert view.locked_until == locked.value.locked_until


def test_a_locked_name_is_refused_before_any_password_is_hashed(
    world: World, scrypt_calls: list[pw.ScryptParams]
) -> None:
    world.create("alice")
    fail(world, "alice", 5)
    scrypt_calls.clear()
    for attempt in (GOOD, WRONG):
        with pytest.raises(AccountLockedError):
            world.sign_in("alice", attempt)
    assert scrypt_calls == []


def test_an_unknown_name_locks_exactly_like_a_real_one(world: World) -> None:
    world.create("alice")
    fail(world, "alice", 5)
    fail(world, "ghost", 5)
    with pytest.raises(AccountLockedError) as real:
        world.sign_in("alice", WRONG)
    with pytest.raises(AccountLockedError) as ghost:
        world.sign_in("ghost", WRONG)
    assert type(real.value) is type(ghost.value)
    assert str(real.value).split(";")[0] == str(ghost.value).split(";")[0]
    assert real.value.locked_until and ghost.value.locked_until


def test_spelling_variants_of_a_name_share_one_counter(world: World) -> None:
    world.create("alice")
    for spelling in ("alice", "ALICE", "Alice", "ａｌｉｃｅ", "alice"):
        fail(world, spelling)
    with pytest.raises(AccountLockedError):
        world.sign_in("aLiCe", GOOD)


def test_the_lock_lasts_15_minutes_then_the_right_password_works(world: World) -> None:
    world.create("alice")
    fail(world, "alice", 5)
    world.clock.advance(minutes=14)
    with pytest.raises(AccountLockedError):
        world.sign_in("alice", GOOD)
    world.clock.advance(minutes=2)
    world.sign_in("alice", GOOD)
    assert world.rows("SELECT COUNT(*) FROM auth_attempt") == [(0,)]


def test_every_lock_lasts_15_minutes_for_every_name_so_nothing_tells_which_names_exist(
    world: World,
) -> None:
    """Review item 1: no doubling. A longer lock for admins or repeat offenders is an oracle."""
    assert sessions.LOCK_DURATION == timedelta(minutes=15)
    world.admin("boss")
    world.create("bob")
    for name in ("boss", "bob", "ghost"):
        for _ in range(3):  # three locks in a row, each the same length
            fail(world, name, 5)
            [(until,)] = world.rows(
                "SELECT locked_until FROM auth_attempt WHERE username_key = :k", k=name
            )
            lock_start = datetime.fromisoformat(until) - sessions.LOCK_DURATION
            assert abs((datetime.now(UTC) + world.clock.offset - lock_start).total_seconds()) < 30
            world.clock.advance(minutes=16)


def test_failures_older_than_the_window_do_not_add_up(world: World) -> None:
    world.create("alice")
    fail(world, "alice", 4)
    world.clock.advance(minutes=16)
    fail(world, "alice", 4)
    world.sign_in("alice", GOOD)  # never reached five inside one window


def test_a_success_clears_the_counter(world: World) -> None:
    world.create("alice")
    fail(world, "alice", 4)
    world.sign_in("alice", GOOD)
    fail(world, "alice", 4)
    world.sign_in("alice", GOOD)


def test_old_counter_rows_are_pruned_when_a_new_failure_is_recorded(world: World) -> None:
    for n in range(5):
        fail(world, f"ghost{n}")
    assert world.rows("SELECT COUNT(*) FROM auth_attempt") == [(5,)]
    world.clock.advance(hours=25)
    fail(world, "fresh")
    assert world.rows("SELECT username_key FROM auth_attempt") == [("fresh",)]


def test_a_disabled_account_is_reported_only_after_the_right_password(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    with world.factory() as uow:
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason=None)
    fail(world, "bob", 1, WRONG)  # looks like any other wrong password
    with pytest.raises(AccountDisabledError):
        world.sign_in("bob", GOOD)
    with world.factory() as uow:
        accounts.enable(uow, account_id=bob.account_id, by="user:root", reason=None)
    world.sign_in("bob", GOOD)


def test_disabling_ends_every_session_and_enabling_does_not_bring_them_back(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    _, token = world.sign_in("bob")
    with world.factory() as uow:
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason=None)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)
    with world.factory() as uow:
        accounts.enable(uow, account_id=bob.account_id, by="user:root", reason=None)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)


def test_changing_the_password_ends_every_session(world: World) -> None:
    bob = world.create("bob")
    _, first = world.sign_in("bob")
    _, second = world.sign_in("bob")
    with world.factory() as uow:
        accounts.change_password(
            uow, account_id=bob.account_id, new_password=prepare_password(OTHER), by="user:root"
        )
    for token in (first, second):
        with pytest.raises(InvalidCredentialsError):
            sessions.principal_for_bearer(world.factory, token)


def test_a_role_change_applies_to_a_live_session_at_once(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    _, token = world.sign_in("bob")
    assert not sessions.principal_for_bearer(world.factory, token).is_admin
    with world.factory() as uow:
        accounts.set_roles(
            uow, account_id=bob.account_id, roles=["admin"], by="user:root", reason=None
        )
    assert sessions.principal_for_bearer(world.factory, token).is_admin


def test_a_password_reset_clears_the_lock(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    fail(world, "bob", 5)
    with pytest.raises(AccountLockedError):
        world.sign_in("bob", GOOD)
    with world.factory() as uow:
        accounts.change_password(
            uow, account_id=bob.account_id, new_password=prepare_password(OTHER), by="user:root"
        )
    world.sign_in("bob", OTHER)


def test_the_password_provider_authenticates_without_opening_a_session(world: World) -> None:
    world.create("alice")
    provider = PasswordIdentityProvider(world.factory, clock=world.clock)
    principal = provider.authenticate_password("alice", GOOD)
    assert principal.via == "password" and principal.actor == "user:alice"
    assert world.rows("SELECT COUNT(*) FROM auth_session") == [(0,)]
    with pytest.raises(InvalidCredentialsError):
        provider.authenticate_password("alice", WRONG)
    _, token = world.sign_in("alice")
    assert provider.principal_for_bearer(token).via == "session"


def test_an_agent_token_resolves_to_an_agent_principal(world: World) -> None:
    bot = world.create("triage", kind="agent")
    expires = datetime.now(UTC) + timedelta(days=1)
    with world.factory() as uow:
        view, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="t",
            expires_at=expires,
            by="user:root",
            clock=world.clock,
        )
    principal = sessions.principal_for_bearer(world.factory, token, clock=world.clock)
    assert (principal.actor, principal.kind, principal.via) == (
        "agent:triage",
        "agent",
        "agent_token",
    )
    assert principal.roles == ["user"] and not principal.is_admin
    world.clock.advance(days=1, minutes=1)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token, clock=world.clock)
    assert view.token_id


def test_a_revoked_or_orphaned_agent_token_stops_working(world: World) -> None:
    bot = world.create("triage", kind="agent")
    with world.factory() as uow:
        view, token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
    sessions.principal_for_bearer(world.factory, token)
    with world.factory() as uow:
        accounts.revoke_agent_token(uow, token_id=view.token_id, by="user:root", reason=None)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)


def test_a_disabled_agent_account_stops_its_tokens(world: World) -> None:
    world.admin()
    bot = world.create("triage", kind="agent")
    with world.factory() as uow:
        _, token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
        accounts.disable(uow, account_id=bot.account_id, by="user:root", reason=None)
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)
    with world.factory() as uow:
        accounts.enable(uow, account_id=bot.account_id, by="user:root", reason=None)
    sessions.principal_for_bearer(world.factory, token)  # the token itself was not revoked


def test_a_token_only_works_in_its_own_table(world: World) -> None:
    bot = world.create("triage", kind="agent")
    world.create("alice")
    _, session = world.sign_in("alice")
    with world.factory() as uow:
        _, agent = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="t", expires_at=None, by="user:root"
        )
    swapped_agent = "tla_" + session.removeprefix("tls_")
    swapped_session = "tls_" + agent.removeprefix("tla_")
    for token in (swapped_agent, swapped_session):
        with pytest.raises(InvalidCredentialsError):
            sessions.principal_for_bearer(world.factory, token)


@pytest.mark.parametrize(
    "token",
    ["", " ", "tls_", "tla_", "tls_" + "A" * 43, "Bearer x", "x" * 1000, "tls_é", "tls_\ud800"],
)
def test_garbage_bearer_values_are_one_invalid_credentials_error(world: World, token: str) -> None:
    with pytest.raises(InvalidCredentialsError) as raised:
        sessions.principal_for_bearer(world.factory, token)
    assert str(raised.value) == "invalid or expired token"


def test_a_wrong_current_password_counts_towards_lockout(world: World) -> None:
    bob = world.create("bob")
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            sessions.change_own_password(
                world.factory,
                account_id=bob.account_id,
                current_password=WRONG,
                new_password=OTHER,
                clock=world.clock,
            )
    with pytest.raises(AccountLockedError):
        world.sign_in("bob", GOOD)
    with pytest.raises(AccountLockedError):
        sessions.change_own_password(
            world.factory,
            account_id=bob.account_id,
            current_password=GOOD,
            new_password=OTHER,
            clock=world.clock,
        )


def test_changing_your_own_password_ends_your_sessions_and_sets_the_new_one(world: World) -> None:
    bob = world.create("bob")
    _, token = world.sign_in("bob")
    sessions.change_own_password(
        world.factory,
        account_id=bob.account_id,
        current_password=GOOD,
        new_password=OTHER,
        clock=world.clock,
    )
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(world.factory, token)
    world.sign_in("bob", OTHER)


def test_a_hash_made_with_a_weaker_cost_is_replaced_at_the_next_sign_in(world: World) -> None:
    previous = pw.configure(pw.ScryptParams(log2_n=3, r=1, p=1))
    try:
        world.create("alice")
    finally:
        pw.configure(previous)
    [(before,)] = world.rows("SELECT password_hash FROM auth_credential")
    assert before.startswith("scrypt$3$1$1$")
    world.sign_in("alice")
    [(after,)] = world.rows("SELECT password_hash FROM auth_credential")
    assert after.startswith("scrypt$4$1$1$") and after != before
    world.sign_in("alice")  # and it still verifies


def test_nothing_secret_reaches_the_log(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    world.create("alice")
    _, token = world.sign_in("alice")
    fail(world, "alice", 5, WRONG)
    with pytest.raises(AccountLockedError):
        world.sign_in("alice", GOOD)
    sessions.sign_out(world.factory, token=token)
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    for secret in (GOOD, WRONG, token, token.removeprefix("tls_")):
        assert secret not in text
