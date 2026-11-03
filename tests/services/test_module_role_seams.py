"""The seams that consult the module roles (roles-mvp.md section 5, RM-S2): the command runner,
proposal accept, ``require_generic``, the per-module word tables, the cross-scope refusal.

The accounts and the grants are real (ledger, projection, resolver). The runner is given stub
handlers so only the access decision shows; the proposal and the generic-command cases run the
real core code. Everything runs on every adapter (``db``).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_api.commands import (
    COMMANDS,
    CommandSpec,
    TableCommandRunner,
    effective_access,
)
from tl_core.auth import accounts
from tl_core.auth.access_words import AccessWordError
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import (
    command_index,
    holder_for_actor,
    require_command_access,
)
from tl_core.confidentiality import system_view
from tl_core.integration.errors import CommandAccessError
from tl_core.modules import ModuleSpec, load_modules, require_generic, use_modules
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import proposals
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import ProposalAccessError
from tl_core.services.records import create_module_record
from tl_mod_correspondence.commands import API_COMMANDS as CORRESPONDENCE
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_mod_cost.commands import API_COMMANDS as COST
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot as ImportCostSnapshotModel
from tl_mod_documents.commands import API_COMMANDS as DOCUMENTS
from tl_mod_documents.derivation.publish import PublishDerivedDocuments
from tl_mod_engineering.commands import API_COMMANDS as ENGINEERING
from tl_mod_materials.commands import MATERIALS_COMMANDS as MATERIALS
from tl_mod_schedule.commands import API_COMMANDS as SCHEDULE
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schemareg.commands import API_COMMANDS as SCHEMAREG

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
P1, P2 = "project:P1", "project:P2"
AGENT = "agent:triage"
OK = CommandResult(stream_id="stub", key=None, version=1, events=[])
API_COMMANDS_OF = {
    "correspondence": CORRESPONDENCE,
    "cost": COST,
    "documents": DOCUMENTS,
    "engineering": ENGINEERING,
    "materials": MATERIALS,
    "schedule": SCHEDULE,
    "schemareg": SCHEMAREG,
}


# --- the word tables ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", sorted(API_COMMANDS_OF))
def test_command_words_equal_the_modules_api_commands(module: str) -> None:
    spec = next(s for s in load_modules() if s.name == module)
    declared = {c.model.__name__: c.access for c in API_COMMANDS_OF[module]}
    assert dict(spec.command_words) == declared and declared
    wrapped = {s.name: s.access for s in COMMANDS if s.module == module}
    assert wrapped == declared  # the API's table carries the same rows, module by module


def test_legacy_has_no_api_commands_and_no_words() -> None:
    spec = next(s for s in load_modules() if s.name == "legacy")
    assert dict(spec.command_words) == {}
    assert "legacy" not in API_COMMANDS_OF and not any(s.module == "legacy" for s in COMMANDS)


def test_every_module_row_of_the_api_table_is_in_the_index_and_nothing_else_is() -> None:
    index = command_index()
    assert {s.name for s in COMMANDS if s.module is not None} == set(index)
    assert {m for m, _ in index.values()} == set(API_COMMANDS_OF)
    assert {w for _, w in index.values()} <= {"admin", "company", "read", "user", "controller"}


def test_command_index_reads_a_fine_word_as_its_table_word() -> None:
    class ReleaseCwp(Command): ...

    class ViewCwp(Command): ...

    stand_in = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Cwp"}),
        projectors=list,
        command_words={"ReleaseCwp": "awp.cwp.release", "ViewCwp": "awp.view"},
    )
    with use_modules([*load_modules(), stand_in]):
        found = command_index()
    assert found["ReleaseCwp"] == ("awp", "controller")
    assert found["ViewCwp"] == ("awp", "read")


def test_command_index_refuses_an_unknown_fine_word_and_a_name_in_two_modules() -> None:
    typo = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Cwp"}),
        projectors=list,
        command_words={"ReleaseCwp": "awp.cwp.relase"},
    )
    with use_modules([*load_modules(), typo]), pytest.raises(AccessWordError):
        command_index()
    twin = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Cwp"}),
        projectors=list,
        command_words={"RegisterDocument": "user"},
    )
    from tl_core.modules import ModuleLoadError

    with use_modules([*load_modules(), twin]), pytest.raises(ModuleLoadError):
        command_index()


def test_a_fine_word_decides_a_command_through_its_table_word(db: DbTarget) -> None:
    create_schema(db)

    class ReleaseCwp(Command): ...

    class ViewCwp(Command): ...

    stand_in = ModuleSpec(
        name="awp",
        record_types=frozenset({"awp.Cwp"}),
        projectors=list,
        command_words={"ReleaseCwp": "awp.cwp.release", "ViewCwp": "awp.view"},
    )
    world = Seams(db)
    world.person("viv")
    world.person("uma")
    world.person("sue")
    with use_modules([*load_modules(), stand_in]):
        world.grant("viv", P1, "awp", "viewer")
        world.grant("uma", P1, "awp", "user")
        world.grant("sue", P1, "awp", "superuser")
        check_fine_word(db, ReleaseCwp, ViewCwp)


def check_fine_word(db: DbTarget, ReleaseCwp: type[Command], ViewCwp: type[Command]) -> None:
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        for who, release, view in (("viv", False, True), ("uma", False, True), ("sue", True, True)):
            for cls, allowed in ((ReleaseCwp, release), (ViewCwp, view)):
                command = cls(actor=f"user:{who}", source="t", scope=P1)
                if allowed:
                    require_command_access(conn, command)
                else:
                    with pytest.raises(ForbiddenError, match="controller access word for awp"):
                        require_command_access(conn, command)


# --- a world with accounts and grants ----------------------------------------------------------


class Seams:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.ids: dict[str, str] = {}
        self.person("ada", ("admin",))

    def person(self, name: str, roles: tuple[str, ...] = ("user",)) -> None:
        with open_uow(self.db) as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=list(roles),
                password=None, by="user:root",
            )  # fmt: skip
        self.ids[name] = view.account_id

    def grant(self, who: str, project: str, module: str, role: str) -> None:
        with open_uow(self.db) as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada", source="test", scope="company", account_id=self.ids[who],
                    project=project, module=module, role=role, reason="test",
                ),
            )  # fmt: skip


@pytest.fixture
def seams(db: DbTarget) -> Iterator[Seams]:
    create_schema(db)
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        world = Seams(db)
        world.person("pia")  # superuser on P1, viewer on P2, everywhere
        world.person("uma")  # no grant
        world.person("dora", ("document_controller",))
        world.person("sue")
        world.grant("pia", P1, "*", "superuser")
        world.grant("pia", P2, "*", "viewer")
        yield world


# --- the command runner ------------------------------------------------------------------------


def stub(spec: CommandSpec) -> CommandSpec:
    return dataclasses.replace(spec, handler=lambda *a, **k: OK)


def probe(spec: CommandSpec, scope: str, actor: str) -> Command:
    return spec.model.model_construct(actor=actor, source="test", scope=scope)


MODULES = sorted({s.module for s in COMMANDS if s.module})


def pick(module: str) -> CommandSpec:
    rows = [s for s in COMMANDS if s.module == module]
    controlling = next((s for s in rows if effective_access(s) == "controller"), None)
    return controlling or next(
        (s for s in rows if effective_access(s) in ("user", "company")), rows[0]
    )


@pytest.mark.parametrize("module", MODULES)
def test_the_runner_decides_a_module_command_by_the_role_on_the_commands_scope(
    seams: Seams, module: str
) -> None:
    runner = TableCommandRunner(tuple(stub(s) for s in COMMANDS))
    chosen = pick(module)
    word = effective_access(chosen)
    for project, role in ((P1, "superuser"), (P2, "viewer")):
        # a viewer holds only `read`; a superuser every word
        allowed = role == "superuser" and word != "admin"
        with open_uow(seams.db) as uow:
            if allowed:
                assert runner.run(uow, probe(chosen, project, "user:pia")) == OK
            else:
                with pytest.raises(CommandAccessError):
                    runner.run(uow, probe(chosen, project, "user:pia"))


def test_the_runner_lets_a_plain_user_run_a_user_command_but_not_a_controlling_one(
    seams: Seams,
) -> None:
    runner = TableCommandRunner(tuple(stub(s) for s in COMMANDS))
    user_cmd = next(s for s in COMMANDS if s.name == "RegisterDocument")
    control_cmd = next(s for s in COMMANDS if s.name == "IssueRevision")
    with open_uow(seams.db) as uow:
        assert runner.run(uow, probe(user_cmd, P1, "user:uma")) == OK
        with pytest.raises(CommandAccessError, match="controller access word for documents"):
            runner.run(uow, probe(control_cmd, P1, "user:uma"))


def test_the_runner_does_not_use_the_dev_ledger_rule(seams: Seams) -> None:
    """A person with no account is refused by the runner, whatever the ledger (dev_file=False)."""
    runner = TableCommandRunner(tuple(stub(s) for s in COMMANDS))
    user_cmd = next(s for s in COMMANDS if s.name == "RegisterDocument")
    with open_uow(seams.db) as uow, pytest.raises(CommandAccessError):
        runner.run(uow, probe(user_cmd, P1, "user:nobody"))


def test_the_runner_still_makes_an_agent_propose(seams: Seams) -> None:
    runner = TableCommandRunner(tuple(stub(s) for s in COMMANDS))
    user_cmd = next(s for s in COMMANDS if s.name == "RegisterDocument")
    with open_uow(seams.db) as uow, pytest.raises(CommandAccessError, match="proposes"):
        runner.run(uow, probe(user_cmd, P1, AGENT))


def test_a_service_actor_keeps_its_declared_access_and_skips_the_module_table(
    seams: Seams,
) -> None:
    runner = TableCommandRunner(tuple(stub(s) for s in COMMANDS))
    control_cmd = next(s for s in COMMANDS if s.name == "IssueRevision")
    with (
        mock.patch("tl_api.commands.require_access", return_value="controller") as declared,
        mock.patch("tl_api.commands.require_command_access") as module_check,
        open_uow(seams.db) as uow,
    ):
        assert runner.run(uow, probe(control_cmd, P1, "svc:rule-x")) == OK
    assert declared.call_count == 1 and module_check.call_count == 0


# --- proposal accept: the account role AND the module role (D14) -------------------------------


def factory(db: DbTarget) -> proposals.Factory:
    def open_one(readonly: bool = False):  # type: ignore[no-untyped-def]
        return open_uow(db, readonly=readonly)

    return open_one


def holds_only(*levels: str) -> Callable[[str], bool]:
    return lambda level: level == "user" or level in levels


def propose_publish(db: DbTarget, project: str) -> str:
    command = PublishDerivedDocuments(
        actor=AGENT, source="mcp:triage", scope=project, derived_id="X", expected_content_rev=1
    )
    with open_uow(db) as uow:
        return proposals.propose(
            uow, tool="propose_import_documents", agent=AGENT, command=command, summary="docs"
        ).proposal_id


def status(db: DbTarget, proposal_id: str) -> str:
    with open_uow(db, readonly=True) as uow:
        return proposals.get_proposal(uow.conn(), proposal_id).status


def accept(
    seams: Seams, proposal_id: str, who: str, holds: Callable[[str], bool], holder: bool = True
):  # type: ignore[no-untyped-def]
    found = None
    if holder:
        with open_uow(seams.db, readonly=True) as uow:
            found = holder_for_actor(uow.conn(), f"user:{who}")
    return proposals.accept_or_fail(
        factory(seams.db), proposal_id=proposal_id, by=f"user:{who}", holds=holds, holder=found
    )


def test_a_controller_proposal_needs_the_account_role_even_with_a_superuser_grant(
    seams: Seams,
) -> None:
    """AND, not replace: `pia` is a superuser of documents on P1 but holds no controller role."""
    pid = propose_publish(seams.db, P1)
    with pytest.raises(ProposalAccessError, match="controller role"):
        accept(seams, pid, "pia", holds_only())
    assert status(seams.db, pid) == "pending"


def test_a_controller_proposal_needs_the_module_word_on_the_stored_scope(seams: Seams) -> None:
    seams.grant("dora", P2, "documents", "viewer")  # lowered on P2, still the account role
    refused = propose_publish(seams.db, P2)
    with pytest.raises(
        ProposalAccessError, match="controller access word for documents on project:P2"
    ):
        accept(seams, refused, "dora", holds_only("controller"))
    assert status(seams.db, refused) == "pending"
    ok = propose_publish(seams.db, P1)
    view = accept(seams, ok, "dora", holds_only("controller"))
    assert view.status in ("accepted", "failed")  # past the gate; the command fails on its own


def test_an_entry_point_with_no_holder_keeps_the_account_role_check_only(seams: Seams) -> None:
    seams.grant("dora", P2, "documents", "viewer")
    pid = propose_publish(seams.db, P2)
    view = accept(seams, pid, "dora", holds_only("controller"), holder=False)
    assert view.status in ("accepted", "failed")


def test_an_admin_accepts_on_any_project(seams: Seams) -> None:
    pid = propose_publish(seams.db, P2)
    view = accept(seams, pid, "ada", holds_only("controller", "admin"))
    assert view.status in ("accepted", "failed")


@pytest.mark.parametrize(
    ("tool", "model", "fields", "module"),
    [
        (
            "propose_publish_schedule_snapshot",
            PublishScheduleSnapshot,
            {"snapshot_id": "s"},
            "schedule",
        ),
        (
            "propose_triage",
            ConfirmTriage,
            {"stream_id": "s", "domain": "general", "subtype": "letter"},
            "correspondence",
        ),
    ],
)
def test_a_proposal_of_each_other_module_is_decided_on_its_stored_scope(
    seams: Seams, tool: str, model: type[Command], fields: dict[str, Any], module: str
) -> None:
    word = command_index()[model.__name__][1]
    levels = ("controller",) if word == "controller" else ()
    seams.grant("dora", P2, module, "viewer")
    for project, expect_refused in ((P2, True), (P1, False)):
        with open_uow(seams.db) as uow:
            pid = proposals.propose(
                uow, tool=tool, agent=AGENT, summary=module,
                command=model(actor=AGENT, source="mcp:triage", scope=project, **fields),
            ).proposal_id  # fmt: skip
        if expect_refused:
            with pytest.raises(ProposalAccessError, match=f"for {module} on {project}"):
                accept(seams, pid, "dora", holds_only(*levels))
            assert status(seams.db, pid) == "pending"
        else:
            assert accept(seams, pid, "dora", holds_only(*levels)).status in ("accepted", "failed")


# --- require_generic ----------------------------------------------------------------------------


class Probe(Command): ...


def generic_picks() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for spec in load_modules():
        for record_type, commands in sorted(spec.generic_commands.items()):
            if commands:
                found.append((spec.name, record_type, sorted(commands)[0]))
                break
    return found


def test_every_module_with_a_record_type_is_walked_by_the_require_generic_test() -> None:
    assert [m for m, _, _ in generic_picks()] == [
        "correspondence",
        "cost",
        "documents",
        "engineering",
        "materials",
        "schedule",
        "schemareg",
    ]


@pytest.mark.parametrize(("module", "record_type", "command"), generic_picks())
def test_require_generic_needs_the_user_word_on_the_records_own_scope(
    seams: Seams, module: str, record_type: str, command: str
) -> None:
    ids: dict[str, str] = {}
    for project in (P1, P2):
        with open_uow(seams.db) as uow:
            made = create_module_record(
                uow,
                Probe(actor="user:ada", source="test", scope=project),
                record_type=record_type,
                title="probe",
                key=f"PR-{module}-{project[-1]}",
                composed_key=True,
            )
        ids[project] = made.stream_id
    with open_uow(seams.db, readonly=True) as uow, system_view():
        conn = uow.conn()
        require_generic(conn, record_type, command, ids[P1], actor="user:ada")  # admin
        # a viewer on P2 holds no `user` word there
        with pytest.raises(ForbiddenError, match=f"user access word for {module} on {P2}"):
            require_generic(conn, record_type, command, ids[P2], actor="user:pia")
        # a superuser on P1 passes the word (the module's own state guard may still refuse)
        try:
            require_generic(conn, record_type, command, ids[P1], actor="user:pia")
        except ForbiddenError:
            raise AssertionError(f"{module}: pia holds user on P1") from None
        except Exception:  # noqa: BLE001, S110 - the module's own state guard, not the word
            pass
        # an agent, and an actor with no account off the dev ledger, hold nothing
        with pytest.raises(ForbiddenError):
            require_generic(conn, record_type, command, ids[P1], actor="agent:ghost")
        # no actor: the allow-list and the guard only (the read-side offer)
        try:
            require_generic(conn, record_type, command, ids[P2])
        except ForbiddenError:
            raise AssertionError("no actor, no word check") from None
        except Exception:  # noqa: BLE001, S110
            pass


def test_require_generic_passes_a_core_record_type_with_any_actor(seams: Seams) -> None:
    with open_uow(seams.db) as uow:
        from tl_core.services.commands import CreateRecord
        from tl_core.services.records import handle_create_record

        made = handle_create_record(
            uow,
            CreateRecord(
                actor="user:ada",
                source="t",
                scope=P2,
                record_type="core.Record",
                title="n",
                key="N-1",
            ),
        )
    with open_uow(seams.db, readonly=True) as uow, system_view():
        require_generic(uow.conn(), "core.Record", "AddLink", made.stream_id, actor="user:pia")


# --- the scope on the command is the project the check uses -------------------------------------


def scalar(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_documents_refuse_a_document_of_another_project(seams: Seams, tmp_path: Path) -> None:
    from tl_mod_documents.errors import DocumentNotFoundError
    from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document
    from tl_mod_documents.testing import DocumentsWorld

    world = DocumentsWorld(seams.db, tmp_path / "objects")
    world.load_standards()
    made = world.register("ISD-001")  # the world's own project
    before = scalar(seams.db, "SELECT COUNT(*) FROM events")
    with open_uow(seams.db) as uow, pytest.raises(DocumentNotFoundError):
        handle_void_document(
            uow,
            VoidDocument(
                actor="user:ada", source="t", scope=P2, stream_id=made.stream_id, reason="x"
            ),
        )
    assert scalar(seams.db, "SELECT COUNT(*) FROM events") == before


def test_engineering_refuse_a_tag_of_another_project(seams: Seams) -> None:
    from tl_mod_engineering.errors import TagNotFoundError
    from tl_mod_engineering.handlers.tags import (
        CreateTag,
        RenameTag,
        handle_create_tag,
        handle_rename_tag,
    )
    from tl_mod_engineering.testing import seed_registry

    seed_registry(seams.db)
    base: dict[str, Any] = {"actor": "user:ada", "source": "t", "scope": P1}
    with open_uow(seams.db) as uow:
        made = handle_create_tag(
            uow,
            CreateTag(**base, number="47-FV-1001", class_code="ControlValve", service="Feed"),
        )
    before = scalar(seams.db, "SELECT COUNT(*) FROM events")
    with open_uow(seams.db) as uow, pytest.raises(TagNotFoundError):
        handle_rename_tag(
            uow,
            RenameTag(
                **{**base, "scope": P2},
                stream_id=made.stream_id,
                new_number="47-FV-1002",
                reason="r",
            ),
        )
    assert scalar(seams.db, "SELECT COUNT(*) FROM events") == before


def test_schedule_refuse_a_schedule_of_another_project(seams: Seams, tmp_path: Path) -> None:
    from tl_mod_schedule.errors import ScheduleNotFoundError
    from tl_mod_schedule.handlers.snapshots import (
        OpenScheduleSnapshot,
        handle_open_schedule_snapshot,
    )
    from tl_mod_schedule.testing import ScheduleWorld

    world = ScheduleWorld(seams.db, tmp_path / "objects")
    made = world.define()  # MAIN, in the world's own project
    before = scalar(seams.db, "SELECT COUNT(*) FROM events")
    with open_uow(seams.db) as uow, pytest.raises(ScheduleNotFoundError):
        handle_open_schedule_snapshot(
            uow,
            OpenScheduleSnapshot(
                actor="user:ada", source="t", scope=P2, schedule_id=made.stream_id
            ),
        )
    assert scalar(seams.db, "SELECT COUNT(*) FROM events") == before


def test_correspondence_refuse_a_draft_of_another_project(seams: Seams) -> None:
    from tl_core.services.errors import RecordNotFoundError
    from tl_mod_correspondence.handlers.responses import VoidDraft, handle_void_draft
    from tl_mod_correspondence.testing import CorrWorld

    item = CorrWorld(seams.db).forge_item(state="Draft")  # in the world's own project
    before = scalar(seams.db, "SELECT COUNT(*) FROM events")
    with open_uow(seams.db) as uow, pytest.raises(RecordNotFoundError):
        handle_void_draft(
            uow, VoidDraft(actor="user:ada", source="t", scope=P2, stream_id=item, reason="x")
        )
    assert scalar(seams.db, "SELECT COUNT(*) FROM events") == before


def test_cost_refuse_a_command_that_is_not_scoped_to_a_project(seams: Seams) -> None:
    from tl_mod_cost.errors import CostScopeError
    from tl_mod_cost.testing import CostWorld, row

    world = CostWorld(seams.db)
    world.import_snapshot([row("4210-PIP", hours_budget=10)])  # a project scope: accepted
    with pytest.raises(CostScopeError):
        world.import_snapshot([row("4210-PIP", hours_budget=10)], scope="company")
    # the word is `admin`: no module grant gives it, an admin passes on any scope
    command = ImportCostSnapshotModel.model_construct(actor="user:sue", source="t", scope=P1)
    seams.grant("sue", P1, "cost", "superuser")
    with open_uow(seams.db, readonly=True) as uow:
        with pytest.raises(ForbiddenError, match="admin access word for cost"):
            require_command_access(uow.conn(), command)
        require_command_access(uow.conn(), command.model_copy(update={"actor": "user:ada"}))


def test_schemareg_commands_run_at_company_scope_where_a_project_grant_is_not_read(
    seams: Seams,
) -> None:
    """A registry command is decided at the command's own scope; at ``company`` only the derived
    roles count, so a project viewer grant neither lowers nor raises what a user holds there."""
    seams.grant("sue", P1, "schemareg", "viewer")
    name = next(n for n, (m, w) in command_index().items() if m == "schemareg" and w == "user")
    model = next(s.model for s in COMMANDS if s.name == name)
    command = model.model_construct(actor="user:sue", source="t", scope="company")
    with open_uow(seams.db, readonly=True) as uow:
        require_command_access(uow.conn(), command)  # derived `user`
        with pytest.raises(ForbiddenError, match=f"user access word for schemareg on {P1}"):
            require_command_access(uow.conn(), command.model_copy(update={"scope": P1}))
