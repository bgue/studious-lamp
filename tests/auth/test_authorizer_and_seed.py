"""The role authorizer, the demo seed and bootstrap (ADR-0009 sections 8, 9 and 10)."""

from __future__ import annotations

import pytest
from authworld import GOOD, OTHER, World
from sqlalchemy import text
from tl_core.auth import accounts, queries, seed, sessions
from tl_core.auth.errors import (
    AccountStateError,
    ForbiddenError,
    InvalidAccountError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from tl_core.auth.provider import RoleAuthorizer
from tl_core.auth.types import DEMO_PASSWORD, DEMO_USERNAME, AccountKind, Principal, Role


def principal(kind: AccountKind = "person", roles: tuple[Role, ...] = ("user",)) -> Principal:
    return Principal(
        actor=f"{'agent' if kind == 'agent' else 'user'}:x",
        account_id="a1",
        kind=kind,
        roles=list(roles),
        via="session",
    )


def test_an_admin_may_do_everything() -> None:
    authorizer = RoleAuthorizer()
    for action in (
        "record.read",
        "command.CreateRecord",
        "admin.accounts.list",
        "admin.tokens.issue",
    ):
        authorizer.authorize(principal(roles=("admin",)), action, "/x")


def test_a_user_may_do_everything_except_admin_actions() -> None:
    authorizer = RoleAuthorizer()
    authorizer.authorize(principal(), "record.read", "/records")
    authorizer.authorize(principal(), "command.CreateRecord", "/commands/CreateRecord")
    authorizer.authorize(principal(), "administer", "/x")  # the prefix is "admin." with the dot
    for action in ("admin.accounts.list", "admin.users.create", "admin.x"):
        with pytest.raises(ForbiddenError):
            authorizer.authorize(principal(), action, "/admin/accounts")


def test_an_agent_is_never_admin_whatever_its_roles_say() -> None:
    authorizer = RoleAuthorizer()
    authorizer.authorize(principal("agent"), "record.read", "/records")
    with pytest.raises(ForbiddenError):
        authorizer.authorize(principal("agent", ("admin",)), "admin.accounts.list", "/admin")


def test_a_principal_without_roles_may_do_nothing() -> None:
    with pytest.raises(ForbiddenError):
        RoleAuthorizer().authorize(principal(roles=()), "record.read", "/records")


def test_the_refusal_names_the_action_and_nothing_secret() -> None:
    with pytest.raises(ForbiddenError) as raised:
        RoleAuthorizer().authorize(principal(), "admin.accounts.list", "/admin/accounts?token=abc")
    assert "admin.accounts.list" in str(raised.value) and "abc" not in str(raised.value)


# --- the demo seed -------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["dev", "demo", "test"])
def test_the_demo_account_is_seeded_in_dev_demo_and_test(world: World, env: str) -> None:
    view = seed.seed_demo(world.factory, env=env)
    assert view is not None and view.username == DEMO_USERNAME == "demo"
    assert view.roles == ["admin"] and view.kind == "person" and view.status == "active"
    principal_, token = world.sign_in("demo", DEMO_PASSWORD)
    assert principal_.is_admin and token.startswith("tls_")


@pytest.mark.parametrize("env", ["prod", "production", "ci", "", "staging"])
def test_the_demo_account_is_never_seeded_elsewhere(world: World, env: str) -> None:
    assert seed.seed_demo(world.factory, env=env) is None
    assert world.rows("SELECT COUNT(*) FROM cur_account") == [(0,)]
    assert world.events() == []


def test_seeding_twice_changes_nothing_and_keeps_a_changed_password(world: World) -> None:
    first = seed.seed_demo(world.factory, env="dev")
    assert first is not None
    with world.factory() as uow:
        accounts.change_password(
            uow, account_id=first.account_id, new_password=OTHER, by="user:root"
        )
    again = seed.seed_demo(world.factory, env="dev")
    assert again is not None and again.account_id == first.account_id
    assert len(world.events()) == 2
    world.sign_in("demo", OTHER)
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("demo", DEMO_PASSWORD)


def test_the_demo_password_is_the_only_exception_to_the_policy(world: World) -> None:
    with pytest.raises(WeakPasswordError):
        world.create("alice", password=DEMO_PASSWORD)
    with world.factory() as uow, pytest.raises(WeakPasswordError):
        accounts.create_account(
            uow, username="demo2", display_name="D", kind="person", roles=["user"],
            password="demo", by="user:root",
        )  # fmt: skip


def test_the_server_can_tell_whether_the_demo_account_is_enabled(world: World) -> None:
    with world.factory(readonly=True) as uow:
        assert queries.demo_account_enabled(uow.conn()) is False
    view = seed.seed_demo(world.factory, env="dev")
    assert view is not None
    with world.factory(readonly=True) as uow:
        assert queries.demo_account_enabled(uow.conn()) is True
    world.admin("someone")
    with world.factory() as uow:
        accounts.disable(uow, account_id=view.account_id, by="user:root", reason="real use")
    with world.factory(readonly=True) as uow:
        assert queries.demo_account_enabled(uow.conn()) is False


# --- bootstrap and recovery -----------------------------------------------------------------


def test_bootstrap_creates_the_first_admin_once(world: World) -> None:
    view = seed.bootstrap_admin(
        world.factory, username="Boss", password=GOOD, display_name="The Boss"
    )
    assert view.username == "boss" and view.roles == ["admin"]
    principal_, _ = world.sign_in("boss", GOOD)
    assert principal_.is_admin
    with pytest.raises(AccountStateError):
        seed.bootstrap_admin(world.factory, username="other", password=GOOD)
    with pytest.raises(AccountStateError):  # not even for the same name: sign in and reset instead
        seed.bootstrap_admin(world.factory, username="boss", password=OTHER)


def test_bootstrap_applies_the_password_policy(world: World) -> None:
    with pytest.raises(WeakPasswordError):
        seed.bootstrap_admin(world.factory, username="boss", password="short")
    assert world.rows("SELECT COUNT(*) FROM cur_account") == [(0,)]


def test_bootstrap_recovers_an_admin_whose_password_is_missing(world: World) -> None:
    """The state after a restore from the archive: accounts exist, no password does."""
    admin = world.admin("boss")
    with world.factory() as uow:
        uow.conn().execute(text("DELETE FROM auth_credential"))
    with pytest.raises(InvalidCredentialsError):
        world.sign_in("boss", GOOD)
    recovered = seed.bootstrap_admin(world.factory, username="boss", password=OTHER)
    assert recovered.account_id == admin.account_id
    world.sign_in("boss", OTHER)
    assert world.events()[-1][0] == "Account.PasswordChanged"
    assert OTHER not in world.events()[-1][3]


def test_bootstrap_will_not_promote_or_revive_other_accounts(world: World) -> None:
    world.create("bob")  # a user, and nobody is admin
    with pytest.raises(InvalidAccountError):
        seed.bootstrap_admin(world.factory, username="bob", password=OTHER)
    root = world.admin("boss")
    with world.factory() as uow:
        uow.conn().execute(text("DELETE FROM auth_credential"))
        accounts.create_account(
            uow, username="spare", display_name="S", kind="person", roles=["admin"], password=None,
            by="user:root",
        )  # fmt: skip
        accounts.disable(uow, account_id=root.account_id, by="user:root", reason="x")
    with pytest.raises(AccountStateError):
        seed.bootstrap_admin(world.factory, username="boss", password=OTHER)


def test_bootstrap_clears_a_lock_on_the_admin(world: World) -> None:
    world.admin("boss")
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            world.sign_in("boss", "this is wrong")
    with world.factory() as uow:
        uow.conn().execute(text("DELETE FROM auth_credential"))
    seed.bootstrap_admin(world.factory, username="boss", password=OTHER)
    world.sign_in("boss", OTHER)


def test_sign_out_all_ends_every_session_of_one_account(world: World) -> None:
    bob = world.create("bob")
    _, one = world.sign_in("bob")
    _, two = world.sign_in("bob")
    sessions.sign_out_all(world.factory, account_id=bob.account_id)
    for token in (one, two):
        with pytest.raises(InvalidCredentialsError):
            sessions.principal_for_bearer(world.factory, token)
