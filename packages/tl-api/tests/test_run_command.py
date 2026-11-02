"""``tl_api.commands.run_command``: the one door every command goes through (P2-WEB1-S2).

The JSON endpoints and the web action route both call it, so the reserved-field refusal, the
company-admin check, the effective time and the module-role access check have no second copy.
Ports of the checks (a), (b) and (c) of the S2 acceptance script.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from typing import Any

import pytest
from harness import Harness
from tl_api import commands
from tl_api.commands import COMMANDS, CommandSpec, command_spec, run_command
from tl_api.context import ApiContext
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.password import prepare_password
from tl_core.auth.types import Principal
from tl_core.services.commands import CommandResult
from tl_core.services.errors import ReservedIdentifierError

P1 = "project:P1"
PASSWORD = "correct horse battery"
OK = CommandResult(stream_id="stub", key=None, version=1, events=[])


def stub(name: str) -> CommandSpec:
    """The row named ``name`` with a handler that answers: only the checks in front show."""
    spec = command_spec(name)
    assert spec is not None, name
    return dataclasses.replace(spec, handler=lambda *a, **k: OK)


def command_of(spec: CommandSpec, *, actor: str, scope: str, **more: Any) -> Any:
    return spec.model.model_construct(actor=actor, source="test", scope=scope, **more)


@pytest.fixture
def people(harness: Harness) -> tuple[ApiContext, dict[str, Principal]]:
    """``uma`` and ``sue`` (users; sue holds the superuser role on P1) and ``ada`` (admin)."""
    ctx: ApiContext = harness.app.state.ctx
    principals: dict[str, Principal] = {}
    ids: dict[str, str] = {}
    roles: list[Any]
    for name, roles in (("uma", ["user"]), ("sue", ["user"]), ("ada", ["admin"])):
        with harness.backend() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=roles,
                password=prepare_password(PASSWORD, username=name), by="svc:test",
            )  # fmt: skip
        ids[name] = view.account_id
        principals[name] = Principal(
            actor=f"user:{name}", account_id=view.account_id, kind="person", roles=roles,
            via="session",
        )  # fmt: skip
    with harness.backend() as uow:
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:ada", source="test", scope="company", account_id=ids["sue"],
                project=P1, module="*", role="superuser", reason="test",
            ),
        )  # fmt: skip
    return ctx, principals


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    with pytest.raises(error) as caught:
        call()
    return caught.value


def test_the_endpoint_holds_none_of_the_three_checks_and_run_command_holds_each_once() -> None:
    endpoint_src = inspect.getsource(commands._make_endpoint)  # pyright: ignore[reportPrivateUsage]
    run_src = inspect.getsource(run_command)
    for word in ("require_command_access", "refuse_reserved", "resolve_effective_at"):
        assert word not in endpoint_src, f"_make_endpoint still has {word}"
        assert run_src.count(word) == 1, f"run_command has {word} {run_src.count(word)} times"
    assert "run_command(" in endpoint_src


@pytest.mark.parametrize(("who", "allowed"), [("uma", False), ("sue", True), ("ada", True)])
def test_a_controller_command_needs_the_module_role(
    people: tuple[ApiContext, dict[str, Principal]], who: str, allowed: bool
) -> None:
    ctx, principals = people
    controller = stub("IssueRevision")  # a documents `controller` command
    row = command_spec("IssueRevision")
    assert row is not None and row.module == "documents"
    cmd = command_of(controller, actor=f"user:{who}", scope=P1)

    def call() -> CommandResult:
        return run_command(
            ctx, controller, cmd, principal=principals[who], path="/commands/IssueRevision"
        )

    if allowed:
        assert call() is OK
    else:
        refuses(ForbiddenError, call)


@pytest.mark.parametrize(("who", "allowed"), [("uma", False), ("ada", True)])
def test_a_company_command_at_company_scope_is_for_an_admin(
    people: tuple[ApiContext, dict[str, Principal]], who: str, allowed: bool
) -> None:
    ctx, principals = people
    company = stub("AddCodeValue")
    assert company.access == "company"
    cmd = command_of(company, actor=f"user:{who}", scope="company")

    def call() -> CommandResult:
        return run_command(
            ctx, company, cmd, principal=principals[who], path="/commands/AddCodeValue"
        )

    if allowed:
        assert call() is OK
    else:
        refuses(ForbiddenError, call)


@pytest.mark.parametrize(("scope", "asked"), [("company", True), (P1, False)])
def test_the_admin_authorizer_is_asked_at_company_scope_with_the_path_only(
    people: tuple[ApiContext, dict[str, Principal]], scope: str, asked: bool
) -> None:
    ctx, principals = people
    company = stub("AddCodeValue")
    seen: list[tuple[str, str]] = []

    class Spy:
        def authorize(self, principal: Principal, action: str, resource: str) -> None:
            seen.append((action, resource))

    spied = dataclasses.replace(ctx, authorizer=Spy())  # type: ignore[arg-type]
    cmd = command_of(company, actor="user:ada", scope=scope)
    run_command(spied, company, cmd, principal=principals["ada"], path="/p", guard=False)
    assert seen == ([("admin.command.AddCodeValue", "/p")] if asked else [])


@pytest.mark.parametrize("guard", [True, False])
def test_the_guard_calls_run_by_default_and_not_when_the_endpoint_ran_them(
    people: tuple[ApiContext, dict[str, Principal]], guard: bool
) -> None:
    """Fail closed: the authorizer and the legacy hook are asked unless the caller says it did."""
    ctx, principals = people
    company = stub("AddCodeValue")
    seen: list[tuple[str, str, str]] = []

    class Spy:
        def authorize(self, principal: Principal, action: str, resource: str) -> None:
            seen.append(("authorizer", action, resource))

    def hook(actor: str, action: str, resource: str) -> None:
        seen.append(("hook", action, resource))

    spied = dataclasses.replace(ctx, authorizer=Spy(), authorize=hook)  # type: ignore[arg-type]
    cmd = command_of(company, actor="user:ada", scope=P1)
    if guard:  # the default
        run_command(spied, company, cmd, principal=principals["ada"], path="/p")
        assert seen == [("authorizer", "command.AddCodeValue", "/p"),
                        ("hook", "command.AddCodeValue", "/p")]  # fmt: skip
    else:
        run_command(spied, company, cmd, principal=principals["ada"], path="/p", guard=False)
        assert seen == []


@pytest.mark.parametrize(
    ("field_name", "value"), [("source", "svc:x"), ("correlation_id", "load:1")]
)
def test_a_command_with_a_reserved_field_is_refused(
    people: tuple[ApiContext, dict[str, Principal]], field_name: str, value: str
) -> None:
    ctx, principals = people
    company = stub("AddCodeValue")
    cmd = command_of(company, actor="user:ada", scope=P1).model_copy(update={field_name: value})
    refuses(
        ReservedIdentifierError,
        lambda: run_command(ctx, company, cmd, principal=principals["ada"]),
    )


def test_command_spec_finds_the_row_and_answers_none_for_an_unknown_name() -> None:
    row = command_spec("AnswerTechnical")
    assert row is not None and row in COMMANDS and row.name == "AnswerTechnical"
    assert command_spec("Nope") is None
