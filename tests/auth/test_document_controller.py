"""The document controller role (ADR-0013): roles, the authorizer and the account events."""

from __future__ import annotations

import pytest
from authworld import World
from tl_adapters.db import rebuild_projections
from tl_core.auth import accounts, queries
from tl_core.auth.errors import ForbiddenError, InvalidAccountError, LastAdminError
from tl_core.auth.provider import AGENT_ACTIONS, RoleAuthorizer
from tl_core.auth.types import ROLES, AccountKind, Principal, Role

CONTROL = "control.command.IssueRevision"
OTHER_CONTROL = "control.command.IssueTransmittal"
LISTED = frozenset({CONTROL, OTHER_CONTROL})


def principal(kind: AccountKind = "person", roles: tuple[Role, ...] = ("user",)) -> Principal:
    return Principal(
        actor=f"{'agent' if kind == 'agent' else 'user'}:x",
        account_id="a1",
        kind=kind,
        roles=list(roles),
        via="session",
    )


def test_there_are_three_roles_in_the_stored_order() -> None:
    assert ROLES == ("admin", "document_controller", "user")


def test_the_controller_property_is_admin_or_document_controller_and_never_an_agent() -> None:
    assert principal(roles=("admin",)).is_controller
    assert principal(roles=("user", "document_controller")).is_controller
    assert principal(roles=("document_controller",)).is_controller
    assert not principal(roles=("user",)).is_controller
    assert not principal("agent", ("user",)).is_controller
    # an agent cannot hold either role; the property does not rely on that
    assert not principal("agent", ("document_controller",)).is_controller
    assert not principal("agent", ("admin",)).is_controller
    assert not principal(roles=("document_controller",)).is_admin


def test_a_document_controller_runs_the_listed_control_actions_and_an_admin_all() -> None:
    authorizer = RoleAuthorizer(controller_actions=LISTED)
    both: tuple[Role, ...] = ("user", "document_controller")
    alone: tuple[Role, ...] = ("document_controller",)
    for roles in (both, alone):
        for action in LISTED:
            authorizer.authorize(principal(roles=roles), action, "/x")
        authorizer.authorize(principal(roles=roles), "command.RegisterDocument", "/x")
    authorizer.authorize(principal(roles=("admin",)), CONTROL, "/x")
    # an admin passes an action nobody listed: control.* never widens past the admin
    authorizer.authorize(principal(roles=("admin",)), "control.command.Unlisted", "/x")


def test_a_user_is_refused_every_control_action() -> None:
    authorizer = RoleAuthorizer(controller_actions=LISTED)
    for action in (*LISTED, "control.command.Unlisted", "control."):
        with pytest.raises(ForbiddenError) as raised:
            authorizer.authorize(principal(), action, "/x")
        assert action in str(raised.value)


def test_a_control_action_nobody_listed_is_an_admins_so_a_typo_fails_closed() -> None:
    authorizer = RoleAuthorizer(controller_actions=LISTED)
    for action in ("control.command.IssueRevison", "control.command.issuerevision", "control.x"):
        with pytest.raises(ForbiddenError):
            authorizer.authorize(principal(roles=("user", "document_controller")), action, "/x")
        authorizer.authorize(principal(roles=("admin",)), action, "/x")


def test_the_default_authorizer_lists_nothing_for_a_document_controller() -> None:
    with pytest.raises(ForbiddenError):
        RoleAuthorizer().authorize(principal(roles=("document_controller",)), CONTROL, "/x")


def test_the_prefix_needs_its_dot_and_a_command_action_is_not_a_control_action() -> None:
    authorizer = RoleAuthorizer(controller_actions=LISTED)
    authorizer.authorize(principal(), "controlled", "/x")  # not "control."
    authorizer.authorize(principal(), "command.IssueRevision", "/x")  # a user action by name only
    # listing a name does not turn a non-control action into a control one
    wide = RoleAuthorizer(controller_actions=frozenset({"admin.accounts.list"}))
    with pytest.raises(ForbiddenError):
        wide.authorize(principal(roles=("document_controller",)), "admin.accounts.list", "/x")


def test_a_document_controller_has_no_admin_action() -> None:
    authorizer = RoleAuthorizer(controller_actions=LISTED)
    for action in ("admin.accounts.list", "admin.accounts.roles", "admin.tokens.issue",
                   "admin.command.AdminFlagLink"):  # fmt: skip
        with pytest.raises(ForbiddenError):
            authorizer.authorize(principal(roles=("user", "document_controller")), action, "/x")


