"""The command runner enforces each command's access for the command's own actor.

A command run by a rule, an inbound mapping or a person's dispatch never runs with more than that
actor holds in the ledger (coordinator decision on FANOUT D14). One test per kind of caller.
"""

from __future__ import annotations

from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from tl_api.commands import CommandSpec, TableCommandRunner, command_runner
from tl_core.integration.actor_access import held_access
from tl_core.integration.apps import RegisterIntegrationApp, handle_register_app
from tl_core.integration.errors import ActionAccessError, CommandAccessError
from tl_core.integration.inbound.service import CreateInboundEndpoint, create_endpoint
from tl_core.services.commands import Command, CommandResult


class UserPing(Command):
    pass


class ControllerPing(Command):
    pass


class AdminPing(Command):
    pass


class CompanyPing(Command):
    pass


def make_runner(calls: list[str]) -> TableCommandRunner:
    def handler(_uow: Any, command: Command) -> CommandResult:
        calls.append(type(command).__name__)
        return CommandResult(stream_id="s", key=None, version=1, events=[])

    return TableCommandRunner(
        (
            CommandSpec(UserPing, handler, "user"),
            CommandSpec(ControllerPing, handler, "controller"),
            CommandSpec(AdminPing, handler, "admin"),
            CommandSpec(CompanyPing, handler, "company"),
        )
    )


def attempt(world: World, actor: str, command: type[Command], *, scope: str = SCOPE) -> list[str]:
    calls: list[str] = []
    runner = make_runner(calls)
    with world.factory() as uow:
        runner.run(uow, command(actor=actor, source="test", scope=scope))
    return calls


def allowed(world: World, actor: str) -> set[str]:
    """Which of the three levels ``actor`` can run (the others raise ``CommandAccessError``)."""
    found: set[str] = set()
    for command in (UserPing, ControllerPing, AdminPing):
        try:
            attempt(world, actor, command)
        except CommandAccessError:
            continue
        found.add(command.__name__)
    return found


USER, CONTROLLER, ADMIN_ALL = (
    {"UserPing"},
    {"UserPing", "ControllerPing"},
    {"UserPing", "ControllerPing", "AdminPing"},
)


# --- a person (a dispatch, an accepted proposal): the roles of the account ---------------------


def test_a_persons_dispatch_cannot_exceed_their_own_access(world: World) -> None:
    assert allowed(world, world.account("plain")) == USER
    assert allowed(world, world.account("controller", "document_controller")) == CONTROLLER
    assert allowed(world, world.account("boss", "admin")) == ADMIN_ALL


def test_a_person_without_an_account_or_with_a_disabled_one_holds_nothing(world: World) -> None:
    assert allowed(world, "user:nobody") == set()
    assert allowed(world, world.account("gone", "document_controller", disabled=True)) == set()


def test_an_agent_holds_user_access_at_most(world: World) -> None:
    assert allowed(world, world.account("bot", kind="agent")) == USER


def test_an_actor_cannot_borrow_the_name_of_the_other_kind(world: World) -> None:
    world.account("bot", kind="agent")
    world.account("pat", "admin")
    assert allowed(world, "user:bot") == set()
    assert allowed(world, "agent:pat") == set()


def test_other_actors_hold_nothing(world: World) -> None:
    for actor in ("svc:action-send", "svc:rule-unknown", "system:migration", "", "user:"):
        assert allowed(world, actor) == set(), actor


def test_a_refused_command_never_reaches_its_handler(world: World) -> None:
    calls: list[str] = []
    runner = make_runner(calls)
    actor = world.account("plain")
    with world.factory() as uow, pytest.raises(CommandAccessError):
        runner.run(uow, AdminPing(actor=actor, source="test", scope=SCOPE))
    assert calls == []


