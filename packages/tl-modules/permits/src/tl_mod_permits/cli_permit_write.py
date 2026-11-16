"""`tl permit` write verbs: request, approve, reject, issue, revalidate, suspend, resume, handback,
close, cancel (P2-PTW-T04).

Each verb builds one command model of ``tl_mod_permits.commands``, gates it with ``require_command``
and runs the handler that ``COMMANDS`` names for it, on one unit of work. A permit is named by the
key a read prints and resolved to its record id with ``get_record``, as the actor's viewer reads it
(a hidden permit answers as one that does not exist). ``--for`` resolves the same way. The CLI
parses options and prints one line; the handlers decide.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_cli.awp_write import _line
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
from tl_core import confidentiality as cf
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork

from tl_mod_permits.cli import permit_app
from tl_mod_permits.commands import (
    ApprovePermit,
    CancelPermit,
    ClosePermit,
    HandBackPermit,
    IssuePermit,
    RejectPermit,
    RequestPermit,
    ResumePermit,
    RevalidatePermit,
    SuspendPermit,
)
from tl_mod_permits.module import COMMANDS
from tl_mod_permits.names import PERMIT

_EXPECTED = typer.Option(
    "--expected-version", min=1, help="The version the change is made on (default: the one read)."
)
_KEY_HELP = "The permit key a read prints, for example P123-PTW-0001."


def _handler(model: type[Command]) -> Callable[[UnitOfWork, Any], CommandResult]:
    """The handler ``COMMANDS`` names for this command model."""
    return next(c.handler for c in COMMANDS if c.model is model)


def _execute(db: DbTarget, who: str, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    """Build the command on the ledger, gate it with the module role, run its handler; one write.

    The build, the gate and the handler read as ``who``, the acting person, as ``cli_isolation``
    does. The process's own viewer on a dev ledger is the file's owner, who reads restricted
    records, so a refusal that names a record would name one ``who`` cannot see.
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


def _for_id(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> str:
    """The id of the record ``key`` names, as ``viewer`` may read it (``--for``)."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return str(row["id"])


def _permit(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> dict[str, Any]:
    """The permit ``key`` names (its envelope row), as ``viewer`` may read it.

    An absent permit, one in another project, a hidden one and a record of another type all answer
    `error: no permit <key>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != PERMIT:
        fail(f"no permit {key}")
    return row


# --- request --------------------------------------------------------------------------------------


@permit_app.command("request")
def permit_request(
    ctx: typer.Context,
    project: Project,
    permit_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="hot_work, confined_space, work_at_height, excavation, isolation or general.",
        ),
    ],
    area: Annotated[str, typer.Option("--area", help="The area.")],
    location: Annotated[str, typer.Option("--location", help="Where the work is.")],
    description: Annotated[str, typer.Option("--description", help="The work to be done.")],
    holder: Annotated[str, typer.Option("--holder", help="Who holds the permit.")],
    needed_from: Annotated[str, typer.Option("--from", help="First day, YYYY-MM-DD.")],
    needed_until: Annotated[str, typer.Option("--until", help="Last day, YYYY-MM-DD.")],
    for_key: Annotated[
        str | None, typer.Option("--for", help="The key of the record the work belongs to.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Request a permit; the actor is the requester. Prints `requested <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        fields: dict[str, Any] = {
            "permit_type": permit_type,
            "area": area,
            "location_text": location,
            "work_description": description,
            "holder": holder,
            "needed_from": needed_from,
            "needed_until": needed_until,
        }
        if for_key is not None:
            viewer = cf.viewer_for_actor(uow.conn(), who)
            fields["for_record_id"] = _for_id(uow, scope, for_key, viewer)
        return _model(RequestPermit, actor=who, source=SOURCE, scope=scope, **fields)

    result = _execute(db, who, build)
    _line("requested", str(result.key), result)


# --- the state verbs ------------------------------------------------------------------------------


def _run(
    ctx: typer.Context,
    verb: str,
    model: type[Command],
    key: str,
    project: str,
    actor: str,
    expected_version: int | None,
    **fields: Any,
) -> None:
    """The one body of the state verbs: the database target comes from the root context."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _permit(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            permit=str(row["id"]),
            expected_version=version,
            **fields,
        )

    _line(verb, key, _execute(db, who, build))


@permit_app.command("approve")
def permit_approve(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Approve a requested permit, by a controller who did not request it.

    Prints `approved <key>  version <v>`.
    """
    _run(ctx, "approved", ApprovePermit, key, project, actor, expected_version)


@permit_app.command("reject")
def permit_reject(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is rejected.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Reject a requested permit, with a reason. Prints `rejected <key>  version <v>`."""
    _run(ctx, "rejected", RejectPermit, key, project, actor, expected_version, reason=reason)


@permit_app.command("issue")
def permit_issue(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    ticks: Annotated[
        list[str] | None,
        typer.Option("--tick", help="A precaution id of the type's list; repeat for each."),
    ] = None,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Issue an approved permit; the ticked precautions are its checks.

    Prints `issued <key>  version <v>`.
    """
    _run(
        ctx,
        "issued",
        IssuePermit,
        key,
        project,
        actor,
        expected_version,
        precautions=list(ticks or []),
    )


@permit_app.command("revalidate")
def permit_revalidate(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Move an active or lapsed permit's end to the end of the next shift.

    Prints `revalidated <key>  version <v>`.
    """
    _run(ctx, "revalidated", RevalidatePermit, key, project, actor, expected_version)


@permit_app.command("suspend")
def permit_suspend(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why work stops.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Suspend an active or lapsed permit (stop work). Prints `suspended <key>  version <v>`."""
    _run(ctx, "suspended", SuspendPermit, key, project, actor, expected_version, reason=reason)


@permit_app.command("resume")
def permit_resume(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Resume a suspended permit; the issue guards run again.

    Prints `resumed <key>  version <v>`.
    """
    _run(ctx, "resumed", ResumePermit, key, project, actor, expected_version)


@permit_app.command("handback")
def permit_handback(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    note: Annotated[str, typer.Option("--note", help="The note that the site is safe.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Hand back a permit with the note that the site is safe.

    Prints `handed back <key>  version <v>`.
    """
    _run(
        ctx,
        "handed back",
        HandBackPermit,
        key,
        project,
        actor,
        expected_version,
        handback_note=note,
    )


@permit_app.command("close")
def permit_close(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Close a handed-back permit. Prints `closed <key>  version <v>`."""
    _run(ctx, "closed", ClosePermit, key, project, actor, expected_version)


@permit_app.command("cancel")
def permit_cancel(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is cancelled.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Cancel a requested or approved permit, with a reason.

    Prints `cancelled <key>  version <v>`.
    """
    _run(ctx, "cancelled", CancelPermit, key, project, actor, expected_version, reason=reason)
