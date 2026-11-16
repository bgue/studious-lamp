"""`tl insp` write verbs: plan, schedule, record, verify, reinspect, cancel (P2-INSP-T04).

Each verb builds one command model of ``tl_mod_quality.commands``, gates it with ``require_command``
and runs the handler that ``INSP_COMMANDS`` names, on one unit of work. An inspection is named by
the key a read prints and resolved to its record id with ``get_record``, as the actor's viewer
reads it (a hidden inspection answers as one that does not exist). The subject, the work package
and the checklist of a verb resolve the same way. The CLI parses options and prints one line; the
handlers decide.
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
from tl_mod_quality import insp_views
from tl_mod_quality.commands import (
    CancelInspection,
    PlanInspection,
    RecordInspectionResult,
    ReinspectInspection,
    ScheduleInspection,
    VerifyInspection,
)
from tl_mod_quality.module import INSP_COMMANDS
from tl_mod_quality.names import CHECKLIST, INSPECTION, POINTS

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

#: The most bytes an ``--answers-file`` may hold.
ANSWERS_FILE_LIMIT = 256 * 1024
POINT_HELP = "The point: hold, witness, review or surveillance."


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


def _line(verb: str, key: str, result: CommandResult) -> None:
    typer.echo(f"{verb} {key}  version {result.version}")


def _point(value: str | None) -> None:
    if value is not None and value not in POINTS:
        raise typer.BadParameter(f"must be one of {', '.join(POINTS)}", param_hint="'--point'")


def _record(
    uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer, record_type: str | None = None
) -> str:
    """The id of the record ``key`` names, as ``viewer`` may read it (a subject, a package, a
    checklist). A hidden or absent record, or one of another type, is `error: no record <KEY>`."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or (record_type is not None and row.get("type") != record_type):
        fail(f"no record {key}")
    return str(row["id"])


def _inspection(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> dict[str, Any]:
    """The inspection ``key`` names (its envelope row), as ``viewer`` may read it.

    An absent inspection, one in another project and a hidden one all answer
    `error: no inspection <key>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != INSPECTION:
        fail(f"no inspection {key}")
    return row


def _answers_from(answers: list[str] | None, answers_file: str | None) -> list[dict[str, Any]]:
    """The answers of ``--answer Q=VALUE`` (repeated) or of ``--answers-file`` (a JSON list)."""
    if answers and answers_file is not None:
        raise typer.BadParameter("give --answer or --answers-file, not both")
    if answers_file is not None:
        try:
            with Path(answers_file).open("rb") as handle:
                raw = handle.read(ANSWERS_FILE_LIMIT + 1)
        except OSError:
            raise typer.BadParameter("cannot read the answers file") from None
        if len(raw) > ANSWERS_FILE_LIMIT:
            fail("answers file is too large")
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise typer.BadParameter("the answers file is not JSON") from None
        if not isinstance(parsed, list):
            raise typer.BadParameter("the answers file must hold a JSON list")
        return parsed
    result: list[dict[str, Any]] = []
    for item in answers or []:
        question, sep, value = item.partition("=")
        if not sep or not question:
            raise typer.BadParameter("an answer is Q=VALUE, for example q1=yes")
        result.append({"q": question, "value": _value(value)})
    return result


def _value(text: str) -> Any:
    """A number when the text is one (a number question), else the text (yes, no, n/a)."""
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            continue
    return text


def _run(
    ctx: typer.Context,
    model: type[Command],
    key: str,
    project: str,
    actor: str,
    expected_version: int | None,
    extra: Callable[[UnitOfWork, str, cf.Viewer], dict[str, Any]] | None = None,
    **fields: Any,
) -> CommandResult:
    """The one body of the verbs on an existing inspection: run ``model``, return the result."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _inspection(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        more = {} if extra is None else extra(uow, scope, viewer)
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            inspection=str(row["id"]),
            expected_version=version,
            **more,
            **fields,
        )

    return _execute(db, who, build)


_EXPECTED = typer.Option(
    "--expected-version", min=1, help="The version the change is made on (default: the one read)."
)
_KEY = typer.Argument(help="The inspection key, for example P123-INS-0001.")


# --- plan -----------------------------------------------------------------------------------------


