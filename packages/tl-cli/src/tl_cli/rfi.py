"""The `tl rfi` group: RFIs, technical queries and deviation requests (brief 9 M10).

Each subcommand parses options, makes one call into `tl_mod_correspondence` (a handler or a read)
and prints. The rules live in the module: the workflow (Draft, Internal review, Issued, Awaiting
response, Answered, Accepted or Rejected, Closed), the clocks, and who may read an item (ADR-0016:
the CLI reads as the signed-in person). The raiser's side is open to any signed-in person; issuing
an item and escalating an answered one to the Commercial domain are a document controller's
(`require_controller`, ADR-0013). Items are named by number, for example P123-RFI-0001; the project
comes from `--project`.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_correspondence import registry, reports_technical, views_domain
from tl_mod_correspondence.handlers.domain import Reference
from tl_mod_correspondence.handlers.escalate import EscalateTechnical, handle_escalate_technical
from tl_mod_correspondence.handlers.technical import (
    RaiseTechnical,
    ReturnTechnical,
    SubmitTechnical,
    UpdateTechnical,
    handle_raise_technical,
    handle_return_technical,
    handle_submit_technical,
    handle_update_technical,
)
from tl_mod_correspondence.handlers.technical_flow import (
    AnswerTechnical,
    CloseTechnical,
    IssueTechnical,
    ReissueTechnical,
    ReviewTechnicalAnswer,
    handle_answer_technical,
    handle_close_technical,
    handle_issue_technical,
    handle_reissue_technical,
    handle_review_technical_answer,
)

from tl_cli.corr import recipient
from tl_cli.derive_support import configure_files
from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _service_errors
from tl_cli.session import require_controller

app = typer.Typer(
    help="RFIs, technical queries and deviation requests: raise, issue, answer, escalate.",
    no_args_is_help=True,
)

_Number = Annotated[str, typer.Argument(help="The item number, for example P123-RFI-0001.")]
_Date = Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD. Default today.")]
_DateReason = Annotated[
    str | None, typer.Option("--date-reason", help="Required for a date before today.")
]
_Flag = Annotated[str, typer.Option(help="yes, no or unknown.")]


def _row(db: DbTarget, scope: str, project: str, number: str) -> registry.ItemRow:
    """The item ``number``; exits `error: no item 'X' in project 'P'` (also for one the person may
    not read, or one that is not a Technical item)."""
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = registry.find_item(uow.conn(), scope, number)
    if found is None or found.record_type != "correspondence.TechnicalItem":
        _fail(f"no technical item {number!r} in project {project!r}")
    return found


def _reference(text: str) -> Reference:
    """``ID`` or ``ID@PIN`` (a document pinned at a revision label)."""
    record_id, _, pin = text.partition("@")
    return Reference(record_id=record_id, pin=pin or None)


def _line(line: reports_technical.RfiLogLine) -> str:
    late = f" OVERDUE {line.days_overdue}d" if line.overdue else ""
    took = "-" if line.response_days is None else f"{line.response_days}d"
    flags = f"cost {line.cost_impact or line.potential_cost_impact} "
    flags += f"schedule {line.schedule_impact or line.potential_schedule_impact}"
    return (
        f"{line.number} {line.state} {line.subtype} {line.discipline or '-'} "
        f"needed {line.required_by or '-'} answered {line.answered_on or '-'} took {took} "
        f"{flags}{late} {line.subject}"
    )


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    subtype: Annotated[str | None, typer.Option("--subtype", help="rfi, tq or deviation.")] = None,
    state: Annotated[str | None, typer.Option("--state")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    only_open: Annotated[bool, typer.Option("--open", help="Not answered, not closed.")] = False,
    only_overdue: Annotated[
        bool, typer.Option("--overdue", help="Awaiting a response past the day needed.")
    ] = False,
    only_impact: Annotated[
        bool, typer.Option("--impact", help="The answer said yes to cost or schedule.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """The RFI log: number, state, kind, discipline, dates, response time, impact flags, subject."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        log = reports_technical.rfi_log(
            uow.conn(),
            f"project:{project}",
            subtype=subtype,
            state=state,
            discipline=discipline,
            only_open=only_open,
            only_overdue=only_overdue,
            only_impact=only_impact,
        )
    if as_json:
        typer.echo(json.dumps(log.model_dump(), indent=2))
        return
    for line in log.lines:
        typer.echo(_line(line))
    average = "-" if log.average_response_days is None else f"{log.average_response_days}d"
    typer.echo(
        f"{log.total} items, {log.answered} answered, {log.open} open, {log.overdue} overdue, "
        f"{log.impact_yes} with an impact; average response {average}"
    )


