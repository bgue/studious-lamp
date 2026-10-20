"""The `tl corr` group: the correspondence register, items, triage and replies (brief 9 M10).

Each subcommand parses options, makes one call into `tl_mod_correspondence` (a handler or a read)
and prints. The rules live in the module: the states, the clocks, who may read an item (ADR-0016:
the CLI reads as the signed-in person, so an item above their clearance is "no item"), and what a
controller alone may do (issue, void a received item, replace an item; ADR-0013). Items are named
by number, for example P123-COR-0001; the project comes from `--project`. The groups
`tl corr clock`, `thread`, `party`, `clause`, `class`, `mail` and `report` are in
`corr_clock.py`, `corr_registry.py` and `corr_report.py`.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_core.uow import UnitOfWork
from tl_mod_correspondence import registry, views
from tl_mod_correspondence.handlers.issue import IssueCorrespondence, handle_issue_correspondence
from tl_mod_correspondence.handlers.items import (
    ReceiveCorrespondence,
    UpdateCorrespondence,
    handle_receive_correspondence,
    handle_update_correspondence,
)
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    DraftCorrespondence,
    RecordResponse,
    VoidCorrespondence,
    VoidDraft,
    handle_close_correspondence,
    handle_draft_correspondence,
    handle_record_response,
    handle_void_correspondence,
    handle_void_draft,
)
from tl_mod_correspondence.handlers.threads import (
    SupersedeCorrespondence,
    handle_supersede_correspondence,
)
from tl_mod_correspondence.handlers.triage import (
    ConfirmTriage,
    ReclassifyCorrespondence,
    handle_confirm_triage,
    handle_reclassify_correspondence,
)

from tl_cli.derive_support import configure_files, file_service
from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.session import require_controller

app = typer.Typer(
    help="The correspondence register: receive, triage, reply, issue, clocks, mail.",
    no_args_is_help=True,
)

_Number = Annotated[str, typer.Argument(help="The item number, for example P123-COR-0001.")]
_CHUNK = 1024 * 1024
_Date = Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD. Default today.")]
_DateReason = Annotated[
    str | None, typer.Option("--date-reason", help="Required for a date before today.")
]


def item_row(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.ItemRow:
    """The item ``number``; exits `error: no item 'X' in project 'P'` (also for one the person
    may not read: the CLI never says which)."""
    found = registry.find_item(uow.conn(), scope, number)
    if found is None:
        _fail(f"no item {number!r} in project {project!r}")
    return found


def recipient(text: str) -> Recipient:
    """``Name``, ``Name:email`` or ``:email`` as a recipient."""
    name, _, email = text.partition(":")
    return Recipient(name=name or None, email=email or None)


def upload(db: DbTarget, scope: str, actor: str, record_id: str, slot: str, path: Path) -> str:
    """Upload ``path`` into the ``slot`` of an item the way a person's upload goes (the item's
    upload guard applies); returns the file id."""
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    service = file_service()
    with _service_errors(), open_uow(db) as uow:
        ticket = service.register_upload(
            uow,
            RegisterUpload(
                actor=actor,
                source="cli",
                scope=scope,
                record_id=record_id,
                slot=slot,
                filename=path.name,
                content_type=media,
                size=path.stat().st_size,
                sha256=digest.hexdigest(),
            ),
        )
        complete = CompleteUpload(
            actor=actor, source="cli", scope=scope, upload_id=ticket.upload_id
        )
        if ticket.exists:
            done = service.complete_upload(uow, complete)
        else:
            with path.open("rb") as source_file:
                done = service.complete_upload(uow, complete, source_file)
    return done.file_id


def _body(body: str | None, body_file: Path | None) -> str | None:
    if body is not None and body_file is not None:
        _fail("give --body or --body-file, not both")
    if body_file is not None:
        return body_file.read_text(encoding="utf-8")
    return body


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Received.")] = None,
    direction: Annotated[
        str | None, typer.Option("--direction", help="in, out or internal.")
    ] = None,
    domain: Annotated[str | None, typer.Option("--domain")] = None,
    subtype: Annotated[str | None, typer.Option("--subtype")] = None,
    awaiting: Annotated[
        bool, typer.Option("--awaiting", help="Items that want an answer.")
    ] = False,
    include_void: Annotated[bool, typer.Option("--all", help="Include void items.")] = False,
    sources: Annotated[
        bool, typer.Option("--sources/--no-sources", help="Add the lines of register sources.")
    ] = True,
) -> None:
    """The master register: number, state, direction, domain/subtype, date, who, subject.

    Transmittals of document control appear as lines of kind `transmittal`.
    """
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        lines = views.register(
            uow.conn(),
            f"project:{project}",
            state=state,
            direction=direction,
            domain=domain,
            subtype=subtype,
            awaiting_response=awaiting,
            include_void=include_void,
            include_sources=sources,
        )
    for line in lines:
        kind = "" if line.kind == "item" else f" [{line.kind}]"
        where = f"{line.domain or '-'}/{line.subtype or '-'}"
        typer.echo(
            f"{line.number} {line.state} {line.direction} {where} {line.on or '-'} "
            f"{line.counterparty or '-'} {line.subject}{kind}"
        )


@app.command("show")
def show(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """One item: its fields, thread, clocks and files."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = item_row(uow, scope, project, number)
        view = views.item_view_by_id(uow.conn(), scope, row.id)
        from sqlalchemy import text

        files = (
            uow.conn()
            .execute(
                text(
                    "SELECT slot, filename, status FROM cur_files WHERE record_id = :r "
                    "ORDER BY slot, filename"
                ),
                {"r": row.id},
            )
            .all()
        )
    typer.echo(f"{view.number} {view.state} {view.direction} {view.medium}")
    typer.echo(f"subject {view.subject}")
    typer.echo(f"class {view.confidentiality}")
    typer.echo(f"domain {view.domain or '-'}/{view.subtype or '-'}")
    typer.echo(f"from {view.from_name or '-'}")
    typer.echo("to " + (", ".join(r.name or r.email or "-" for r in view.to) or "-"))
    typer.echo(
        f"received {view.received_on or '-'} sent {view.sent_on or '-'} "
        f"issued {view.issued_on or '-'}"
    )
    typer.echo(f"thread {view.thread_number or '-'} answers {view.responds_to_number or '-'}")
    typer.echo(
        f"response {'required' if view.response_required else 'not required'}"
        f" due {view.response_due or '-'} answered {view.responded_on or '-'}"
    )
    if view.delivery != "none":
        typer.echo(f"delivery {view.delivery}")
    for clock in view.clocks:
        left = "-" if clock.days_left is None else str(clock.days_left)
        typer.echo(
            f"clock {clock.key} {clock.label} {clock.effective_state} due {clock.due_on} "
            f"left {left} ({clock.day_type})"
        )
    for slot, name, status in files:
        typer.echo(f"file {slot} {name} {status}")
    if view.clearances:
        typer.echo("named " + ", ".join(c.account for c in view.clearances))
    if view.body:
        typer.echo("")
        typer.echo(view.body)


