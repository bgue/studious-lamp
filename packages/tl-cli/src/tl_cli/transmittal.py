"""The `tl transmittal` group: draft, issue, answer, close and void transmittals (brief 9 M1).

A transmittal is one formal exchange of issued revisions with other parties. Each subcommand parses
options, makes one call into `tl_mod_documents` (a handler or a read) and prints. The rules (only
issued revisions, the number pattern, the dates, which state allows what) live in the module.
Transmittals are named by number; revisions as `NUMBER@CODE` (`ISO-1234@B`); the project comes from
`--project`. Issuing a transmittal is a controller's act (ADR-0013).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry, views
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    RecordTransmittalResponse,
    VoidTransmittal,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
    handle_void_transmittal,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.session import require_controller

app = typer.Typer(help="Draft, issue, answer, close and void transmittals.", no_args_is_help=True)

_Number = Annotated[str, typer.Argument(help="The transmittal number, for example P123-TRN-0001.")]
_Date = Annotated[
    str | None, typer.Option("--date", help="YYYY-MM-DD. Default today; never later.")
]
_DateReason = Annotated[
    str | None, typer.Option("--date-reason", help="Required for a date before today.")
]


def _transmittal(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.TransmittalRow:
    """The transmittal ``number``; exits `error: no transmittal 'X' in project 'P'`."""
    found = registry.find_transmittal(uow.conn(), scope, number)
    if found is None:
        _fail(f"no transmittal {number!r} in project {project!r}")
    return found


def _recipient(text: str) -> Recipient:
    """``Name``, ``Name:Organisation`` or ``Name:Organisation:email`` as a recipient."""
    name, organisation, email = ([*text.split(":", 2), None, None])[:3]
    return Recipient(name=name, organisation=organisation or None, email=email or None)


def _revision_ids(uow: UnitOfWork, scope: str, project: str, items: list[str]) -> list[str]:
    """The revision ids of `NUMBER@CODE` items; exits `error: ...` for a bad item."""
    ids: list[str] = []
    for item in items:
        number, at, code = item.rpartition("@")
        if not at or not number or not code:
            _fail(f"revision {item!r} must be written NUMBER@CODE, for example ISO-1234@B")
        doc = _document(uow, scope, project, number)
        rev = registry.find_revision(uow.conn(), doc.id, code)
        if rev is None:
            _fail(f"no revision {code!r} of {number}")
        ids.append(rev.id)
    return ids


@app.command("create")
def create(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject", help="The transmittal title.")],
    purpose: Annotated[
        str,
        typer.Option(
            "--purpose",
            help="for_review, for_information, for_approval, for_construction, as_built "
            "or for_record.",
        ),
    ],
    to: Annotated[
        list[str],
        typer.Option(
            "--to", help="A recipient: NAME, NAME:ORGANISATION or NAME:ORGANISATION:EMAIL."
        ),
    ],
    revisions: Annotated[
        list[str], typer.Option("--revision", help="An issued revision, NUMBER@CODE. Repeat it.")
    ],
    number: Annotated[
        str | None, typer.Option("--number", help="Default: allocated by the pattern.")
    ] = None,
    direction: Annotated[
        str, typer.Option("--direction", help="outgoing or incoming.")
    ] = "outgoing",
    due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Draft a transmittal of issued revisions to named recipients."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        ids = _revision_ids(uow, scope, project, revisions)
        made = handle_create_transmittal(
            uow,
            CreateTransmittal.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "number": number,
                    "subject": subject,
                    "direction": direction,
                    "purpose": purpose,
                    "due_date": due,
                    "recipients": [_recipient(t) for t in to],
                    "revision_ids": ids,
                    "notes": notes,
                }
            ),
        )
    typer.echo(f"created transmittal {made.key}")
    typer.echo(f"items {len(ids)}")


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    issued_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue a draft transmittal (controller): it is now the record of what was sent."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        row = _transmittal(uow, scope, project, number)
        handle_issue_transmittal(
            uow,
            IssueTransmittal(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                issued_on=issued_on,
                date_reason=date_reason,
            ),
        )
        after = _transmittal(uow, scope, project, number)
    typer.echo(f"issued {number} on {after.issued_on}")


@app.command("answer")
def answer(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    code: Annotated[
        str,
        typer.Option("--code", help="approved, approved_with_comments, rejected or noted."),
    ],
    note: Annotated[str | None, typer.Option("--note")] = None,
    responded_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record the recipients' answer to an issued transmittal."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _transmittal(uow, scope, project, number)
        handle_record_transmittal_response(
            uow,
            RecordTransmittalResponse.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "stream_id": row.id,
                    "response_code": code,
                    "response_note": note,
                    "responded_on": responded_on,
                    "date_reason": date_reason,
                }
            ),
        )
    typer.echo(f"answered {number}: {code}")


@app.command("close")
def close(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close an issued or answered transmittal."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _transmittal(uow, scope, project, number)
        handle_close_transmittal(
            uow,
            CloseTransmittal(
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
    """Void a draft transmittal drafted in error. An issued one is closed, not voided."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _transmittal(uow, scope, project, number)
        handle_void_transmittal(
            uow,
            VoidTransmittal(
                actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason
            ),
        )
    typer.echo(f"voided {number}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    direction: Annotated[str | None, typer.Option("--direction")] = None,
) -> None:
    """List a project's transmittals by number: number, state, direction, purpose, items, title."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rows = registry.list_transmittals(
            uow.conn(), f"project:{project}", state=state, direction=direction
        )
    for row in rows:
        fields = [
            row.number,
            "Void" if row.voided else row.state,
            row.direction,
            row.purpose,
            f"items={row.item_count}",
            row.title,
        ]
        typer.echo("  ".join(fields))


@app.command("show")
def show(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """Show a transmittal: its fields, its recipients and its items."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        view = views.transmittal_view(uow.conn(), f"project:{project}", number)
    fields = [
        ("number", view.number),
        ("title", view.title),
        ("state", view.state),
        ("direction", view.direction),
        ("purpose", view.purpose),
        ("issued", view.issued_on),
        ("due", view.due_date),
        ("response", view.response_code),
        ("responded", view.responded_on),
    ]
    for name, value in fields:
        typer.echo(f"{name}: {value or '-'}")
    for recipient in view.recipients:
        line = f"recipient {recipient['name']}"
        if recipient.get("organisation"):
            line += f", {recipient['organisation']}"
        if recipient.get("email"):
            line += f" <{recipient['email']}>"
        typer.echo(line)
    for item in view.items:
        typer.echo(f"item {item.document_number}@{item.revision_code} {item.issue_status or '-'}")
