"""Module roles at the API (roles-mvp.md sections 5 and 9, RM-S2): every module command x viewer,
user, superuser, admin, agent x two projects equals the role table.

The matrix goes through the real command endpoints (real authorizer, real ``_make_endpoint``, real
``require_command_access``) with two things made loose so that only the access decision shows: the
request body accepts any fields and the handler is a stub that answers 200. A 200 is "the gate let
it through", a 403 is "refused". Each expected cell is computed from
``schema/settings/module-roles.yaml`` here, never from the code under test. Runs on every adapter.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import APIRouter
from fastapi.testclient import TestClient
from harness import Harness
from pydantic import ConfigDict, create_model
from tl_api import commands
from tl_api.app import create_app
from tl_api.commands import COMMANDS, CommandSpec, controller_actions
from tl_api.tokens import TokenStore, add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import (
    GrantModuleRole,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)
from tl_core.auth.module_roles import command_index
from tl_core.auth.password import prepare_password
from tl_core.auth.provider import RoleAuthorizer
from tl_core.auth.types import Principal
from tl_core.services.commands import Command, CommandResult

P1, P2 = "project:P1", "project:P2"
PROJECTS = (P1, P2)
PASSWORD = "correct horse battery"
TABLE_FILE = Path(__file__).resolve().parents[3] / "schema" / "settings" / "module-roles.yaml"
ROLE_WORDS: dict[str, set[str]] = {
    r: set(w) for r, w in yaml.safe_load(TABLE_FILE.read_text(encoding="utf-8"))["roles"].items()
}
OK = CommandResult(stream_id="stub", key=None, version=1, events=[])
PEOPLE = {
    "viewer": "viv",
    "user": "uma",
    "superuser": "sue",
    "admin": "ada",
    "agent": "agent:triage",
}


def expected_allowed(role: str, word: str) -> bool:
    """May ``role`` run a command needing ``word`` on a project scope?"""
    if role == "agent":
        return False  # an agent proposes; it never runs a module command over REST
    if role == "admin":
        return True
    if word == "company":
        word = "user"  # `company` is the plain user word on a project
    if word == "admin":
        return False
    return word in ROLE_WORDS[role]


def loosen(spec: CommandSpec) -> CommandSpec:
    def construct(cls: Any, **data: Any) -> Any:
        if not data:
            return object.__new__(cls)
        return cls.model_construct(**data)

    model = type(
        spec.model.__name__,
        (spec.model,),
        {"__new__": construct, "__init__": lambda self, **data: None},
    )
    return dataclasses.replace(spec, model=model, handler=lambda *a, **k: OK)


class Cast:
    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.clients: dict[str, TestClient] = {}
        self.ids: dict[str, str] = {}

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with self.harness.backend() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=list(roles),
                password=prepare_password(PASSWORD, username=name), by="svc:test",
            )  # fmt: skip
        self.ids[name] = view.account_id
        _, token = sessions.sign_in(self.harness.backend, username=name, password=PASSWORD)
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        self.clients[name] = client

    def agent(self, name: str) -> None:
        token = add_token(self.harness.settings.tokens_path, f"agent:{name}")
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        self.clients[f"agent:{name}"] = client

    def grant(self, who: str, project: str, module: str, role: str) -> None:
        with self.harness.backend() as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada", source="test", scope="company", account_id=self.ids[who],
                    project=project, module=module, role=role, reason="test",
                ),
            )  # fmt: skip

    def post(self, who: str, name: str, scope: str) -> int:
        return self.clients[who].post(f"/commands/{name}", json={"scope": scope}).status_code


@pytest.fixture
def loose(
    parity_harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Cast]:
    """The harness's app is built over the loose router (the real endpoints, stub handlers)."""
    body = create_model(
        "LooseBody", __config__=ConfigDict(extra="allow"), scope=(str, ...), source=(str, "api")
    )
    router = APIRouter()
    for spec in COMMANDS:
        router.add_api_route(
            f"/commands/{spec.name}",
            commands._make_endpoint(loosen(spec), body),  # pyright: ignore[reportPrivateUsage]
            methods=["POST"],
            response_model=CommandResult,
            operation_id=f"loose_{spec.name}",
        )
    monkeypatch.setattr(commands, "router", router)
    harness = parity_harness
    harness.app = create_app(
        harness.backend,
        settings=harness.settings,
        tokens=TokenStore(harness.settings.tokens_path),
        files_service=harness.service,
        object_store=harness.store,
    )
    cast = Cast(harness)
    cast.person("ada", ("admin",))
    cast.person("viv", ("user",))  # explicit viewer everywhere
    cast.person("uma", ("user",))  # no grant: derived user
    cast.person("sue", ("user",))  # explicit superuser everywhere
    cast.person("pia", ("user",))  # superuser on P1, viewer on P2
    cast.person("dora", ("user", "document_controller"))  # derived superuser of three modules
    cast.person("solo", ("document_controller",))
    cast.agent("triage")
    for project in PROJECTS:
        cast.grant("viv", project, "*", "viewer")
        cast.grant("sue", project, "*", "superuser")
    cast.grant("pia", P1, "*", "superuser")
    cast.grant("pia", P2, "*", "viewer")
    yield cast