@app.command("receive")
def receive(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject of the item.")],
    file: Annotated[
        Path | None,
        typer.Option("--file", help="The letter as it arrived (stored in the slot original)."),
    ] = None,
    from_name: Annotated[str | None, typer.Option("--from", help="Who sent it.")] = None,
    to: Annotated[
        list[str] | None, typer.Option("--to", help="NAME or NAME:EMAIL. Repeat.")
    ] = None,
    medium: Annotated[
        str, typer.Option("--medium", help="letter, email, portal, minutes, other.")
    ] = "letter",
    external_ref: Annotated[
        str | None, typer.Option("--ref", help="The sender's reference.")
    ] = None,
    sent_on: Annotated[str | None, typer.Option("--sent-on", help="YYYY-MM-DD.")] = None,
    received_on: Annotated[str | None, typer.Option("--received-on", help="Default today.")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", exists=True, dir_okay=False)
    ] = None,
    response_required: Annotated[bool, typer.Option("--response-required")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Log an item that arrived: numbered, Received, internal. Attach the letter with --file."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if file is not None and not file.is_file():
        _fail(f"no such file: {file}")
    if file is not None:
        configure_files()
    with _service_errors(), open_uow(db) as uow:
        made = handle_receive_correspondence(
            uow,
            ReceiveCorrespondence.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "subject": subject,
                    "medium": medium,
                    "external_ref": external_ref,
                    "from_name": from_name,
                    "to": [recipient(t) for t in to or []],
                    "sent_on": sent_on,
                    "received_on": received_on,
                    "body": _body(body, body_file),
                    "response_required": response_required,
                }
            ),
        )
    typer.echo(f"received {made.key}")
    if file is not None:
        upload(db, scope, actor, made.stream_id, "original", file)
        typer.echo(f"file original {file.name}")


