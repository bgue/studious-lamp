"""The command runner enforces each command's access for the command's own actor.

A command run by a rule, an inbound mapping or a person's dispatch never runs with more than that
actor holds in the ledger (coordinator decision on FANOUT D14). One test per kind of caller.
"""

from __future__ import annotations

from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from sqlalchemy import text
from tl_api.commands import CommandSpec, TableCommandRunner, command_runner
from tl_core.integration.actor_access import held_access
from tl_core.integration.errors import ActionAccessError, CommandAccessError
from tl_core.services.commands import Command, CommandResult
from tl_core.util import new_ulid


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
    actor = world.account("bot", kind="agent")
    with world.factory(readonly=True) as uow:
        assert held_access(uow.conn(), actor) == "user"
    assert allowed(world, actor) == set()  # and the runner lets it run none of these (a proposal)


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
    world.switch_rule(world.create_rule(key=f"r-{declared}", access=declared), on=True)
    assert allowed(world, f"svc:rule-r-{declared}") == expected


# --- an inbound endpoint's service actor -------------------------------------------------------


@pytest.mark.parametrize(("declared", "expected"), [("user", USER), ("controller", CONTROLLER)])
def test_an_inbound_endpoints_actor_holds_what_the_endpoint_declares(
    world: World, declared: str, expected: set[str]
) -> None:
    world.endpoint(declared, access=declared)
    assert allowed(world, f"svc:inbound-erp.{declared}") == expected


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
    world.switch_rule(world.create_rule(key="invoker", access="user"), on=True)
    world.switch_rule(world.create_rule(key="invoker-c", access="controller"), on=True)

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
    import intfakes as fakes
    from tl_core.integration.enrichers.registry import use_enrichers

    with use_enrichers({"fake": fakes.FakeEnricher}):
        world.switch_enricher(world.register_enricher(access=declared), on=True)
    assert allowed(world, "svc:enricher-fake") == expected


# --- the security review's findings (coordinator, 2026-10-18) --------------------------------


def test_two_endpoints_never_share_an_actor(world: World) -> None:
    """App ``a`` + endpoint ``b-c`` and app ``a-b`` + endpoint ``c`` were both
    ``svc:inbound-a-b-c``; the weaker one borrowed the stronger one's access."""
    from tl_core.integration.inbound.service import actor_for

    assert actor_for("a", "b-c") != actor_for("a-b", "c")
    low = world.endpoint("b-c", app="a", access="user")
    high = world.endpoint("c", app="a-b", access="controller")
    assert low.endpoint_id != high.endpoint_id
    assert allowed(world, actor_for("a", "b-c")) == USER
    assert allowed(world, actor_for("a-b", "c")) == CONTROLLER
    assert allowed(world, "svc:inbound-a-b-c") == set()  # the old, ambiguous name is nobody's


@pytest.mark.parametrize("table", ["cur_rule", "cur_inbound_endpoint", "cur_enricher"])
def test_a_service_actor_is_unique_in_its_table(world: World, table: str) -> None:
    import intfakes as fakes
    from sqlalchemy.exc import IntegrityError
    from tl_core.integration.enrichers.registry import use_enrichers

    with use_enrichers({"fake": fakes.FakeEnricher}):
        world.create_rule(key="r1")
        world.endpoint("o1")
        world.register_enricher()
    with world.factory() as uow:
        conn = uow.conn()
        row = dict(conn.execute(text(f"SELECT * FROM {table}")).mappings().first() or {})  # noqa: S608
        key = {
            "cur_rule": "rule_id",
            "cur_inbound_endpoint": "endpoint_id",
            "cur_enricher": "enricher_id",
        }[table]
        name = {"cur_rule": "key", "cur_inbound_endpoint": "name", "cur_enricher": "name"}[table]
        row[key] = new_ulid()
        row[name] = "clone"
        names, marks = ", ".join(row), ", ".join(":" + c for c in row)
        with pytest.raises(IntegrityError), conn.begin_nested():  # a savepoint: Postgres aborts
            conn.execute(  # the whole transaction on a violation
                text(f"INSERT INTO {table} ({names}) VALUES ({marks})"),  # noqa: S608
                row,
            )


def test_a_disabled_owner_holds_nothing(world: World) -> None:
    import intfakes as fakes
    from tl_core.integration.enrichers.registry import use_enrichers

    rule = world.create_rule(key="r1", access="controller")
    made = world.endpoint("o1", access="controller")
    with use_enrichers({"fake": fakes.FakeEnricher}):
        enricher = world.register_enricher(access="controller")
        world.switch_enricher(enricher, on=True)
    world.switch_rule(rule, on=True)
    actors = ("svc:rule-r1", "svc:inbound-erp.o1", "svc:enricher-fake")
    assert [allowed(world, a) for a in actors] == [CONTROLLER] * 3
    world.switch_rule(rule, on=False)
    world.switch_endpoint(made.endpoint_id, False)
    world.switch_enricher(enricher, on=False)
    assert [allowed(world, a) for a in actors] == [set()] * 3


def test_a_switched_off_app_takes_its_owners_with_it(world: World) -> None:
    from tl_core.integration.apps import SetIntegrationAppEnabled, handle_set_app_enabled

    world.endpoint("o1", access="controller")
    rule = world.create_rule(key="r1", access="controller", integration_app="erp")
    world.switch_rule(rule, on=True)
    assert allowed(world, "svc:inbound-erp.o1") == CONTROLLER
    assert allowed(world, "svc:rule-r1") == CONTROLLER
    app_id = world.rows("SELECT app_id FROM cur_integration_app")[0]["app_id"]
    with world.factory() as uow:
        handle_set_app_enabled(
            uow,
            SetIntegrationAppEnabled(
                actor=ADMIN, source="test", scope=SCOPE, app_id=app_id, enabled=False
            ),
        )
    assert allowed(world, "svc:inbound-erp.o1") == set() and allowed(world, "svc:rule-r1") == set()


def test_a_look_alike_name_resolves_to_nobody(world: World) -> None:
    world.account("bob", "admin")
    assert allowed(world, "user:bob") == ADMIN_ALL
    for alias in ("user:BOB", "user:Bob", "user:ｂｏｂ", "user: bob", "user:bob "):
        assert allowed(world, alias) == set(), alias


def test_an_account_with_no_role_holds_nothing(world: World) -> None:
    actor = world.account("norole")
    assert allowed(world, actor) == USER
    with world.factory() as uow:
        uow.conn().execute(
            text("UPDATE cur_account SET roles_json = '[]' WHERE username = 'norole'")
        )
    assert allowed(world, actor) == set()


def test_an_agent_goes_through_a_proposal_not_the_runner(world: World) -> None:
    from tl_api.commands import command_runner
    from tl_core.services.commands import CreateRecord
    from tl_core.services.feed import PostToFeed

    agent = world.account("triage", kind="agent")
    runner = command_runner()
    with world.factory() as uow, pytest.raises(CommandAccessError):
        runner.run(
            uow,
            CreateRecord(
                actor=agent, source="x", scope=SCOPE, record_type="core.Record", title="T"
            ),
        )
    with world.factory() as uow:  # a post is a message: the one thing an agent does directly
        assert runner.run(
            uow, PostToFeed(actor=agent, source="x", scope=SCOPE, body="found a leak")
        )
