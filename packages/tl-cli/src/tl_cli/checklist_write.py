"""`tl checklist` write verbs: create, edit, publish, revise, retire (P2-INSP-T05).

Each verb builds one command model of ``tl_mod_quality.commands``, gates it with ``require_command``
and runs the handler that ``INSP_COMMANDS`` names, on one unit of work. A checklist is named by the
key a read prints and resolved to its record id with ``get_record``, as the actor's viewer reads it
(a hidden checklist answers as one that does not exist). ``--questions-file`` is read here as a JSON
list of question objects (at most 256 KiB); the question rules run in the handlers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_quality.commands import (
    CreateChecklist,
    EditChecklist,
    PublishChecklist,
    RetireChecklist,
    ReviseChecklist,
)
from tl_mod_quality.module import INSP_COMMANDS
from tl_mod_quality.names import CHECKLIST

from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command

#: The largest question file the CLI reads (bytes).
MAX_QUESTIONS_FILE = 256 * 1024

QUESTIONS_HELP = "A JSON list of question objects, as the command takes them."
QUESTIONS_FILE = Annotated[Path | None, typer.Option("--questions-file", help=QUESTIONS_HELP)]


def _handler(model: type[Command]) -> Callable[[UnitOfWork, Any], CommandResult]:
    """The handler ``INSP_COMMANDS`` names for this command model."""
    return next(c.handler for c in INSP_COMMANDS if c.model is model)


def _execute(db: DbTarget, who: str, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    """Build the command on the ledger, gate it with the module role, run its handler; one write.

    The build, the gate and the handler read as ``who``, the acting person, as the permit verbs
    (``tl_mod_permits/cli_permit_write.py::_execute``) and ``cli_isolation`` do. The process's own
    viewer on a dev ledger is the file's owner, who reads restricted records, so a refusal that
    names a record would name one ``who`` cannot see.
    """
    with service_errors(), open_uow(db) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), who)):
        command = build(uow)
        require_command(uow, command)
        return _handler(type(command))(uow, command)


def _model(model: type[Command], **fields: Any) -> Command:
    """The command model with ``fields``; a value the model refuses is a usage error (exit 2)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc.errors()[0]["msg"])) from None


def _given(**options: Any) -> dict[str, Any]:
    """The options the user gave (a None is not given: the field is left out of the command)."""
    return {name: value for name, value in options.items() if value is not None}


def _questions(path: Path | None) -> list[Any] | None:
    """The question list in ``path`` (JSON), or None when no file is named.

    A file over ``MAX_QUESTIONS_FILE`` bytes is refused before it is read. Its content is not
    checked here: the command model bounds it and the handler checks the question rules.
    """
    if path is None:
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_QUESTIONS_FILE + 1)
    except OSError as exc:
        fail(f"cannot read questions file: {exc.strerror}")
    if len(raw) > MAX_QUESTIONS_FILE:
        fail("questions file is too large")
    try:
        loaded: list[Any] = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        fail("questions file is not valid JSON")
    return loaded


def _checklist(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> dict[str, Any]:
    """The checklist ``key`` names (its envelope row), as ``viewer`` may read it.

    An absent checklist, one in another project and a hidden one all answer
    `error: no checklist <key>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != CHECKLIST:
        fail(f"no checklist {key}")
    return row


def _line(verb: str, key: str, result: CommandResult) -> None:
    """One line: the verb, the key and the version the command left."""
    typer.echo(f"{verb} {key}  version {result.version}")


# --- create, edit --------------------------------------------------------------------------------


def checklist_create(
    ctx: typer.Context,
    project: Project,
    title: Annotated[str, typer.Option("--title", help="The title of the checklist.")],
    discipline: Annotated[str | None, typer.Option("--discipline", help="The discipline.")] = None,
    questions_file: QUESTIONS_FILE = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Create a checklist in Draft, version 1. Prints `created <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        fields = _given(
            title=title,
            discipline=discipline,
            questions=_questions(questions_file),
        )
        return _model(CreateChecklist, actor=who, source=SOURCE, scope=scope, **fields)

    result = _execute(db, who, build)
    _line("created", str(result.key), result)


def checklist_edit(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The checklist key, for example P123-CHK-0001.")],
    project: Project,
    title: Annotated[str | None, typer.Option("--title", help="The title.")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline", help="The discipline.")] = None,
    questions_file: QUESTIONS_FILE = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change fields of a Draft checklist; at least one is needed.

    Prints `edited <key>  version <v>`.
    """
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _checklist(uow, scope, key, viewer)
        fields = _given(
            title=title,
            discipline=discipline,
            questions=_questions(questions_file),
        )
        return _model(
            EditChecklist,
            actor=who,
            source=SOURCE,
            scope=scope,
            checklist=str(row["id"]),
            expected_version=int(row["version"]),
            **fields,
        )

    _line("edited", key, _execute(db, who, build))


# --- state verbs ---------------------------------------------------------------------------------


def _run(
    ctx: typer.Context,
    model: type[Command],
    key: str,
    project: str,
    actor: str,
) -> CommandResult:
    """The one body of the state verbs: read the checklist as the actor, then run the handler."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _checklist(uow, scope, key, viewer)
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            checklist=str(row["id"]),
            expected_version=int(row["version"]),
        )

    return _execute(db, who, build)


def checklist_publish(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The checklist key, for example P123-CHK-0001.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Publish a Draft checklist; its questions must pass the rules.

    Prints `published <key>  version <v>`.
    """
    _line("published", key, _run(ctx, PublishChecklist, key, project, actor))


def checklist_revise(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The checklist key, for example P123-CHK-0001.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Copy a Published checklist as a new Draft. Prints `revised <new key>  version <v>`."""
    result = _run(ctx, ReviseChecklist, key, project, actor)
    _line("revised", str(result.key), result)


def checklist_retire(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The checklist key, for example P123-CHK-0001.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Retire a Draft or Published checklist. Prints `retired <key>  version <v>`."""
    _line("retired", key, _run(ctx, RetireChecklist, key, project, actor))


# --- registration --------------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Add the write verbs to the ``checklist`` group."""
    verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("create", checklist_create),
        ("edit", checklist_edit),
        ("publish", checklist_publish),
        ("revise", checklist_revise),
        ("retire", checklist_retire),
    )
    for name, function in verbs:
        app.command(name)(function)