def test_every_module_command_is_decided_by_the_table_for_every_role_and_project(
    loose: Cast,
) -> None:
    index = dict(command_index())
    assert {s.name for s in COMMANDS if s.module is not None} == set(index)
    assert len(index) > 100
    mismatches: list[str] = []
    for name, (_, word) in sorted(index.items()):
        for role, who in PEOPLE.items():
            for project in PROJECTS:
                status = loose.post(who, name, project)
                if status not in (200, 403):
                    mismatches.append(f"{name} {role} {project}: status {status}")
                elif (status != 403) != expected_allowed(role, word):
                    mismatches.append(f"{name} {role} {project}: {status} (word {word})")
    assert not mismatches, mismatches[:10]


def test_the_matrix_has_both_a_let_through_and_a_refused_cell_for_each_word() -> None:
    words = {w for _, w in command_index().values()}
    assert {"user", "controller"} <= words
    assert expected_allowed("user", "user") and not expected_allowed("user", "controller")
    assert expected_allowed("superuser", "controller") and not expected_allowed("viewer", "user")
    assert expected_allowed("admin", "admin") and not expected_allowed("superuser", "admin")
    assert not expected_allowed("agent", "read")


def test_a_plain_user_with_no_grant_on_project_b_is_refused_there(loose: Cast) -> None:
    assert loose.post("uma", "IssueRevision", P2) == 403  # derived user: no controller word
    assert loose.post("uma", "RegisterDocument", P2) == 200
    loose.grant("uma", P1, "documents", "superuser")
    assert loose.post("uma", "IssueRevision", P1) == 200
    assert loose.post("uma", "IssueRevision", P2) == 403  # the grant is for project A only


def test_a_superuser_on_one_project_and_a_viewer_on_the_other(loose: Cast) -> None:
    assert loose.post("pia", "IssueRevision", P1) == 200
    assert loose.post("pia", "IssueRevision", P2) == 403
    assert loose.post("pia", "RegisterDocument", P2) == 403  # a viewer holds no `user` word


def test_a_document_controller_derives_superuser_of_three_modules_and_user_elsewhere(
    loose: Cast,
) -> None:
    for project in PROJECTS:
        for name in ("IssueRevision", "IssueCorrespondence", "PublishScheduleSnapshot"):
            assert loose.post("dora", name, project) == 200, (name, project)
        assert loose.post("dora", "ImportCostSnapshot", project) == 403
    assert loose.post("solo", "IssueRevision", P1) == 200
    assert loose.post("solo", "CreateTag", P2) == 200  # `user` in every module
    assert loose.post("solo", "ImportCostSnapshot", P1) == 403