def insp_plan(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The key of the record inspected.")],
    title: Annotated[str, typer.Option("--title", help="The title of the inspection.")],
    point: Annotated[str, typer.Option("--point", help=POINT_HELP)],
    for_key: Annotated[
        str | None, typer.Option("--for", help="The key of the work package it is for.")
    ] = None,
    area: Annotated[str | None, typer.Option("--area", help="The area.")] = None,
    planned_on: Annotated[
        str | None, typer.Option("--planned-on", help="The planned date, YYYY-MM-DD.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Plan an inspection; the actor is the planner. Prints `planned <key>  version <v>`."""
    _point(point)
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        fields = _given(title=title, point=point, area=area, planned_on=planned_on)
        if for_key is not None:
            fields["for_iwp_id"] = _record(uow, scope, for_key, viewer)
        return _model(
            PlanInspection,
            actor=who,
            source=SOURCE,
            scope=scope,
            subject_id=_record(uow, scope, subject, viewer),
            **fields,
        )

    result = _execute(db, who, build)
    _line("planned", str(result.key), result)


# --- schedule, record, verify, reinspect, cancel --------------------------------------------------


def insp_schedule(
    ctx: typer.Context,
    key: Annotated[str, _KEY],
    project: Project,
    checklist: Annotated[
        str, typer.Option("--checklist", help="The key of the published checklist.")
    ],
    on: Annotated[str, typer.Option("--on", help="The scheduled date, YYYY-MM-DD.")],
    inspector: Annotated[str, typer.Option("--inspector", help="The inspector, user:X.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Schedule a planned inspection against a published checklist.

    Prints `scheduled <key>  version <v>`.
    """

    def pick(uow: UnitOfWork, scope: str, viewer: cf.Viewer) -> dict[str, Any]:
        return {"checklist": _record(uow, scope, checklist, viewer, CHECKLIST)}

    result = _run(
        ctx,
        ScheduleInspection,
        key,
        project,
        actor,
        expected_version,
        extra=pick,
        scheduled_for=on,
        inspector=inspector,
    )
    _line("scheduled", key, result)


def insp_record(
    ctx: typer.Context,
    key: Annotated[str, _KEY],
    project: Project,
    answer: Annotated[
        list[str] | None,
        typer.Option("--answer", help="A question and its value, Q=VALUE; repeat for each."),
    ] = None,
    answers_file: Annotated[
        str | None,
        typer.Option("--answers-file", help="A JSON list of answers (at most 256 KiB)."),
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="A note on the result.")] = None,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Record the result of a scheduled inspection.

    Prints `recorded <key>  version <v>`, then `result <accept|reject|conditional>` and
    `punch <n>` (the punch items the result raised).
    """
    answers = _answers_from(answer, answers_file)
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _inspection(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        return _model(
            RecordInspectionResult,
            actor=who,
            source=SOURCE,
            scope=scope,
            inspection=str(row["id"]),
            expected_version=version,
            answers=answers,
            **_given(note=note),
        )

    result = _execute(db, who, build)
    _line("recorded", key, result)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = insp_views.inspection_detail(
            uow.conn(), scope, key, viewer=cf.viewer_for_actor(uow.conn(), who)
        )
    if found is not None:
        typer.echo(f"result {found.row.result}")
        typer.echo(f"punch {found.row.punch_count}")


def insp_verify(
    ctx: typer.Context,
    key: Annotated[str, _KEY],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Verify a done inspection, by someone who did not record it.

    Prints `verified <key>  version <v>`.
    """
    result = _run(ctx, VerifyInspection, key, project, actor, expected_version)
    _line("verified", key, result)


def insp_reinspect(
    ctx: typer.Context,
    key: Annotated[str, _KEY],
    project: Project,
    planned_on: Annotated[
        str | None, typer.Option("--planned-on", help="The planned date, YYYY-MM-DD.")
    ] = None,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Plan a new inspection that repeats a rejected or conditional one.

    Prints `reinspected <new key>  version <v>`; the old inspection is untouched.
    """
    result = _run(
        ctx,
        ReinspectInspection,
        key,
        project,
        actor,
        expected_version,
        **_given(planned_on=planned_on),
    )
    _line("reinspected", str(result.key or key), result)


def insp_cancel(
    ctx: typer.Context,
    key: Annotated[str, _KEY],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is cancelled.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Cancel a planned or scheduled inspection. Prints `cancelled <key>  version <v>`."""
    result = _run(ctx, CancelInspection, key, project, actor, expected_version, reason=reason)
    _line("cancelled", key, result)


# --- registration ---------------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Add the write verbs to the ``insp`` group."""
    verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("plan", insp_plan),
        ("schedule", insp_schedule),
        ("record", insp_record),
        ("verify", insp_verify),
        ("reinspect", insp_reinspect),
        ("cancel", insp_cancel),
    )
    for name, function in verbs:
        app.command(name)(function)
