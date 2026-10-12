"""Account services against a real ledger (ADR-0009): events, projections, rules, no secrets."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from authworld import GOOD, OTHER, World
from tl_adapters.db import rebuild_projections
from tl_core.auth import accounts, queries, sessions
from tl_core.auth.errors import (
    AccountNotFoundError,
    AccountStateError,
    AgentTokenNotFoundError,
    InvalidAccountError,
    InvalidCredentialsError,
    LastAdminError,
    UsernameTakenError,
    WeakPasswordError,
)
from tl_core.auth.password import prepare_password
from tl_core.ledger import ConcurrencyError


def test_creating_an_account_appends_one_metadata_event_and_a_projection_row(world: World) -> None:
    view = world.create("Alice", roles=("user",))
    assert (view.username, view.kind, view.roles, view.status) == (
        "alice",
        "person",
        ["user"],
        "active",
    )
    assert view.locked_until is None and view.seq >= 1
    [(event_type, stream_id, actor, payload)] = world.events()
    assert (event_type, stream_id, actor) == (
        "Account.Created",
        f"account:{view.account_id}",
        "user:root",
    )
    assert GOOD not in payload and "scrypt" not in payload and "password" not in payload


def test_the_username_is_unique_across_kinds_and_case(world: World) -> None:
    world.create("triage", kind="agent")
    for name in ("triage", "TRIAGE", "Triage"):
        with pytest.raises(UsernameTakenError):
            world.create(name, password=GOOD)
    assert len(world.events()) == 1  # the refused creates left no event


def test_invalid_accounts_are_refused(world: World) -> None:
    with pytest.raises(InvalidAccountError):
        world.create("a b")
    with pytest.raises(InvalidAccountError):
        world.create("alice", roles=())
    with pytest.raises(InvalidAccountError):
        world.create("alice", roles=("root",))
    with pytest.raises(InvalidAccountError):
        world.create("bot", kind="agent", roles=("admin",))
    with pytest.raises(InvalidAccountError):
        world.create("sim-1", kind="sim", roles=("admin",))
    with world.factory() as uow, pytest.raises(InvalidAccountError):
        accounts.create_account(
            uow, username="bot", display_name="Bot", kind="agent", roles=["user"],
            password=prepare_password(GOOD), by="user:root",
        )  # fmt: skip
    assert world.events() == []


def test_a_weak_password_is_refused_and_nothing_is_written(world: World) -> None:
    with pytest.raises(WeakPasswordError):
        world.create("alice", password="short")
    assert world.events() == []
    assert world.rows("SELECT COUNT(*) FROM auth_credential") == [(0,)]


def test_the_password_lives_only_in_the_operational_table_as_a_hash(world: World) -> None:
    view = world.create("alice")
    [(stored,)] = world.rows(
        "SELECT password_hash FROM auth_credential WHERE account_id = :a", a=view.account_id
    )
    assert stored.startswith("scrypt$") and GOOD not in stored
    everything = " ".join(
        str(row)
        for table in ("events", "cur_account")
        for row in world.rows(f"SELECT * FROM {table}")
    )
    assert GOOD not in everything and stored not in everything


def test_roles_can_change_and_a_no_op_is_refused(world: World) -> None:
    world.admin()
    user = world.create("bob")
    with world.factory() as uow:
        changed = accounts.set_roles(
            uow, account_id=user.account_id, roles=["admin", "user"], by="user:root", reason="cover"
        )
    assert changed.roles == ["admin", "user"]
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.set_roles(
            uow, account_id=user.account_id, roles=["user", "admin"], by="user:root", reason=None
        )
    with world.factory(readonly=True) as uow:
        assert queries.count_active_admins(uow.conn()) == 2


def test_the_last_active_admin_cannot_be_demoted_or_disabled(world: World) -> None:
    only = world.admin()
    with world.factory() as uow, pytest.raises(LastAdminError):
        accounts.set_roles(
            uow, account_id=only.account_id, roles=["user"], by="user:root", reason=None
        )
    with world.factory() as uow, pytest.raises(LastAdminError):
        accounts.disable(uow, account_id=only.account_id, by="user:root", reason="no")
    second = world.admin("second")
    with world.factory() as uow:
        accounts.disable(uow, account_id=second.account_id, by="user:root", reason="ok")
    with world.factory() as uow, pytest.raises(LastAdminError):  # a disabled admin does not count
        accounts.disable(uow, account_id=only.account_id, by="user:root", reason="no")
    with world.factory() as uow:  # a non-admin can always be disabled
        user = accounts.create_account(
            uow, username="bob", display_name="Bob", kind="person", roles=["user"],
            password=prepare_password(GOOD), by="user:root",
        )  # fmt: skip
        accounts.disable(uow, account_id=user.account_id, by="user:root", reason=None)


def test_two_admins_cannot_disable_each_other_at_once(world: World) -> None:
    """Holds because write transactions take the ledger's single writer lock (ADR-0009 s8).

    It cannot fail while that lock is global; it is here to fail if the lock ever becomes finer.
    """
    first, second = world.admin("one"), world.admin("two")
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def attempt(target: str) -> None:
        barrier.wait(timeout=10)
        try:
            with world.factory() as uow:
                accounts.disable(uow, account_id=target, by="user:root", reason="race")
            outcomes.append("disabled")
        except LastAdminError:
            outcomes.append("refused")
        except ConcurrencyError:
            outcomes.append("conflict")

    threads = [
        threading.Thread(target=attempt, args=(first.account_id,), daemon=True),
        threading.Thread(target=attempt, args=(second.account_id,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes.count("disabled") == 1, outcomes
    with world.factory(readonly=True) as uow:
        assert queries.count_active_admins(uow.conn()) == 1


def test_disable_and_enable_are_events_and_state_checked(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    with world.factory() as uow:
        assert (
            accounts.disable(uow, account_id=bob.account_id, by="user:root", reason="left").status
            == "disabled"
        )
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.disable(uow, account_id=bob.account_id, by="user:root", reason=None)
    with world.factory() as uow:
        assert (
            accounts.enable(uow, account_id=bob.account_id, by="user:root", reason="back").status
            == "active"
        )
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.enable(uow, account_id=bob.account_id, by="user:root", reason=None)
    types = [e[0] for e in world.events()]
    assert types == ["Account.Created", "Account.Created", "Account.Disabled", "Account.Enabled"]


def test_an_unknown_account_is_not_found(world: World) -> None:
    for call in (
        lambda uow: accounts.disable(uow, account_id="nope", by="user:root", reason=None),
        lambda uow: accounts.set_roles(
            uow, account_id="nope", roles=["user"], by="user:root", reason=None
        ),
        lambda uow: accounts.change_password(
            uow, account_id="nope", new_password=prepare_password(GOOD), by="user:root"
        ),
    ):
        with world.factory() as uow, pytest.raises(AccountNotFoundError):
            call(uow)


def test_an_admin_reset_needs_no_current_password_and_is_forced(world: World) -> None:
    admin = world.admin()
    bob = world.create("bob")
    with world.factory() as uow:
        accounts.change_password(
            uow, account_id=bob.account_id, new_password=prepare_password(OTHER), by="user:root"
        )
    world.sign_in("bob", OTHER)
    last = world.events()[-1]
    assert last[0] == "Account.PasswordChanged" and '"forced":true' in last[3].replace(" ", "")
    assert OTHER not in last[3]
    assert last[2] == "user:root" and admin.username == "root"


def test_a_self_service_change_needs_the_current_password_and_is_not_forced(
    world: World,
) -> None:
    bob = world.create("bob")
    for current in ("not the password", ""):
        with pytest.raises(InvalidCredentialsError):
            sessions.change_own_password(
                world.factory, account_id=bob.account_id, current_password=current,
                new_password=OTHER, clock=world.clock,
            )  # fmt: skip
    sessions.change_own_password(
        world.factory, account_id=bob.account_id, current_password=GOOD, new_password=OTHER,
        clock=world.clock,
    )  # fmt: skip
    world.sign_in("bob", OTHER)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("bob", GOOD)
    assert '"forced":false' in world.events()[-1][3].replace(" ", "")


def test_a_new_password_must_meet_the_policy(world: World) -> None:
    bob = world.create("bob")
    with pytest.raises(WeakPasswordError):
        prepare_password("bob", username="bob")
    with pytest.raises(WeakPasswordError):
        sessions.change_own_password(
            world.factory, account_id=bob.account_id, current_password=GOOD, new_password="short",
            clock=world.clock,
        )  # fmt: skip
    world.sign_in("bob", GOOD)  # the old password still works


def test_an_agent_account_has_no_password(world: World) -> None:
    bot = world.create("bot", kind="agent")
    with world.factory() as uow, pytest.raises(InvalidAccountError):
        accounts.change_password(
            uow, account_id=bot.account_id, new_password=prepare_password(GOOD), by="user:root"
        )


def test_agent_tokens_are_issued_once_stored_hashed_and_revocable(world: World) -> None:
    bot = world.create("triage", kind="agent")
    expires = datetime.now(UTC) + timedelta(days=30)
    with world.factory() as uow:
        view, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="triage assistant",
            expires_at=expires,
            by="user:root",
        )
    assert token.startswith("tla_") and view.label == "triage assistant" and not view.revoked
    [(stored_hash,)] = world.rows("SELECT token_hash FROM auth_token_secret")
    assert stored_hash != token and token not in str(world.rows("SELECT * FROM auth_token_secret"))
    issued = [e for e in world.events() if e[0] == "AgentToken.Issued"]
    assert len(issued) == 1 and token not in issued[0][3] and stored_hash not in issued[0][3]
    with world.factory() as uow:
        revoked = accounts.revoke_agent_token(
            uow, token_id=view.token_id, by="user:root", reason="rotated"
        )
    assert revoked.revoked
    assert world.rows("SELECT COUNT(*) FROM auth_token_secret") == [(0,)]
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.revoke_agent_token(uow, token_id=view.token_id, by="user:root", reason=None)
    with world.factory(readonly=True) as uow:
        [listed] = queries.list_agent_tokens(uow.conn(), account_id=bot.account_id)
    assert listed.revoked and listed.token_id == view.token_id


def test_only_an_active_agent_account_gets_tokens(world: World) -> None:
    person = world.create("bob")
    bot = world.create("bot", kind="agent")
    with world.factory() as uow, pytest.raises(InvalidAccountError):
        accounts.issue_agent_token(
            uow, account_id=person.account_id, label="x", expires_at=None, by="user:root"
        )
    with world.factory() as uow:
        accounts.disable(uow, account_id=bot.account_id, by="user:root", reason=None)
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="x", expires_at=None, by="user:root"
        )
    with world.factory() as uow, pytest.raises(AgentTokenNotFoundError):
        accounts.revoke_agent_token(uow, token_id="missing", by="user:root", reason=None)


def test_token_expiry_must_be_in_the_future_and_aware(world: World) -> None:
    bot = world.create("bot", kind="agent")
    for bad in (datetime.now(UTC) - timedelta(seconds=1), datetime.now()):
        with world.factory() as uow, pytest.raises(InvalidAccountError):
            accounts.issue_agent_token(
                uow, account_id=bot.account_id, label="x", expires_at=bad, by="user:root"
            )


def test_an_agent_holds_a_bounded_number_of_live_tokens(world: World) -> None:
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        for n in range(accounts.MAX_ACTIVE_TOKENS_PER_AGENT):
            accounts.issue_agent_token(
                uow, account_id=bot.account_id, label=f"t{n}", expires_at=None, by="user:root"
            )
    with world.factory() as uow, pytest.raises(AccountStateError):
        accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="one more", expires_at=None, by="user:root"
        )


def test_the_projection_rebuilds_from_events_and_keeps_the_secrets(world: World) -> None:
    admin = world.admin()
    bot = world.create("bot", kind="agent")
    with world.factory() as uow:
        view, token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="a", expires_at=None, by="user:root"
        )
    before = world.rows("SELECT * FROM cur_account ORDER BY account_id")
    before_tokens = world.rows("SELECT * FROM cur_agent_token")
    world.factory.dispose()
    rebuild_projections(world.db)
    assert world.rows("SELECT * FROM cur_account ORDER BY account_id") == before
    assert world.rows("SELECT * FROM cur_agent_token") == before_tokens
    assert world.rows("SELECT COUNT(*) FROM auth_credential") == [(1,)]  # admin's hash survived
    assert world.rows("SELECT COUNT(*) FROM auth_token_secret") == [(1,)]
    assert admin.username == "root" and view.token_id and token


def test_listing_shows_every_account_without_secrets(world: World) -> None:
    world.admin()
    world.create("bob")
    world.create("bot", kind="agent")
    with world.factory(readonly=True) as uow:
        listed = queries.list_accounts(uow.conn())
    assert [a.username for a in listed] == ["root", "bob", "bot"]
    dumped = " ".join(a.model_dump_json() for a in listed)
    assert "scrypt" not in dumped and GOOD not in dumped
    with world.factory(readonly=True) as uow:
        assert queries.find_account(uow.conn(), username="BOB") is not None
        assert queries.find_account(uow.conn(), username="nobody") is None
        with pytest.raises(AccountNotFoundError):
            queries.get_account(uow.conn(), "nope")
