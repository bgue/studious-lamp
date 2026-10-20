"""``plan_command``: the checks every automation passes before a command is built (ADR-0017)."""

from __future__ import annotations

from typing import Any

import pytest
from tl_api.commands import command_runner
from tl_core.integration.automation import ServerFields, plan_command
from tl_core.integration.contract import AUTOMATION_COMMANDS, access_covers
from tl_core.services.commands import Command
from tl_core.services.links import AddLink, SuggestLink

FIELDS = ServerFields(
    actor="svc:rule-x",
    source="rule:x@1/d1",
    scope="project:P123",
    correlation_id="C" * 26,
    causation_id="E" * 26,
)
RUNNER = command_runner()


class Table:
    """A runner whose access table is ours."""

    def __init__(self, access: dict[str, Any]) -> None:
        self._access = access

    def model_of(self, name: str) -> type[Command] | None:
        return RUNNER.model_of(name)

    def access_of(self, name: str) -> Any:
        return self._access.get(name)

    def run(self, uow: Any, command: Command) -> Any:
        raise AssertionError("plan_command never runs a command")


def plan(name: str, args: dict[str, Any], **kw: Any):  # noqa: ANN201
    values: dict[str, Any] = {
        "declared": "user",
        "allowed": AUTOMATION_COMMANDS,
        "link_source": "rule",
        "runner": RUNNER,
    }
    values.update(kw)
    runner = values.pop("runner")
    return plan_command(runner, name, args, FIELDS, **values)


def test_a_good_command_gets_the_servers_fields_and_not_the_clients() -> None:
    built = plan("PostToFeed", {"body": "hello"})
    command = built.command
    assert command is not None and built.planned.permitted and built.planned.problem is None
    assert (command.actor, command.source, command.scope) == (
        "svc:rule-x",
        "rule:x@1/d1",
        FIELDS.scope,
    )
    assert (command.correlation_id, command.causation_id) == ("C" * 26, "E" * 26)
    assert "actor" not in built.planned.command and built.planned.command["body"] == "hello"


@pytest.mark.parametrize(
    "field",
    ["actor", "source", "scope", "correlation_id", "causation_id", "by_module", "idempotency_key"],
)
def test_arguments_that_name_a_server_field_are_refused_not_ignored(field: str) -> None:
    for args in ({"body": "x", field: "y"}, {"body": "x", "nest": {"deep": [{field: 1}]}}):
        built = plan("PostToFeed", args)
        assert built.command is None and built.planned.problem is not None
        assert built.planned.problem.code == "server_field"


@pytest.mark.parametrize(
    "name", ["VoidRecord", "ChangeSetting", "AdminRetractLink", "NoSuchCommand", ""]
)
def test_a_command_outside_the_automation_list_is_refused(name: str) -> None:
    built = plan(name, {})
    assert built.command is None and built.planned.problem is not None
    assert built.planned.problem.code == "command_not_allowed"


def test_a_command_outside_the_records_own_list_is_refused() -> None:
    built = plan("PostToFeed", {"body": "x"}, allowed={"CreateRecord"})
    assert built.planned.problem is not None and built.planned.problem.code == "command_not_allowed"


def test_the_declared_access_must_cover_the_command() -> None:
    needs_controller = Table({"PostToFeed": "controller"})
    refused = plan("PostToFeed", {"body": "x"}, runner=needs_controller, declared="user")
    assert refused.command is None and refused.planned.permitted is False
    assert refused.planned.problem is not None and refused.planned.problem.code == "access_denied"
    assert refused.planned.access == "controller"
    allowed = plan("PostToFeed", {"body": "x"}, runner=needs_controller, declared="controller")
    assert allowed.command is not None and allowed.planned.permitted


def test_a_command_nobody_declared_an_access_for_is_never_permitted() -> None:
    built = plan("PostToFeed", {"body": "x"}, runner=Table({}), declared="controller")
    assert built.command is None and built.planned.access is None
    assert built.planned.problem is not None and built.planned.problem.code == "access_denied"
    assert not access_covers("controller", None)


def test_a_command_the_server_does_not_have_is_refused() -> None:
    class Empty(Table):
        def model_of(self, name: str) -> None:
            return None

    built = plan("PostToFeed", {"body": "x"}, runner=Empty({"PostToFeed": "user"}))
    assert built.planned.problem is not None and built.planned.problem.code == "unknown_command"


def test_a_field_the_command_lacks_is_refused() -> None:
    built = plan("PostToFeed", {"body": "x", "bodyy": "typo"})
    assert built.planned.problem is not None and built.planned.problem.code == "unknown_field"


def test_the_commands_own_validation_runs_and_never_echoes_the_input() -> None:
    built = plan("PostToFeed", {"body": "   "})
    problem = built.planned.problem
    assert problem is not None and problem.code == "invalid_command"
    assert "body" in problem.message and "   " not in problem.message
    nul = plan("PostToFeed", {"body": "a\x00b"})
    assert nul.planned.problem is not None and "\x00" not in nul.planned.problem.message


def test_a_link_gets_the_engines_own_link_source_and_no_other() -> None:
    built = plan("AddLink", {"from_id": "a", "to_id": "b"})
    assert isinstance(built.command, AddLink) and built.command.link_source == "rule"
    suggested = plan("SuggestLink", {"from_id": "a", "to_id": "b"}, link_source="enricher")
    assert (
        isinstance(suggested.command, SuggestLink) and suggested.command.link_source == "enricher"
    )
    other = plan("AddLink", {"from_id": "a", "to_id": "b", "link_source": "manual"})
    assert other.planned.problem is not None and other.planned.problem.code == "link_source"
    same = plan("AddLink", {"from_id": "a", "to_id": "b", "link_source": "rule"})
    assert same.command is not None


def test_the_message_of_a_problem_is_bounded() -> None:
    long_name = "x" * 5000
    built = plan("PostToFeed", {"body": "x", long_name: 1})
    assert built.planned.problem is not None and len(built.planned.problem.message) <= 200
