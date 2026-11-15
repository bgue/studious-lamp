"""The nested-command seam (P2-FORMS S3, D8): one module command runs inside the caller's unit."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ConfigDict
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_core.auth.module_roles import Holder
from tl_core.ledger import Event
from tl_core.modules import ModuleSpec, ProposableCommand, use_modules
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import InvalidProposalError, ProposalAccessError
from tl_core.services.nested import (
    MSG_NOT_NESTABLE,
    NestedCommandError,
    run_nested_command,
)
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

NOTE = "nest.Note"
SCOPE = "project:P1"
CALLER = "user:uma"


class NestProjector:
    name = "nest"
    handles = frozenset({"Nest.Never"})

    def ddl(self, dialect: str) -> list[str]:
        return []

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


class MakeNote(Command):
    model_config = ConfigDict(extra="forbid")
    title: str = "note"


class MakeBossNote(Command):
    model_config = ConfigDict(extra="forbid")
    title: str = "boss note"


class Refuse(Command):
    model_config = ConfigDict(extra="forbid")


def _make(uow: UnitOfWork, cmd: MakeNote | MakeBossNote) -> CommandResult:
    return create_module_record(
        uow,
        cmd,
        record_type=NOTE,
        title=cmd.title,
        key=f"N-{cmd.title}",
        extra_events=[],
    )


def _refuse(uow: UnitOfWork, cmd: Refuse) -> CommandResult:
    del uow, cmd
    raise InvalidProposalError("refused on purpose")


@pytest.fixture
def nest(db: DbTarget) -> Iterator[DbTarget]:
    spec = ModuleSpec(
        name="nest",
        record_types=frozenset({NOTE}),
        projectors=lambda: [NestProjector()],
        proposable=(
            ProposableCommand("propose_note", MakeNote, _make, "user"),
            ProposableCommand("propose_boss_note", MakeBossNote, _make, "controller"),
            ProposableCommand("propose_refusal", Refuse, _refuse, "user"),
        ),
    )
    with use_modules([spec]):
        yield db


def run(uow: UnitOfWork, command_type: str, args: dict[str, Any] | None = None, **more: Any) -> Any:
    options: dict[str, Any] = {"actor": CALLER, "scope": SCOPE, "source": "mcp:agent-1"}
    options.update(more)
    return run_nested_command(uow, command_type=command_type, args=args or {}, **options)


def count(db: DbTarget, table: str = "cur_core_record") -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_a_proposable_module_command_runs_in_the_callers_unit(nest: DbTarget) -> None:
    with open_uow(nest) as uow:
        result = run(uow, "MakeNote", {"title": "alpha"})
        assert uow.conn().execute(text("SELECT count(*) FROM cur_core_record")).scalar_one() == 1
    assert result.key == "N-alpha" and count(nest) == 1


def test_a_refusal_rolls_back_an_earlier_append_of_the_same_unit(nest: DbTarget) -> None:
    with pytest.raises(InvalidProposalError, match="on purpose"), open_uow(nest) as uow:
        run(uow, "MakeNote", {"title": "first"})
        run(uow, "Refuse")
    assert count(nest) == 0 and count(nest, "events") == 0


@pytest.mark.parametrize(
    "name",
    [
        "CreateRecord",
        "UpdateRecord",
        "VoidRecord",
        "TransitionWorkflow",
        "DispatchFromThread",
        "InvokeAction",
        "ChangeSetting",
        "NoSuchCommand",
        "",
    ],
)
def test_core_commands_and_unknown_names_are_refused_with_one_text(
    nest: DbTarget, name: str
) -> None:
    with pytest.raises(NestedCommandError) as caught, open_uow(nest) as uow:
        run(uow, name, {"stream_id": "x", "transition": "publish"})
    assert str(caught.value) == MSG_NOT_NESTABLE
    assert NestedCommandError is InvalidProposalError
    assert count(nest, "events") == 0


def test_a_core_command_is_refused_even_when_the_caller_holds_everything(nest: DbTarget) -> None:
    with pytest.raises(NestedCommandError), open_uow(nest) as uow:
        run(uow, "ChangeSetting", {}, holds=lambda level: True)


def test_args_naming_the_actor_the_source_or_roles_cannot_impersonate(nest: DbTarget) -> None:
    with open_uow(nest) as uow:
        result = run(
            uow,
            "MakeNote",
            {"title": "beta", "actor": "user:ada", "source": "api", "actor_roles": ["admin"]},
            causation_id="CAUSE1",
            correlation_id="CORR1",
        )
    with open_uow(nest, readonly=True) as uow:
        rows = uow.conn().execute(
            text("SELECT actor, source, causation_id, correlation_id FROM events")
        )
        events = [tuple(r) for r in rows]
    assert result.events and events
    assert set(events) == {(CALLER, "mcp:agent-1", "CAUSE1", "CORR1")}


def test_the_caller_sets_the_scope_whatever_the_args_say(nest: DbTarget) -> None:
    with open_uow(nest) as uow:
        run(uow, "MakeNote", {"title": "gamma", "scope": "company"})
    with open_uow(nest, readonly=True) as uow:
        found = uow.conn().execute(text("SELECT DISTINCT scope FROM events")).scalars().all()
    assert list(found) == [SCOPE]


def test_without_holds_or_holder_a_controller_command_is_refused_and_a_user_command_runs(
    nest: DbTarget,
) -> None:
    with pytest.raises(ProposalAccessError), open_uow(nest) as uow:
        run(uow, "MakeBossNote")
    assert count(nest) == 0
    with open_uow(nest) as uow:
        run(uow, "MakeNote", {"title": "delta"})
    assert count(nest) == 1


def test_holds_decides_a_controller_command(nest: DbTarget) -> None:
    with pytest.raises(ProposalAccessError), open_uow(nest) as uow:
        run(uow, "MakeBossNote", holds=lambda level: level == "admin")
    with open_uow(nest) as uow:
        run(uow, "MakeBossNote", holds=lambda level: level == "controller")
    assert count(nest) == 1


def test_a_holder_adds_the_module_role_check(nest: DbTarget) -> None:
    stranger = Holder(actor=CALLER, kind="person", account_id=None, account_roles=("user",))
    with open_uow(nest) as uow:  # no word is declared for these commands: the check is a no-op
        run(uow, "MakeNote", {"title": "eps"}, holder=stranger)
    assert count(nest) == 1