def test_a_company_command_needs_admin_in_the_company_scope_only(world: World) -> None:
    plain = world.account("plain")
    assert attempt(world, plain, CompanyPing) == ["CompanyPing"]
    with pytest.raises(CommandAccessError):
        attempt(world, plain, CompanyPing, scope="company")
    assert attempt(world, world.account("boss", "admin"), CompanyPing, scope="company")


# --- a rule's service actor: the access declared on the rule -----------------------------------


@pytest.mark.parametrize(("declared", "expected"), [("user", USER), ("controller", CONTROLLER)])
def test_a_rules_actor_holds_what_the_rule_declares(
    world: World, declared: str, expected: set[str]
) -> None:
    world.create_rule(key=f"r-{declared}", access=declared)
    assert allowed(world, f"svc:rule-r-{declared}") == expected


# --- an inbound endpoint's service actor -------------------------------------------------------


@pytest.mark.parametrize(("declared", "expected"), [("user", USER), ("controller", CONTROLLER)])
def test_an_inbound_endpoints_actor_holds_what_the_endpoint_declares(
    world: World, declared: str, expected: set[str]
) -> None:
    with world.factory() as uow:
        handle_register_app(
            uow,
            RegisterIntegrationApp(
                actor=ADMIN, source="test", scope=SCOPE, name="erp", label="ERP"
            ),
        )
    with world.factory() as uow:
        made = create_endpoint(
            uow,
            CreateInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, app="erp", name=declared,
                mapping='{"command": "PostToFeed", "args": {}}',
                allowed_commands=["PostToFeed"], access=declared,  # type: ignore[arg-type]
            ),
        )  # fmt: skip
    assert made.endpoint_id
    assert allowed(world, f"svc:inbound-erp-{declared}") == expected


def test_a_service_actor_holds_nothing_the_ledger_does_not_know(world: World) -> None:
    with world.factory(readonly=True) as uow:
        assert held_access(uow.conn(), "svc:rule-ghost") is None
        assert held_access(uow.conn(), "svc:inbound-ghost-x") is None
        assert held_access(uow.conn(), "svc:enricher-ghost") is None


# --- the real table: InvokeAction gets holds from the actor, not from the caller ----------------


def test_invoke_action_through_the_runner_uses_the_actors_own_access(world: World) -> None:
    world.define_action(access="controller")
    record = world.record("47-1234-W012")
    from tl_core.integration.contract import InvokeAction

    def invoke(actor: str) -> Any:
        with world.factory() as uow:
            return command_runner().run(
                uow,
                InvokeAction(
                    actor=actor, source="test", scope=SCOPE, action="send_to_nde", targets=[record]
                ),
            )

    with pytest.raises(ActionAccessError):
        invoke(world.account("plain"))
    assert invoke(world.account("controller", "document_controller")).events


def test_a_rules_actor_cannot_invoke_an_action_above_its_declared_access(world: World) -> None:
    from tl_core.integration.contract import InvokeAction

    world.define_action(access="controller")
    record = world.record("47-1234-W012")
    world.create_rule(key="invoker", access="user")
    world.create_rule(key="invoker-c", access="controller")

    def invoke(actor: str) -> Any:
        with world.factory() as uow:
            return command_runner().run(
                uow,
                InvokeAction(
                    actor=actor, source="rule:invoker", scope=SCOPE, action="send_to_nde",
                    targets=[record],
                ),
            )  # fmt: skip

    with pytest.raises(ActionAccessError):
        invoke("svc:rule-invoker")
    assert invoke("svc:rule-invoker-c").events


# --- an enricher's service actor ---------------------------------------------------------------


@pytest.mark.parametrize(("declared", "expected"), [("user", USER), ("controller", CONTROLLER)])
def test_an_enrichers_actor_holds_what_the_registration_declares(
    world: World, declared: str, expected: set[str]
) -> None:
    import fakes
    from tl_core.integration.enrichers.registry import use_enrichers

    with use_enrichers({"fake": fakes.FakeEnricher}):
        world.register_enricher(access=declared)
    assert allowed(world, "svc:enricher-fake") == expected