@app.command("update")
def update(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    from_name: Annotated[str | None, typer.Option("--from")] = None,
    external_ref: Annotated[str | None, typer.Option("--ref")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    response_required: Annotated[
        bool | None, typer.Option("--response-required/--no-response")
    ] = None,
    response_due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change the fields of a draft or a received item (the ones you name)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    given = {
        k: v
        for k, v in {
            "subject": subject,
            "from_name": from_name,
            "external_ref": external_ref,
            "body": body,
            "response_required": response_required,
            "response_due": response_due,
        }.items()
        if v is not None
    }
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_update_correspondence(
            uow,
            UpdateCorrespondence.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "stream_id": row.id,
                    "reason": reason,
                    **given,
                }
            ),
        )
    typer.echo(f"updated {number}")


@app.command("suggest")
def suggest(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """What the suggestion engine proposes for an item (`tl corr triage` decides)."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.suggestion_for_item(uow.conn(), f"project:{project}", number)
    typer.echo(f"suggested {found.domain or '-'}/{found.subtype or '-'} score {found.score}")
    for why in found.reasons:
        typer.echo(f"  {why}")


@app.command("triage")
def triage(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    domain: Annotated[str | None, typer.Option("--domain")] = None,
    subtype: Annotated[str | None, typer.Option("--subtype")] = None,
    accept: Annotated[
        bool, typer.Option("--accept", help="Confirm the domain and subtype the engine suggests.")
    ] = False,
    refs: Annotated[
        list[str] | None, typer.Option("--ref", help="An item this refers to (number). Repeat.")
    ] = None,
    no_clocks: Annotated[bool, typer.Option("--no-clocks")] = False,
    response_required: Annotated[
        bool | None, typer.Option("--response-required/--no-response")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Confirm the domain and subtype of a received item (a person's act, not an agent's)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if accept == (domain is not None or subtype is not None):
        _fail("give --accept to confirm the suggestion, or --domain and --subtype")
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        if accept:
            found = views.suggestion_for_item(uow.conn(), scope, number)
            domain, subtype = found.domain, found.subtype
        if domain is None or subtype is None:
            _fail("give both --domain and --subtype")
        ids = [item_row(uow, scope, project, n).id for n in refs or []]
        done = handle_confirm_triage(
            uow,
            ConfirmTriage(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                domain=domain,
                subtype=subtype,
                referenced_ids=ids,
                response_required=response_required,
                start_clocks=not no_clocks,
            ),
        )
        clocks = registry.clocks_of(uow.conn(), row.id)
    typer.echo(f"triaged {number} as {domain}/{subtype}")
    for clock in clocks:
        typer.echo(f"clock {clock.key} {clock.label} due {clock.due_on}")
    assert done.events


@app.command("reclassify")
def reclassify(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    domain: Annotated[str, typer.Option("--domain")],
    subtype: Annotated[str, typer.Option("--subtype")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change the domain and subtype of a draft, received or triaged item."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_reclassify_correspondence(
            uow,
            ReclassifyCorrespondence(
                actor=actor, source="cli", scope=scope, stream_id=row.id,
                domain=domain, subtype=subtype, reason=reason,
            ),
        )  # fmt: skip
    typer.echo(f"reclassified {number} as {domain}/{subtype}")


@app.command("draft")
def draft(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject")],
    to: Annotated[list[str], typer.Option("--to", help="NAME or NAME:EMAIL. Repeat.")],
    body: Annotated[str | None, typer.Option("--body")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", exists=True, dir_okay=False)
    ] = None,
    cc: Annotated[list[str] | None, typer.Option("--cc")] = None,
    reply_to: Annotated[
        str | None, typer.Option("--reply-to", help="The number of the item this answers.")
    ] = None,
    domain: Annotated[str | None, typer.Option("--domain")] = None,
    subtype: Annotated[str | None, typer.Option("--subtype")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Start a letter we write: a Draft, optionally an answer to an item."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        parent = item_row(uow, scope, project, reply_to).id if reply_to else None
        made = handle_draft_correspondence(
            uow,
            DraftCorrespondence.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "subject": subject,
                    "body": _body(body, body_file),
                    "to": [recipient(t) for t in to],
                    "cc": [recipient(t) for t in cc or []],
                    "responds_to_id": parent,
                    "domain": domain,
                    "subtype": subtype,
                }
            ),
        )
    typer.echo(f"drafted {made.key}")


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    template: Annotated[
        str | None, typer.Option("--template", help="A letter template code.")
    ] = None,
    issued_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue a draft letter (controller): a PDF is stored, the send is a stub, clocks start."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    configure_files()
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_issue_correspondence(
            uow,
            IssueCorrespondence(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                template=template,
                issued_on=issued_on,
                date_reason=date_reason,
            ),
        )
        after = views.item_view_by_id(uow.conn(), scope, row.id)
    typer.echo(
        f"issued {number} on {after.issued_on} (delivery {after.delivery}: nothing was sent)"
    )
    for clock in after.clocks:
        typer.echo(f"clock {clock.key} {clock.label} due {clock.due_on}")


@app.command("respond")
def respond(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The number of the item that answers it.")],
    answered_on: Annotated[str | None, typer.Option("--date")] = None,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Needed for a date before today.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record that an item has been answered by another item."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        answer = item_row(uow, scope, project, by)
        handle_record_response(
            uow,
            RecordResponse(
                actor=actor, source="cli", scope=scope, stream_id=row.id,
                response_id=answer.id, responded_on=answered_on, reason=reason,
            ),
        )  # fmt: skip
    typer.echo(f"{number} answered by {by}")


@app.command("close")
def close(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Needed if it wanted an answer.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close an item that needs no more work; its open clocks are cancelled."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        handle_close_correspondence(
            uow,
            CloseCorrespondence(
                actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason
            ),
        )
    typer.echo(f"closed {number}")


@app.command("void")
def void(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void an item made in error. A draft is anyone's; a received item is a controller's."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = item_row(uow, scope, project, number)
    if row.state != "Draft":
        require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        if row.state == "Draft":
            handle_void_draft(
                uow,
                VoidDraft(actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason),
            )
        else:
            handle_void_correspondence(
                uow,
                VoidCorrespondence(
                    actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason
                ),
            )
    typer.echo(f"voided {number}")


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The number of the item that replaces it.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace an item by another (controller). The old item stays, marked superseded."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        old = item_row(uow, scope, project, number)
        new = item_row(uow, scope, project, by)
        handle_supersede_correspondence(
            uow,
            SupersedeCorrespondence(
                actor=actor, source="cli", scope=scope, stream_id=old.id,
                superseded_by_id=new.id, reason=reason,
            ),
        )  # fmt: skip
    typer.echo(f"{number} superseded by {by}")


@app.command("domains")
def domains(project: _Project) -> None:
    """The correspondence domains in force for a project: subtypes, clocks and templates."""
    for domain in views.domain_views(f"project:{project}"):
        typer.echo(
            f"{domain.code} {domain.semver} default {domain.default_subtype} "
            f"class {domain.confidentiality_default} {domain.name}"
        )
        for subtype in domain.subtypes:
            typer.echo(f"  {subtype.code} {subtype.label}")
