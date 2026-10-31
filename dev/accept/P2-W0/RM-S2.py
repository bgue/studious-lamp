"""Acceptance script for P2-W0 RM-S2: one access function at every API-side entry point.

Runs on SQLite with a temp ledger. Prints one ``PASS <check>`` line per check and the full
matrix (every module command x viewer, user, superuser, admin, agent x P1, P2); exits 0 when
every check passes, 1 on the first failure.

The matrix goes through the real command endpoints (real authorizer, real ``_make_endpoint``,
real ``require_command_access``) with two things made loose so only the access decision shows:
the request body model accepts any fields, and the handler is a stub that answers 200. A 200 is
"the access gate let it through", a 403 is "refused". The expected cell is computed from
``schema/settings/module-roles.yaml`` here, never from the code under test.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

os.environ.setdefault("TL_ENV", "test")  # dev tokens, for the agent principal

import yaml  # noqa: E402
from fastapi import APIRouter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ConfigDict, create_model  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api import commands  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.commands import (  # noqa: E402
    COMMANDS,
    CommandSpec,
    TableCommandRunner,
    action_for,
    check_command_words,
    controller_actions,
    effective_access,
)
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore, add_token  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.access_words import AccessWordError  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role  # noqa: E402
from tl_core.auth.module_roles import (  # noqa: E402
    command_index,
    holder_for_actor,
    require_command_access,
)
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.auth.provider import RoleAuthorizer  # noqa: E402
from tl_core.auth.types import Principal  # noqa: E402
from tl_core.confidentiality import system_view  # noqa: E402
from tl_core.integration.errors import CommandAccessError  # noqa: E402
from tl_core.modules import (  # noqa: E402
    ModuleSpec,
    load_modules,
    require_generic,
    use_modules,
)
from tl_core.services import proposals  # noqa: E402
from tl_core.services.commands import Command, CommandResult, CreateRecord  # noqa: E402
from tl_core.services.records import create_module_record, handle_create_record  # noqa: E402
from tl_mod_correspondence.handlers.triage import ConfirmTriage  # noqa: E402
from tl_mod_documents.derivation.publish import PublishDerivedDocuments  # noqa: E402
from tl_mod_documents.handlers.documents import (  # noqa: E402
    RegisterDocument,
    handle_register_document,
)
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot  # noqa: E402

P1, P2 = "project:P1", "project:P2"
PROJECTS = (P1, P2)
PASSWORD = "correct horse battery"
TABLE_FILE = Path(__file__).resolve().parents[3] / "schema" / "settings" / "module-roles.yaml"
TABLE = yaml.safe_load(TABLE_FILE.read_text(encoding="utf-8"))
ROLE_WORDS: dict[str, set[str]] = {r: set(w) for r, w in TABLE["roles"].items()}
OK = CommandResult(stream_id="stub", key=None, version=1, events=[])


def passed(check: str) -> None:
    print(f"PASS {check}")


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    try:
        call()
    except error as exc:
        return exc
    raise AssertionError(f"expected {error.__name__}")


def expected_allowed(role: str, word: str) -> bool:
    """The matrix cell, from the role table: may ``role`` run a command that needs ``word``, on a
    project scope? (``company`` is the plain user word there; ``admin`` is an admin's alone.)"""
    if role == "agent":
        return False  # an agent proposes; it never runs a module command over REST
    if role == "admin":
        return True  # every role and word, plus admin
    if word == "company":
        word = "user"
    if word == "admin":
        return False
    return word in ROLE_WORDS[role]


# --- the loose router: real endpoints, loose body and a stub handler ----------------------------


def loosen(spec: CommandSpec) -> CommandSpec:
    def construct(cls: Any, **data: Any) -> Any:
        if not data:  # model_construct itself asks for a bare instance
            return object.__new__(cls)
        return cls.model_construct(**data)

    model = type(
        spec.model.__name__,
        (spec.model,),
        {"__new__": construct, "__init__": lambda self, **data: None},
    )
    return dataclasses.replace(spec, model=model, handler=lambda *a, **k: OK)


def install_loose_router() -> None:
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
    commands.router = router


# --- the world -----------------------------------------------------------------------------------


class World:
    def __init__(self, work: Path) -> None:
        self.db = work / "ledger.db"
        create_schema(self.db)
        self.backend = open_backend(self.db)
        self.tokens_path = work / "tokens.json"
        settings = ApiSettings(db_path=self.db, tokens_path=self.tokens_path)
        install_loose_router()
        self.app = create_app(self.backend, settings=settings, tokens=TokenStore(self.tokens_path))
        self.clients: dict[str, TestClient] = {}
        self.ids: dict[str, str] = {}

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with self.backend() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=list(roles),
                password=prepare_password(PASSWORD, username=name), by="svc:accept",
            )  # fmt: skip
        self.ids[name] = view.account_id
        _, token = sessions.sign_in(self.backend, username=name, password=PASSWORD)
        client = TestClient(self.app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        self.clients[name] = client

    def agent(self, name: str) -> None:
        token = add_token(self.tokens_path, f"agent:{name}")
        client = TestClient(self.app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        self.clients[f"agent:{name}"] = client

    def grant(self, who: str, project: str, module: str, role: str) -> None:
        with self.backend() as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada", source="accept", scope="company", account_id=self.ids[who],
                    project=project, module=module, role=role, reason="acceptance",
                ),
            )  # fmt: skip

    def post(self, who: str, name: str, scope: str) -> int:
        return self.clients[who].post(f"/commands/{name}", json={"scope": scope}).status_code


