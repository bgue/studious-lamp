"""``tl intake``: the signed-in controller's side of public intake (V3-F4; I01, I04).

The hook ref ``tl_mod_forms.intake_cli:intake_app`` names the group ``intake``. Verbs:
``code issue``, ``code revoke``, ``code ls`` and ``ls``, ``show``, ``accept``, ``reject``,
``purge``. There is no public route here; the public ``/i/<code>`` page is S6's.

The code is made here by ``new_code()``, and only ``code_hash(code)`` goes into the command: the
server never sees the code. ``issue`` prints it once, after the unit of work has committed, and it
is never stored, logged, put in an error text or taken as an option (there is no ``--code``).
Reads (``ls``, ``show``, ``code ls``) are the module's views as the signed-in viewer after
``forms.intake.review`` (items) or ``forms.intake.issue`` (codes); writes run the module's commands
as the actor, who needs the command's own word. An item that is missing, hidden, of another project
or purged prints the one `error: no such intake item`. Nothing prints a hash, a salt, a code or a
stored body; ``show`` prints the answers of a Pending item, and no other verb prints an answer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command, session_viewer
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.confidentiality import Viewer
from tl_core.qr.codes import code_hash, grouped, new_code
from tl_core.services.commands import Command

from tl_mod_forms import intake, intake_read, intake_views, views
from tl_mod_forms.commands import (
    AcceptIntakeItem,
    IssueIntakeCode,
    RejectIntakeItem,
    RevokeIntakeCode,
)
from tl_mod_forms.handlers.intake import (
    handle_accept_intake_item,
    handle_issue_intake_code,
    handle_reject_intake_item,
    handle_revoke_intake_code,
)
from tl_mod_forms.names import INTAKE_CODE_STATES, INTAKE_ITEM_STATES

intake_app = typer.Typer(no_args_is_help=True, help="Public intake: codes and the queue.")
code_app = typer.Typer(no_args_is_help=True, help="Issue, revoke and list intake codes.")
intake_app.add_typer(code_app, name="code")

LIST_LIMIT = 200
MSG_NO_TEMPLATE = "no template"
REASONS = ("spam", "duplicate", "not_ours", "unclear")
CODE_STATE = Annotated[str | None, typer.Option("--state", help="Only this state.")]


def _model[C: Command](model: type[C], **fields: Any) -> C:
    """The command model with ``fields``; a value the model refuses is a usage error (exit 2)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc.errors()[0]["msg"])) from None