@app.command("show")
def show(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """One item: its question, answer, impact statements, clocks and escalations."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        view = views_domain.technical_view(uow.conn(), f"project:{project}", number)
    typer.echo(f"{view.number} {view.state} {view.subtype} {view.discipline or '-'}")
    typer.echo(f"subject {view.subject}")
    typer.echo(f"class {view.confidentiality}")
    typer.echo("to " + (", ".join(r.name or r.email or "-" for r in view.to) or "-"))
    typer.echo(f"issued {view.issued_on or '-'} needed by {view.required_by or '-'}")
    typer.echo(
        f"expected cost {view.potential_cost_impact} schedule {view.potential_schedule_impact}"
    )
    typer.echo(f"question {view.question}")
    if view.proposed_solution:
        typer.echo(f"proposed {view.proposed_solution}")
    if view.answered_on:
        typer.echo(
            f"answered {view.answered_on}: cost {view.answer_cost_impact} "
            f"schedule {view.answer_schedule_impact}"
        )
        typer.echo(f"answer {view.answer}")
    if view.review_decision:
        typer.echo(
            f"judged {view.review_decision} on {view.reviewed_on}: {view.review_note or '-'}"
        )
    for clock in view.clocks:
        left = "-" if clock.days_left is None else str(clock.days_left)
        typer.echo(
            f"clock {clock.key} {clock.label} {clock.effective_state} "
            f"due {clock.due_on} left {left}"
        )
    for esc in view.escalations:
        typer.echo(f"escalated to {esc.number} ({esc.subtype}, {esc.state})")


@app.command("raise")
def raise_(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject")],
    question: Annotated[str, typer.Option("--question", help="The question, or the deviation.")],
    subtype: Annotated[str, typer.Option("--subtype", help="rfi, tq or deviation.")] = "rfi",
    solution: Annotated[str | None, typer.Option("--solution", help="What you propose.")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    required_by: Annotated[
        str | None, typer.Option("--required-by", help="The day an answer is needed.")
    ] = None,
    cost_impact: Annotated[
        str, typer.Option("--cost-impact", help="yes, no or unknown.")
    ] = "unknown",
    schedule_impact: Annotated[
        str, typer.Option("--schedule-impact", help="yes, no or unknown.")
    ] = "unknown",
    to: Annotated[
        list[str] | None, typer.Option("--to", help="NAME or NAME:EMAIL. Repeat.")
    ] = None,
    ref: Annotated[
        list[str] | None,
        typer.Option("--ref", help="A record id, or ID@REV to pin a document at a revision."),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Raise an RFI as a Draft (any person). Submit it for review with `tl rfi submit`."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db) as uow:
        made = handle_raise_technical(
            uow,
            RaiseTechnical(
                actor=actor,
                source="cli",
                scope=f"project:{project}",
                subtype=subtype,
                subject=subject,
                question=question,
                proposed_solution=solution,
                discipline=discipline,
                required_by=required_by,
                potential_cost_impact=cost_impact,
                potential_schedule_impact=schedule_impact,
                to=[recipient(t) for t in to or []],
                references=[_reference(r) for r in ref or []],
            ),
        )
    typer.echo(f"raised {made.key}")


@app.command("update")
def update(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    question: Annotated[str | None, typer.Option("--question")] = None,
    solution: Annotated[str | None, typer.Option("--solution")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    required_by: Annotated[str | None, typer.Option("--required-by")] = None,
    cost_impact: Annotated[str | None, typer.Option("--cost-impact")] = None,
    schedule_impact: Annotated[str | None, typer.Option("--schedule-impact")] = None,
    to: Annotated[list[str] | None, typer.Option("--to", help="Replaces the recipients.")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change the fields you name of a draft or an item in internal review."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    given = {
        "subject": subject,
        "question": question,
        "proposed_solution": solution,
        "discipline": discipline,
        "required_by": required_by,
        "potential_cost_impact": cost_impact,
        "potential_schedule_impact": schedule_impact,
        "reason": reason,
    }
    fields = {k: v for k, v in given.items() if v is not None}
    if to is not None:
        fields["to"] = [recipient(t) for t in to]  # type: ignore[assignment]
    with _service_errors(), open_uow(db) as uow:
        handle_update_technical(
            uow,
            UpdateTechnical.model_validate(
                {"actor": actor, "source": "cli", "scope": scope, "stream_id": row.id, **fields}
            ),
        )
    typer.echo(f"updated {number}")


@app.command("submit")
def submit(
    ctx: typer.Context, number: _Number, project: _Project, actor: _Actor = _DEFAULT_ACTOR
) -> None:
    """Send a Draft to internal review (it needs a recipient and a day for the answer)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_submit_technical(
            uow, SubmitTechnical(actor=actor, source="cli", scope=scope, stream_id=row.id)
        )
    typer.echo(f"{number} is in internal review")


@app.command("return")
def return_(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str, typer.Option("--reason")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Send an item in internal review back to its raiser."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_return_technical(
            uow,
            ReturnTechnical(
                actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason
            ),
        )
    typer.echo(f"{number} is a draft again")


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    template: Annotated[str | None, typer.Option("--template")] = None,
    issued_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue an item that passed internal review (controller): a PDF is stored, the send is a
    stub, the clock starts and the item waits for its answer."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    configure_files()
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_issue_technical(
            uow,
            IssueTechnical(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                template=template,
                issued_on=issued_on,
                date_reason=date_reason,
            ),
        )
        after = views_domain.technical_view(uow.conn(), scope, number)
    typer.echo(
        f"issued {number} on {after.issued_on} (delivery {after.delivery}: nothing was sent)"
    )
    for clock in after.clocks:
        typer.echo(f"clock {clock.key} {clock.label} due {clock.due_on}")


@app.command("answer")
def answer(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    text: Annotated[str, typer.Option("--answer", help="The answer.")],
    cost_impact: _Flag = "unknown",
    schedule_impact: _Flag = "unknown",
    answer_item: Annotated[
        str | None, typer.Option("--answer-item", help="The number of the item that carries it.")
    ] = None,
    revision: Annotated[
        str | None, typer.Option("--revision", help="The id of the answering document revision.")
    ] = None,
    answered_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record the answer, with the answerer's statement on cost and schedule."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    item_id = None
    if answer_item is not None:
        with _service_errors(), open_uow(db, readonly=True) as uow:
            found = registry.find_item(uow.conn(), scope, answer_item)
        if found is None:
            _fail(f"no item {answer_item!r} in project {project!r}")
        item_id = found.id
    with _service_errors(), open_uow(db) as uow:
        handle_answer_technical(
            uow,
            AnswerTechnical(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                answer=text,
                cost_impact=cost_impact,
                schedule_impact=schedule_impact,
                answer_item_id=item_id,
                answering_revision_id=revision,
                answered_on=answered_on,
                date_reason=date_reason,
            ),
        )
    typer.echo(f"answered {number}: cost {cost_impact} schedule {schedule_impact}")
    if "yes" in (cost_impact, schedule_impact):
        typer.echo(
            f"the answer has an impact: `tl rfi escalate {number}` raises a commercial notice"
        )


@app.command("review")
def review(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    accept: Annotated[bool, typer.Option("--accept/--reject")] = True,
    note: Annotated[str | None, typer.Option("--note", help="Needed to reject.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Accept the answer, or reject it with a note."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_review_technical_answer(
            uow,
            ReviewTechnicalAnswer(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                decision="accepted" if accept else "rejected",
                note=note,
            ),
        )
    typer.echo(f"{number} {'accepted' if accept else 'rejected'}")


@app.command("reissue")
def reissue(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str, typer.Option("--reason")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Send a rejected item round again (back to internal review)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_reissue_technical(
            uow,
            ReissueTechnical(
                actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason
            ),
        )
    typer.echo(f"{number} is in internal review again")


@app.command("close")
def close(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close an item that needs no more work (a reason is needed unless it was accepted)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_close_technical(
            uow,
            CloseTechnical(actor=actor, source="cli", scope=scope, stream_id=row.id, reason=reason),
        )
    typer.echo(f"closed {number}")


@app.command("escalate")
def escalate(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    subtype: Annotated[
        str, typer.Option("--subtype", help="The notice: early_warning, change_notice, ...")
    ] = "early_warning",
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    clause: Annotated[
        str | None, typer.Option("--clause", help="CONTRACT/CLAUSE the notice is given under.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Make a commercial notice from an answered item (controller): a draft, derived from the RFI,
    whose time bar counts from the day of the answer."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        made = handle_escalate_technical(
            uow,
            EscalateTechnical(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                subtype=subtype,
                subject=subject,
                clause=clause,
            ),
        )
        notice = registry.get_item(uow.conn(), made.stream_id)
        bars = [c for c in registry.clocks_of(uow.conn(), made.stream_id) if c.kind == "time_bar"]
    typer.echo(f"escalated {number} to {made.key}")
    for bar in bars:
        typer.echo(f"time bar {bar.key} {bar.label} due {bar.due_on}")
    if notice is not None:
        typer.echo(f"{notice.number} is a draft, class {notice.confidentiality}")