def test_an_agent_is_refused_control_actions_even_when_they_are_listed() -> None:
    authorizer = RoleAuthorizer(agent_actions=AGENT_ACTIONS | LISTED, controller_actions=LISTED)
    every: tuple[tuple[Role, ...], ...] = (("user",), ("document_controller",), ("admin",))
    for roles in every:
        with pytest.raises(ForbiddenError):
            authorizer.authorize(principal("agent", roles), CONTROL, "/x")


def test_the_role_is_granted_and_taken_back_by_events_and_survives_a_rebuild(world: World) -> None:
    world.admin()
    bob = world.create("bob")
    assert bob.roles == ["user"]
    with world.factory() as uow:
        granted = accounts.set_roles(
            uow,
            account_id=bob.account_id,
            roles=["document_controller", "user"],
            by="user:root",
            reason="takes over document control",
        )
    assert granted.roles == ["document_controller", "user"]
    principal_, _ = world.sign_in("bob")
    assert principal_.roles == ["document_controller", "user"]
    assert principal_.is_controller and not principal_.is_admin
    with world.factory() as uow:
        taken = accounts.set_roles(
            uow, account_id=bob.account_id, roles=["user"], by="user:root", reason="moved on"
        )
    assert taken.roles == ["user"]
    assert not world.sign_in("bob")[0].is_controller
    sets = [e for e in world.events() if e[0] == "Account.RolesSet"]
    assert [e[2] for e in sets] == ["user:root", "user:root"]
    assert "document_controller" in sets[0][3] and "takes over document control" in sets[0][3]
    with world.factory() as uow:
        accounts.set_roles(
            uow,
            account_id=bob.account_id,
            roles=["document_controller", "user"],
            by="user:root",
            reason=None,
        )
    rebuild_projections(world.db)
    with world.factory(readonly=True) as uow:
        assert queries.get_account(uow.conn(), bob.account_id).roles == [
            "document_controller",
            "user",
        ]


def test_the_roles_are_stored_in_one_order_whatever_order_they_come(world: World) -> None:
    both = world.create("dora", roles=("document_controller", "user"))
    assert both.roles == ["document_controller", "user"]
    everything = world.create("zed", roles=("document_controller", "user", "admin"))
    assert everything.roles == ["admin", "document_controller", "user"]


def test_a_controller_alone_is_a_valid_account(world: World) -> None:
    only = world.create("dora", roles=("document_controller",))
    assert only.roles == ["document_controller"]
    assert world.sign_in("dora")[0].is_controller


def test_an_agent_account_can_never_hold_the_role(world: World) -> None:
    for roles in (("document_controller",), ("user", "document_controller")):
        with pytest.raises(InvalidAccountError, match="document_controller"):
            world.create("bot", kind="agent", roles=roles)
    bot = world.create("bot", kind="agent")
    with world.factory() as uow, pytest.raises(InvalidAccountError, match="document_controller"):
        accounts.set_roles(
            uow, account_id=bot.account_id, roles=["document_controller", "user"], by="user:root",
            reason=None,
        )  # fmt: skip
    with world.factory(readonly=True) as uow:
        assert queries.get_account(uow.conn(), bot.account_id).roles == ["user"]


def test_a_sim_account_may_hold_the_role_but_not_admin(world: World) -> None:
    sim = world.create("sim-doc-controller", kind="sim", roles=("user", "document_controller"))
    assert sim.roles == ["document_controller", "user"] and sim.kind == "sim"
    with pytest.raises(InvalidAccountError):
        world.create("sim-boss", kind="sim", roles=("admin",))


def test_an_unknown_role_is_refused_and_the_message_lists_the_three(world: World) -> None:
    with pytest.raises(InvalidAccountError, match="admin, document_controller, user"):
        world.create("alice", roles=("controller",))
    with pytest.raises(InvalidAccountError):
        world.create("alice", roles=("Document_Controller",))
    assert world.events() == []


def test_the_role_does_not_count_for_the_last_admin_rule(world: World) -> None:
    only = world.admin()
    world.create("dora", roles=("document_controller",))
    with world.factory() as uow, pytest.raises(LastAdminError):
        accounts.set_roles(
            uow, account_id=only.account_id, roles=["document_controller", "user"],
            by="user:root", reason=None,
        )  # fmt: skip
    # a controller can be disabled freely: it is not an admin
    controller = world.create("erin", roles=("user", "document_controller"))
    with world.factory() as uow:
        accounts.disable(uow, account_id=controller.account_id, by="user:root", reason=None)
    with world.factory(readonly=True) as uow:
        assert queries.count_active_admins(uow.conn()) == 1