def _read(db: DbTarget, actor: str, scope: str, word: str, call: Any) -> Any:
    """Run ``call(conn, viewer)`` read-only as the signed-in viewer, after the access word."""
    who = acting(db, actor)
    viewer = session_viewer(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        try:
            if word == "issue":
                intake_read.require_issue(uow.conn(), who, scope)
            else:
                intake_read.require_review(uow.conn(), who, scope)
        except ForbiddenError as exc:
            fail(f"forbidden: {exc}")
        return call(uow.conn(), viewer)


def _run(db: DbTarget, actor: str, scope: str, build: Any, handler: Any) -> Any:
    """Build one command as the actor (``build(conn, viewer, who)``), check its word, run it."""
    who = acting(db, actor)
    with service_errors(), open_uow(db) as uow:
        conn = uow.conn()
        viewer = cf.viewer_for_actor(conn, who)
        with cf.use_viewer(viewer):
            cmd = build(conn, viewer, who)
            require_command(uow, cmd)
            return handler(uow, cmd)


# --- codes ------------------------------------------------------------------------------------


def _template_id(conn: Connection, ref: str, viewer: Viewer) -> str:
    rows = views.template_list(conn, limit=views.MAX_LIMIT, viewer=viewer).rows
    found = next((r for r in rows if ref in (r.key, r.id)), None)
    if found is None:
        fail(MSG_NO_TEMPLATE)
    return found.id


def _context_id(conn: Connection, scope: str, key: str, viewer: Viewer) -> str:
    visible, extra = cf.not_hidden_each("r.id", viewer)
    row = conn.execute(
        text(
            "SELECT r.id FROM cur_core_record r WHERE r.scope = :scope AND r.key = :key "
            f"AND r.voided = :no AND {visible}"
        ),
        {"scope": scope, "key": key, "no": False, **extra},
    ).first()
    if row is None:
        fail("no record")
    return str(row.id)


@code_app.command("issue")
def code_issue(
    ctx: typer.Context,
    project: Project,
    template: Annotated[str, typer.Option("--template", help="A published public template.")],
    heading: Annotated[str, typer.Option("--heading", help="What the code is for.")],
    controller_role: Annotated[
        str, typer.Option("--controller-role", help="Who reviews what comes in.")
    ],
    expires_on: Annotated[str, typer.Option("--expires-on", help="YYYY-MM-DD.")],
    context: Annotated[
        str | None, typer.Option("--context", help="The key of a record the code is about.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Issue a code. Prints `issued <id>  expires <date>` and the code, once: it cannot be shown
    again. The code is made here and the server is sent its hash only."""
    scope = scope_of(project)
    made = new_code()
    digest = code_hash(made)

    def build(conn: Connection, viewer: Viewer, who: str) -> Command:
        return _model(
            IssueIntakeCode,
            actor=who,
            source=SOURCE,
            scope=scope,
            code_hash=digest,
            template_id=_template_id(conn, template, viewer),
            context_id=None if context is None else _context_id(conn, scope, context, viewer),
            heading=heading,
            controller_role=controller_role,
            expires_on=expires_on,
        )

    result = _run(ctx.obj, actor, scope, build, handle_issue_intake_code)
    typer.echo(f"issued {result.stream_id}  expires {expires_on}")
    typer.echo(f"code {grouped(made)}")
    typer.echo("this code is shown once and cannot be recovered", err=True)


@code_app.command("revoke")
def code_revoke(
    ctx: typer.Context,
    code_id: Annotated[str, typer.Argument(help="The code's id (`tl intake code ls`).")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is revoked.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Revoke an Active code. A revoked code opens nothing."""
    scope = scope_of(project)

    def build(_conn: Connection, _viewer: Viewer, who: str) -> Command:
        return _model(
            RevokeIntakeCode, actor=who, source=SOURCE, scope=scope, code_id=code_id, reason=reason
        )

    _run(ctx.obj, actor, scope, build, handle_revoke_intake_code)
    typer.echo(f"revoked {code_id}")


@code_app.command("ls")
def code_ls(
    ctx: typer.Context,
    project: Project,
    state: CODE_STATE = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = LIST_LIMIT,
    actor: Actor = DEV_ACTOR,
) -> None:
    """List the codes: `<id>  <state>  pending <n>  expires <date>  <heading>  <role>`. No code
    and no hash is ever shown."""
    scope = scope_of(project)
    if state is not None and state not in INTAKE_CODE_STATES:
        raise typer.BadParameter(
            f"must be one of {', '.join(INTAKE_CODE_STATES)}", param_hint="'--state'"
        )

    def listed(conn: Connection, viewer: Viewer) -> intake_views.Page[intake_views.CodeRow]:
        return intake_views.code_list(conn, scope, state=state, limit=limit, viewer=viewer)

    page = _read(ctx.obj, actor, scope, "issue", listed)
    typer.echo(f"intake codes: {page.total}")
    for c in page.rows:
        typer.echo(
            f"{c.id}  {c.state}  pending {c.pending}  expires {cell(c.expires_on, 10)}  "
            f"{cell(c.heading, 40)}  {cell(c.controller_role, 20)}"
        )


# --- items ------------------------------------------------------------------------------------


@intake_app.command("ls")
def item_ls(
    ctx: typer.Context,
    project: Project,
    state: CODE_STATE = None,
    code: Annotated[str | None, typer.Option("--code-id", help="Only this code's items.")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = LIST_LIMIT,
    actor: Actor = DEV_ACTOR,
) -> None:
    """List the items, oldest first: `<id>  <state>  <received>  code <id>  <outcome>`. A hidden
    item is not listed. No answer is shown here; `tl intake show` opens one."""
    scope = scope_of(project)
    if state is not None and state not in INTAKE_ITEM_STATES:
        raise typer.BadParameter(
            f"must be one of {', '.join(INTAKE_ITEM_STATES)}", param_hint="'--state'"
        )

    def listed(conn: Connection, viewer: Viewer) -> intake_views.Page[intake_views.ItemRow]:
        return intake_views.item_list(
            conn, scope, state=state, code_id=code, limit=limit, viewer=viewer
        )

    page = _read(ctx.obj, actor, scope, "review", listed)
    typer.echo(f"intake items: {page.total}")
    for i in page.rows:
        outcome = i.accepted_as or i.rejected_reason
        typer.echo(
            f"{i.id}  {i.state}  {cell(i.received_at, 25)}  code {i.code_id}  {cell(outcome, 30)}"
        )


@intake_app.command("show")
def item_show(
    ctx: typer.Context,
    item_id: Annotated[str, typer.Argument(help="The item's id (`tl intake ls`).")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Open an item. A Pending one also prints the sender's answers, one per line."""
    scope = scope_of(project)

    def one(conn: Connection, viewer: Viewer) -> intake_read.ItemDetail | None:
        return intake_read.item_detail(conn, scope, item_id, viewer)

    found = _read(ctx.obj, actor, scope, "review", one)
    if found is None:
        fail(intake_read.MSG_ITEM)
    row = found.row
    typer.echo(f"item {row.id}  {row.state}")
    typer.echo(f"code {row.code_id}  received {row.received_at}  bytes {row.body_bytes}")
    if row.accepted_as:
        typer.echo(f"accepted as {row.accepted_as} by {cell(row.accepted_by)} on {row.accepted_on}")
        typer.echo(f"claim {cell(row.claim_name)}  {cell(row.claim_company)}")
    if row.rejected_reason:
        typer.echo(f"rejected {row.rejected_reason} by {cell(row.rejected_by)}")
    if row.purged_at:
        typer.echo(f"purged {row.purged_at}")
    if found.answers is not None:
        typer.echo("answers")
        for a in found.answers:
            typer.echo(f"  {cell(a.get('q'), 30)}  {cell(a.get('value'), 200)}")


@intake_app.command("accept")
def item_accept(
    ctx: typer.Context,
    item_id: Annotated[str, typer.Argument(help="A Pending item's id.")],
    project: Project,
    command: Annotated[
        str, typer.Option("--as", help="The command the item becomes (the template's accepts_as).")
    ],
    args_file: Annotated[
        Path, typer.Option("--args-file", help="A JSON object: that command's arguments.")
    ],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Accept a Pending item as the record the template proposes: your completed command runs as
    you (you need its access word), then the item is Accepted and its body is removed. A refusal
    leaves the item Pending."""
    scope = scope_of(project)
    try:
        loaded: object = json.loads(args_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise typer.BadParameter("not a readable JSON file", param_hint="'--args-file'") from None
    if not isinstance(loaded, dict):
        raise typer.BadParameter("must be a JSON object", param_hint="'--args-file'")
    args: dict[str, Any] = {str(k): v for k, v in loaded.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]

    def build(_conn: Connection, _viewer: Viewer, who: str) -> Command:
        return _model(
            AcceptIntakeItem,
            actor=who,
            source=SOURCE,
            scope=scope,
            item_id=item_id,
            command_type=command,
            command_args=args,
        )

    _run(ctx.obj, actor, scope, build, handle_accept_intake_item)
    typer.echo(f"accepted {item_id} as {command}")


@intake_app.command("reject")
def item_reject(
    ctx: typer.Context,
    item_id: Annotated[str, typer.Argument(help="A Pending item's id.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help=f"One of {', '.join(REASONS)}.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Reject a Pending item. Its body is kept until `tl intake purge` finds it due."""
    scope = scope_of(project)
    if reason not in REASONS:
        raise typer.BadParameter(f"must be one of {', '.join(REASONS)}", param_hint="'--reason'")

    def build(_conn: Connection, _viewer: Viewer, who: str) -> Command:
        return _model(
            RejectIntakeItem, actor=who, source=SOURCE, scope=scope, item_id=item_id, reason=reason
        )

    _run(ctx.obj, actor, scope, build, handle_reject_intake_item)
    typer.echo(f"rejected {item_id}")


@intake_app.command("purge")
def item_purge(
    ctx: typer.Context,
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Remove the stored text of every item of the project received longer ago than the retention
    window (`forms.intake.retention_days`). Run it daily; a second run finds nothing. Prints
    `purged <n>`; an item you may not read is left alone."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    who = acting(db, actor)
    with service_errors(), open_uow(db) as uow:
        try:
            intake_read.require_review(uow.conn(), who, scope)
        except ForbiddenError as exc:
            fail(f"forbidden: {exc}")
        done = intake.purge_due(
            uow,
            datetime.now(UTC),
            actor=who,
            source=SOURCE,
            scope=scope,
            viewer=cf.viewer_for_actor(uow.conn(), who),
        )
    typer.echo(f"purged {done}")


__all__ = ["code_app", "intake_app"]