def test_an_explicit_viewer_grant_replaces_the_derived_superuser_for_that_module_only(
    loose: Cast,
) -> None:
    loose.grant("dora", P2, "documents", "viewer")
    assert loose.post("dora", "IssueRevision", P2) == 403
    assert loose.post("dora", "IssueRevision", P1) == 200
    assert loose.post("dora", "IssueCorrespondence", P2) == 200


def test_a_company_word_is_the_admins_at_company_scope_and_a_users_on_a_project(
    loose: Cast,
) -> None:
    assert loose.post("uma", "AddCodeValue", "company") == 403
    assert loose.post("ada", "AddCodeValue", "company") == 200
    assert loose.post("uma", "AddCodeValue", P1) == 200


def test_a_core_command_is_not_decided_by_module_roles(loose: Cast) -> None:
    assert loose.post("viv", "CreateRecord", P1) == 200
    assert loose.post("sue", "AdminFlagLink", P1) == 403


def test_a_revoke_closes_the_commands_at_once_on_that_project_only(loose: Cast) -> None:
    assert loose.post("sue", "IssueRevision", P1) == 200
    assert loose.post("sue", "IssueRevision", P2) == 200
    with loose.harness.backend() as uow:
        revoke_module_role(
            uow,
            RevokeModuleRole(
                actor="user:ada", source="test", scope="company", account_id=loose.ids["sue"],
                project=P1, module="*", role="superuser", reason="test",
            ),
        )  # fmt: skip
    assert loose.post("sue", "IssueRevision", P1) == 403  # back to the derived user role
    assert loose.post("sue", "RegisterDocument", P1) == 200
    assert loose.post("sue", "IssueRevision", P2) == 200


# --- the authorizer (D1) ---------------------------------------------------------------------


def principal(
    actor: str, roles: list[Any], kind: str = "person", via: str = "session"
) -> Principal:
    return Principal(actor=actor, account_id="a", kind=kind, roles=roles, via=via)  # type: ignore[arg-type]


def test_the_authorizer_refuses_a_plain_user_and_an_agent_every_controlling_action() -> None:
    auth = RoleAuthorizer(controller_actions=controller_actions())
    plain = principal("user:x", ["user"])
    agent = principal("agent:x", ["user"], kind="agent", via="agent_token")
    admin = principal("user:y", ["admin"])
    actions = sorted(controller_actions())
    assert len(actions) > 30
    for action in actions:
        with pytest.raises(ForbiddenError):
            auth.authorize(plain, action, "r")
        with pytest.raises(ForbiddenError):
            auth.authorize(agent, action, "r")
        auth.authorize(admin, action, "r")


def test_the_authorizer_passes_the_derived_controller_of_that_module_only() -> None:
    auth = RoleAuthorizer(controller_actions=controller_actions())
    dcon = principal("user:d", ["document_controller"])
    auth.authorize(dcon, "control.command.IssueRevision", "r")
    auth.authorize(dcon, "control.command.IssueCorrespondence", "r")
    with pytest.raises(ForbiddenError):
        auth.authorize(dcon, "control.command.ImportCostSnapshot", "r")
    with pytest.raises(ForbiddenError):  # an unlisted control action stays admin-only
        auth.authorize(dcon, "control.command.NoSuchThing", "r")
    auth.authorize(principal("user:y", ["admin"]), "control.command.NoSuchThing", "r")


def test_an_explicit_grant_counts_at_the_authorizer_for_that_module_only() -> None:
    plain = principal("user:x", ["user"])
    auth = RoleAuthorizer(
        controller_actions=controller_actions(), granted=lambda p, m: m == "documents"
    )
    auth.authorize(plain, "control.command.IssueRevision", "r")
    with pytest.raises(ForbiddenError):
        auth.authorize(plain, "control.command.ImportCostSnapshot", "r")


def test_a_controller_command_with_no_module_cannot_be_built() -> None:
    class Stray(Command): ...

    with pytest.raises(Exception, match="module"):
        CommandSpec(Stray, lambda *a, **k: OK, access="controller")