def run(world: World) -> None:
    world.person("ada", ("admin",))
    world.person("viv", ("user",))  # explicit viewer everywhere
    world.person("uma", ("user",))  # no grant: derived user
    world.person("sue", ("user",))  # explicit superuser everywhere
    world.person("pia", ("user",))  # superuser on P1, viewer on P2
    world.person("dora", ("user", "document_controller"))  # derived superuser (3 modules)
    world.person("solo", ("document_controller",))  # the role and nothing else
    world.agent("triage")
    for project in PROJECTS:
        world.grant("viv", project, "*", "viewer")
        world.grant("sue", project, "*", "superuser")
    world.grant("pia", P1, "*", "superuser")
    world.grant("pia", P2, "*", "viewer")

    index = dict(command_index())
    module_specs = [s for s in COMMANDS if s.module is not None]
    assert {s.name for s in module_specs} == set(index), "table rows and command_words differ"
    passed(f"command_index() lists the {len(index)} module commands the table carries")
    assert all(w in ("admin", "company", "read", "user", "controller") for _, w in index.values())
    passed("command_index() holds only table words and platform words")

    # --- the matrix ------------------------------------------------------------------------
    people = {
        "viewer": "viv", "user": "uma", "superuser": "sue", "admin": "ada", "agent": "agent:triage",
    }  # fmt: skip
    cells = [(r, p) for r in people for p in PROJECTS]
    print("\nMATRIX  Y = let through, - = refused   (viewer user superuser admin agent) x (P1 P2)")
    print(
        f"{'command':36s} {'module':15s} {'word':10s} "
        + " ".join(f"{r[:3]}{p[-1]}" for r, p in cells)
    )
    mismatches: list[str] = []
    for name, (module, word) in sorted(index.items(), key=lambda kv: (kv[1][0], kv[0])):
        marks: list[str] = []
        for role, project in cells:
            status = world.post(people[role], name, project)
            got = status != 403
            want = expected_allowed(role, word)
            if status not in (200, 403):
                mismatches.append(f"{name} {role} {project}: status {status}")
            if got != want:
                mismatches.append(f"{name} {role} {project}: got {status}, table says {want}")
            marks.append(("Y" if got else "-") + ("" if got == want else "!"))
        print(f"{name:36s} {module:15s} {word:10s} " + " ".join(f"{m:4s}" for m in marks))
    assert not mismatches, mismatches[:10]
    passed(f"matrix: {len(index)} commands x 5 roles x 2 projects equals the role table")

    # --- the named cases -------------------------------------------------------------------
    assert world.post("uma", "IssueRevision", P2) == 403
    assert world.post("uma", "RegisterDocument", P2) == 200
    passed("a plain user with no grant is refused a controller command on P2, allowed a user one")

    assert world.post("pia", "IssueRevision", P1) == 200
    assert world.post("pia", "IssueRevision", P2) == 403
    assert world.post("pia", "RegisterDocument", P2) == 403  # viewer on P2: no user word either
    passed("superuser on P1 only: controller acts on P1, nothing but reading on P2")

    for project in PROJECTS:
        for name in ("IssueRevision", "IssueCorrespondence", "PublishScheduleSnapshot"):
            assert world.post("dora", name, project) == 200, (name, project)
        assert world.post("dora", "ImportCostSnapshot", project) == 403
        assert world.post("dora", "RecordTag", project) == 403  # an admin's, not a controller's
    passed(
        "document_controller derives superuser: documents, correspondence, schedule on P1 and P2"
    )
    assert world.post("solo", "IssueRevision", P1) == 200
    assert world.post("solo", "CreateTag", P1) == 403  # no `user` role: nothing derived there
    passed("a document_controller with no user role: controller acts yes, other modules' user no")
    world.grant("dora", P2, "documents", "viewer")
    assert world.post("dora", "IssueRevision", P2) == 403
    assert world.post("dora", "IssueRevision", P1) == 200
    assert world.post("dora", "IssueCorrespondence", P2) == 200  # other modules keep derived
    passed("an explicit viewer grant replaces the derived superuser, for that module and project")

    # company scope: a `company` word is an admin's there, any signed-in person's on a project
    assert world.post("uma", "AddCodeValue", "company") == 403
    assert world.post("ada", "AddCodeValue", "company") == 200
    assert world.post("uma", "AddCodeValue", P1) == 200
    passed("a `company` command: admin at company scope, a user's on a project")
    assert world.post("uma", "CreateRecord", P1) == 200  # core commands: not module-decided
    assert world.post("viv", "CreateRecord", P1) == 200
    assert world.post("sue", "AdminFlagLink", P1) == 403
    passed("core commands are untouched by module roles (viewer creates a core record)")

    # --- the authorizer ----------------------------------------------------------------------
    plain = Principal(actor="user:x", account_id="a", kind="person", roles=["user"], via="session")
    agent = Principal(
        actor="agent:x", account_id="b", kind="agent", roles=["user"], via="agent_token"
    )
    admin = Principal(actor="user:y", account_id="c", kind="person", roles=["admin"], via="session")
    auth = RoleAuthorizer(controller_actions=controller_actions())
    auth.authorize(plain, "control.command.IssueRevision", "r")  # the endpoint decides
    refuses(ForbiddenError, lambda: auth.authorize(plain, "control.command.NoSuchThing", "r"))
    refuses(ForbiddenError, lambda: auth.authorize(agent, "control.command.IssueRevision", "r"))
    auth.authorize(admin, "control.command.NoSuchThing", "r")
    passed("RoleAuthorizer: a listed control action passes a person, an unlisted one is an admin's")

    # --- the runner, per module --------------------------------------------------------------
    stubs = tuple(loosen(s) for s in COMMANDS)
    runner = TableCommandRunner(stubs)

    def probe(spec: CommandSpec, scope: str, actor: str) -> Command:
        return spec.model.model_construct(actor=actor, source="accept", scope=scope)

    modules = sorted({s.module for s in module_specs if s.module})
    for module in modules:
        rows = [s for s in stubs if s.module == module]
        pick = next((s for s in rows if effective_access(s) == "controller"), None)
        pick = pick or next((s for s in rows if effective_access(s) in ("user", "company")), None)
        pick = pick or rows[0]
        word = effective_access(pick)
        for project, role in ((P1, "superuser"), (P2, "viewer")):
            want = expected_allowed(role, word)
            with world.backend() as uow:
                try:
                    runner.run(uow, probe(pick, project, "user:pia"))
                    got = True
                except CommandAccessError:
                    got = False
            assert got == want, (module, pick.name, project, got, want)
    passed(f"runner: one command per module ({len(modules)}) decided by the module role, per scope")
    with world.backend() as uow:
        refuses(
            CommandAccessError,
            lambda: runner.run(
                uow,
                probe(loosen(CommandSpec(CreateRecord, handle_create_record)), P1, "agent:triage"),
            ),
        )
    passed("runner: an agent still proposes, never runs a record command")

    # --- proposal acceptance, per module with a proposable --------------------------------------
    cases = [
        ("schedule", "propose_publish_schedule_snapshot", PublishScheduleSnapshot,
         {"snapshot_id": "snap"}),
        ("documents", "propose_import_documents", PublishDerivedDocuments,
         {"derived_id": "d", "expected_content_rev": 1}),
        ("correspondence", "propose_triage", ConfirmTriage,
         {"stream_id": "s", "domain": "general", "subtype": "letter"}),
    ]  # fmt: skip

    def module_role(who: str, module: str, project: str) -> str:
        """The role each accepter holds, as the grants above made it."""
        if who == "dora":  # derived superuser, but an explicit viewer on documents in P2
            return "viewer" if (module, project) == ("documents", P2) else "superuser"
        if who == "pia":
            return "superuser" if project == P1 else "viewer"
        return "user"

    accepted_ok = refused = 0
    for module, tool, model, fields in cases:
        word = effective_access(next(s for s in COMMANDS if s.model is model))
        for project in PROJECTS:
            for who in ("dora", "uma", "pia"):
                with world.backend() as uow:
                    view = proposals.propose(
                        uow, tool=tool, agent="agent:triage", summary=f"{module} {project}",
                        command=model(
                            actor="agent:triage", source="mcp:triage", scope=project, **fields
                        ),
                    )  # fmt: skip
                response = world.clients[who].post(f"/proposals/{view.proposal_id}/accept", json={})
                account_role_ok = word != "controller" or who == "dora"  # ADR-0014, as before
                want = account_role_ok and expected_allowed(module_role(who, module, project), word)
                assert (response.status_code != 403) == want, (
                    module, project, who, response.status_code, response.text[:120],
                )  # fmt: skip
                if not want:
                    assert response.json()["error"] == "proposal_access", response.text[:120]
                    refused += 1
                else:
                    accepted_ok += 1
    passed(
        f"proposal accept: {refused} refused 403 for an accepter without the word on the stored "
        f"scope, {accepted_ok} let through, across schedule, documents and correspondence"
    )

    # --- require_generic, per module ------------------------------------------------------------
    class Probe(Command):
        pass

    refused_in = 0
    for spec in load_modules():
        pick = next(
            ((rt, sorted(cmds)[0]) for rt, cmds in sorted(spec.generic_commands.items()) if cmds),
            None,
        )
        if pick is None:
            continue
        record_type, command = pick
        ids: dict[str, str] = {}
        for project in PROJECTS:
            with world.backend() as uow:
                made = create_module_record(
                    uow,
                    Probe(actor="user:ada", source="accept", scope=project),
                    record_type=record_type, title="probe", key=f"PR-{spec.name}-{project[-1]}",
                    composed_key=True,
                )  # fmt: skip
            ids[project] = made.stream_id
        with world.backend(True) as uow, system_view():
            conn = uow.conn()
            require_generic(conn, record_type, command, ids[P1], actor="user:ada")  # admin, P1
            on_p2 = ids[P2]
            refuses(
                ForbiddenError,
                lambda c=conn, t=record_type, k=command, i=on_p2: require_generic(
                    c, t, k, i, actor="user:pia"
                ),
            )
            try:
                require_generic(conn, record_type, command, ids[P1], actor="user:pia")
            except ForbiddenError:
                raise AssertionError(f"{spec.name}: pia holds user on P1") from None
            except Exception:  # noqa: S110 - the module's own state guard may refuse, not the word
                pass
        refused_in += 1
    passed(f"require_generic: the word `user` refused on P2, held on P1, for {refused_in} modules")

    # --- GET /records/{id}/actions --------------------------------------------------------------
    doc: dict[str, str] = {}
    for project in PROJECTS:
        with world.backend() as uow:
            doc[project] = handle_register_document(
                uow,
                RegisterDocument(
                    actor="user:ada", source="accept", scope=project, number=f"D-{project[-1]}",
                    title="Doc",
                ),
            ).stream_id  # fmt: skip
    offered_total = 0
    for who in ("viv", "uma", "sue", "ada", "pia", "dora", "agent:triage"):
        for project in PROJECTS:
            response = world.clients[who].get(f"/records/{doc[project]}/actions")
            assert response.status_code == 200, (who, project, response.status_code)
            for offer in response.json()["actions"]:
                offered_total += 1
                assert world.post(who, offer["command"], project) == 200, (who, project, offer)
    assert offered_total > 0

    def offered(who: str, project: str) -> set[str]:
        got = world.clients[who].get(f"/records/{doc[project]}/actions").json()
        return {o["command"] for o in got["actions"]}

    offers = {(w, p): offered(w, p) for w in ("viv", "uma", "sue", "pia", "dora") for p in PROJECTS}
    assert "VoidDocument" in offers[("sue", P1)] and "VoidDocument" in offers[("dora", P1)]
    assert not offers[("uma", P1)] & {"VoidDocument", "SupersedeDocument"}
    assert not offers[("pia", P2)] and not offers[("viv", P1)]
    assert not offers[("dora", P2)]  # explicit viewer on documents P2
    passed(f"GET /records/{{id}}/actions: {offered_total} offers, all let through by the endpoint")

    # --- fine words and the start-up checks ------------------------------------------------------
    class ReleaseCwp(Command):
        pass

    class ViewCwp(Command):
        pass

    stand_in = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Cwp"}),
        projectors=list,
        command_words={"ReleaseCwp": "awp.cwp.release", "ViewCwp": "awp.view"},
    )
    with use_modules([*load_modules(), stand_in]):
        found = command_index()
        assert found["ReleaseCwp"] == ("awp", "controller"), found["ReleaseCwp"]
        assert found["ViewCwp"] == ("awp", "read"), found["ViewCwp"]
        with world.backend(True) as uow:
            conn = uow.conn()
            release = ReleaseCwp(actor="user:uma", source="accept", scope=P1)
            refuses(ForbiddenError, lambda: require_command_access(conn, release))
            require_command_access(conn, release.model_copy(update={"actor": "user:sue"}))
            view = ViewCwp(actor="user:viv", source="accept", scope=P1)
            require_command_access(conn, view)
        assert holder_for_actor is not None
    passed("a stand-in module's awp.cwp.release reads as controller and awp.view as read")

    bad = ModuleSpec(
        name="awp", record_types=frozenset({"awp.Cwp"}), projectors=list,
        command_words={"ReleaseCwp": "awp.cwp.relase"},
    )  # fmt: skip
    with use_modules([*load_modules(), bad]):
        refuses(AccessWordError, command_index)
    passed("an unknown fine word raises AccessWordError from command_index()")

    spec = CommandSpec(CreateRecord, handle_create_record, "awp.cwp.release", module="awp")
    assert effective_access(spec) == "controller"
    assert action_for(spec) == "control.command.CreateRecord"
    read = CommandSpec(CreateRecord, handle_create_record, "awp.view", module="awp")
    assert effective_access(read) == "read" and action_for(read) == "command.CreateRecord"
    for typo in ("awp.cwp.relase", "Controller", "", "admn"):
        refuses(
            AccessWordError, lambda typo=typo: CommandSpec(CreateRecord, handle_create_record, typo)
        )
    refuses(ValueError, lambda: CommandSpec(CreateRecord, handle_create_record, "controller"))
    refuses(ValueError, lambda: CommandSpec(CreateRecord, handle_create_record, "awp.cwp.release"))
    passed("Access takes a fine word; a typo fails at construction; controller needs a module")

    wrong = CommandSpec(CreateRecord, handle_create_record, "controller", module="documents")
    refuses(ValueError, lambda: check_command_words([wrong]))
    check_command_words(COMMANDS)
    passed("start-up: a module row the module's command_words do not carry is an error")

    proposable = {item.model.__name__ for s in load_modules() for item in s.proposable}
    assert proposable <= set(index), proposable - set(index)
    passed("every module proposable command is in command_index()")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="rm-s2-"))
    world = World(work)
    try:
        run(world)
    finally:
        world.backend.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
