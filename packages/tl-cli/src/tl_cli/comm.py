"""The `tl comm` group: the Commercial domain, notices and claims under the contract (brief 9 M10).

Commercial items are `restricted` (ADR-0016), so **every command of this group needs a document
controller or admin session** (`require_controller`, ADR-0013): a person who cannot read a
restricted item cannot make one, and the module refuses a viewer below that level as well. Each
subcommand parses options, makes one call into `tl_mod_correspondence` and prints. The time bar of
a notice starts when it is raised and counts from the day the contractor became aware
(`--aware-on`); issuing the notice meets it. Items are named by number, for example P123-EW-0001.

`tl comm export` writes the pending and approved changes as CSV for the cost system. It is a bulk
export (brief 18.10): it writes only the classes named with `--class` (default internal, which is
none of the Commercial items), never privileged ones, and quotes any cell a spreadsheet would run
as a formula.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_mod_correspondence import export, registry, reports_commercial, views_domain
from tl_mod_correspondence.handlers.commercial import (
    RaiseCommercial,
    ReturnCommercial,
    ReviewCommercial,
    SubmitCommercial,
    UpdateCommercial,
    handle_raise_commercial,
    handle_return_commercial,
    handle_review_commercial,
    handle_submit_commercial,
    handle_update_commercial,
)
from tl_mod_correspondence.handlers.commercial_flow import (
    AssessCommercial,
    CloseCommercial,
    IssueCommercial,
    ReferCommercialToLegal,
    handle_assess_commercial,
    handle_close_commercial,
    handle_issue_commercial,
    handle_refer_commercial_to_legal,
)
from tl_mod_correspondence.handlers.domain import CostCodeImpact, Reference

from tl_cli.corr import recipient
from tl_cli.derive_support import configure_files
from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _service_errors
from tl_cli.session import require_controller

app = typer.Typer(
    help="Notices and claims under the contract: raise, review, issue, assess, export.",
    no_args_is_help=True,
)

_Number = Annotated[str, typer.Argument(help="The item number, for example P123-EW-0001.")]
_Date = Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD. Default today.")]
_DateReason = Annotated[
    str | None, typer.Option("--date-reason", help="Required for a date before today.")
]
_COMMERCIAL = "correspondence.CommercialItem"


def _row(db: DbTarget, scope: str, project: str, number: str) -> registry.ItemRow:
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = registry.find_item(uow.conn(), scope, number)
    if found is None or found.record_type != _COMMERCIAL:
        _fail(f"no commercial item {number!r} in project {project!r}")
    return found


def _impact(text: str) -> CostCodeImpact:
    """``CODE`` or ``CODE=AMOUNT`` or ``CODE=AMOUNT:HOURS``."""
    code, _, rest = text.partition("=")
    amount, _, hours = rest.partition(":")
    return CostCodeImpact(cost_code=code, amount=amount or None, hours=hours or None)


def _line(line: reports_commercial.CommercialLine) -> str:
    bar = "no bar"
    if line.time_bar_due:
        left = "-" if line.time_bar_days_left is None else str(line.time_bar_days_left)
        bar = f"bar {line.time_bar_state} due {line.time_bar_due} left {left}"
        bar += " LATE" if line.time_bar_late else ""
    money = (
        f"{line.currency or '-'} est {line.estimated_value or '-'} ass {line.assessed_value or '-'}"
    )
    return f"{line.number} {line.state} {line.subtype} {bar} {money} {line.subject}"


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    subtype: Annotated[str | None, typer.Option("--subtype")] = None,
    state: Annotated[str | None, typer.Option("--state")] = None,
    only_open: Annotated[bool, typer.Option("--open", help="Leave out closed and void.")] = False,
    time_bars: Annotated[
        bool, typer.Option("--time-bars", help="Time bars still running, or late.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """The Commercial register: state, time bar, estimated and assessed value, subject."""
    db: DbTarget = ctx.obj
    require_controller(db)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = reports_commercial.commercial_register(
            uow.conn(),
            f"project:{project}",
            subtype=subtype,
            state=state,
            only_open=only_open,
            time_bars_only=time_bars,
        )
    if as_json:
        typer.echo(json.dumps(found.model_dump(), indent=2))
        return
    for line in found.lines:
        typer.echo(_line(line))
    for total in found.totals:
        typer.echo(
            f"total {total.currency}: {total.count} items, estimated {total.estimated}, "
            f"assessed {total.assessed}"
        )
    typer.echo(f"{found.time_bars_running} time bars running, {found.time_bars_late} late")


@app.command("show")
def show(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """One item: values, clause, awareness day, time bar clocks and assessment."""
    db: DbTarget = ctx.obj
    require_controller(db)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        view = views_domain.commercial_view(uow.conn(), f"project:{project}", number)
    typer.echo(f"{view.number} {view.state} {view.subtype}")
    typer.echo(f"subject {view.subject}")
    typer.echo(f"class {view.confidentiality}")
    typer.echo(f"clause {view.clause or '-'} aware {view.aware_on or '-'}")
    typer.echo(f"from {view.derived_from_number or '-'}")
    typer.echo(
        f"estimated {view.currency or '-'} {view.estimated_value or '-'} "
        f"hours {view.estimated_hours or '-'} schedule {view.schedule_impact_days} days"
    )
    for impact in view.cost_code_impacts:
        typer.echo(f"cost code {impact['cost_code']} {impact.get('amount') or '-'}")
    if view.assessment_status:
        typer.echo(
            f"assessed {view.assessment_status} {view.assessed_value or '-'} on {view.assessed_on}"
        )
    for clock in view.clocks:
        left = "-" if clock.days_left is None else str(clock.days_left)
        typer.echo(
            f"clock {clock.key} {clock.label} ({clock.kind}) {clock.effective_state} "
            f"due {clock.due_on} left {left}"
        )
    if view.entitlement_basis:
        typer.echo(f"basis {view.entitlement_basis}")


@app.command("raise")
def raise_(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject")],
    subtype: Annotated[
        str, typer.Option("--subtype", help="early_warning, change_notice, claim_notice, ...")
    ] = "early_warning",
    body: Annotated[str | None, typer.Option("--body")] = None,
    clause: Annotated[
        str | None, typer.Option("--clause", help="CONTRACT/CLAUSE: its time bar sets the clock.")
    ] = None,
    aware_on: Annotated[
        str | None, typer.Option("--aware-on", help="The day the contractor became aware.")
    ] = None,
    currency: Annotated[str | None, typer.Option("--currency")] = None,
    value: Annotated[str | None, typer.Option("--value", help="Estimated value, 12500.00.")] = None,
    hours: Annotated[str | None, typer.Option("--hours")] = None,
    cost_code: Annotated[
        list[str] | None,
        typer.Option("--cost-code", help="CODE, CODE=AMOUNT or CODE=AMOUNT:HOURS."),
    ] = None,
    schedule_days: Annotated[int | None, typer.Option("--schedule-days")] = None,
    schedule_note: Annotated[str | None, typer.Option("--schedule-note")] = None,
    basis: Annotated[
        str | None, typer.Option("--basis", help="Why the contractor is entitled.")
    ] = None,
    to: Annotated[
        list[str] | None, typer.Option("--to", help="NAME or NAME:EMAIL. Repeat.")
    ] = None,
    ref: Annotated[list[str] | None, typer.Option("--ref", help="A record id. Repeat.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Raise a notice as a Draft (controller). Its time bar starts counting from --aware-on."""
    db: DbTarget = ctx.obj
    require_controller(db)
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        made = handle_raise_commercial(
            uow,
            RaiseCommercial(
                actor=actor,
                source="cli",
                scope=scope,
                subtype=subtype,
                subject=subject,
                body=body,
                clause=clause,
                aware_on=aware_on,
                currency=currency,
                estimated_value=value,
                estimated_hours=hours,
                cost_code_impacts=[_impact(c) for c in cost_code or []] or None,
                schedule_impact_days=schedule_days,
                schedule_impact_note=schedule_note,
                entitlement_basis=basis,
                to=[recipient(t) for t in to or []],
                references=[Reference(record_id=r) for r in ref or []],
            ),
        )
        bars = [c for c in registry.clocks_of(uow.conn(), made.stream_id) if c.kind == "time_bar"]
    typer.echo(f"raised {made.key}")
    for bar in bars:
        typer.echo(f"time bar {bar.key} {bar.label} due {bar.due_on}")


@app.command("update")
def update(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    currency: Annotated[str | None, typer.Option("--currency")] = None,
    value: Annotated[str | None, typer.Option("--value")] = None,
    hours: Annotated[str | None, typer.Option("--hours")] = None,
    cost_code: Annotated[
        list[str] | None, typer.Option("--cost-code", help="Replaces the cost codes.")
    ] = None,
    schedule_days: Annotated[int | None, typer.Option("--schedule-days")] = None,
    schedule_note: Annotated[str | None, typer.Option("--schedule-note")] = None,
    basis: Annotated[str | None, typer.Option("--basis")] = None,
    to: Annotated[list[str] | None, typer.Option("--to", help="Replaces the recipients.")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change the fields you name of a draft or an item in commercial review."""
    db: DbTarget = ctx.obj
    require_controller(db)
    scope = f"project:{project}"
    row = _row(db, scope, project, number)
    given: dict[str, object] = {
        "subject": subject,
        "body": body,
        "currency": currency,
        "estimated_value": value,
        "estimated_hours": hours,
        "schedule_impact_days": schedule_days,
        "schedule_impact_note": schedule_note,
        "entitlement_basis": basis,
        "reason": reason,
    }
    fields = {k: v for k, v in given.items() if v is not None}
    if cost_code is not None:
        fields["cost_code_impacts"] = [_impact(c) for c in cost_code]
    if to is not None:
        fields["to"] = [recipient(t) for t in to]
    with _service_errors(), open_uow(db) as uow:
        handle_update_commercial(
            uow,
            UpdateCommercial.model_validate(
                {"actor": actor, "source": "cli", "scope": scope, "stream_id": row.id, **fields}
            ),
        )
    typer.echo(f"updated {number}")


def _move(
    db: DbTarget,
    project: str,
    number: str,
    actor: str,
    model: Callable[..., Command],
    handler: Callable[[UnitOfWork, Any], CommandResult],
    **more: object,
) -> str:
    """Run one transition command on an item (the shared body of submit, review, return, close
    and legal) and return its state."""
    scope = f"project:{project}"
    require_controller(db)
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handler(uow, model(actor=actor, source="cli", scope=scope, stream_id=row.id, **more))
        after = registry.get_item(uow.conn(), row.id)
    return after.state if after else "?"


@app.command("submit")
def submit(
    ctx: typer.Context, number: _Number, project: _Project, actor: _Actor = _DEFAULT_ACTOR
) -> None:
    """Send a Draft to commercial review (a claim needs its basis and its clause first)."""
    state = _move(ctx.obj, project, number, actor, SubmitCommercial, handle_submit_commercial)
    typer.echo(f"{number} is {state}")


@app.command("review")
def review(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    note: Annotated[str | None, typer.Option("--note")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Pass an item in commercial review to the project manager's approval."""
    state = _move(
        ctx.obj, project, number, actor, ReviewCommercial, handle_review_commercial, note=note
    )
    typer.echo(f"{number} is {state}")


@app.command("return")
def return_(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str, typer.Option("--reason")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Send an item in review back to its author."""
    state = _move(
        ctx.obj, project, number, actor, ReturnCommercial, handle_return_commercial, reason=reason
    )
    typer.echo(f"{number} is {state}")


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
    """Approve and issue the notice: a PDF is stored, the send is a stub, the time bar is met."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    configure_files()
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_issue_commercial(
            uow,
            IssueCommercial(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=row.id,
                template=template,
                issued_on=issued_on,
                date_reason=date_reason,
            ),
        )
        after = views_domain.commercial_view(uow.conn(), scope, number)
    typer.echo(
        f"issued {number} on {after.issued_on} (delivery {after.delivery}: nothing was sent)"
    )
    for clock in after.clocks:
        late = " LATE" if clock.closed_on and clock.closed_on > clock.due_on else ""
        typer.echo(
            f"clock {clock.key} {clock.label} {clock.effective_state} due {clock.due_on}{late}"
        )


@app.command("assess")
def assess(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    status: Annotated[str, typer.Option("--status", help="agreed, disputed or partially_agreed.")],
    assessed_value: Annotated[str | None, typer.Option("--value")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    assessed_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record the other party's assessment (a value is needed unless it is disputed)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    row = _row(db, scope, project, number)
    with _service_errors(), open_uow(db) as uow:
        handle_assess_commercial(
            uow,
            AssessCommercial.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "stream_id": row.id,
                    "status": status,
                    "assessed_value": assessed_value,
                    "note": note,
                    "assessed_on": assessed_on,
                    "date_reason": date_reason,
                }
            ),
        )
    typer.echo(f"{number} assessed as {status.replace('_', ' ')}")


@app.command("close")
def close(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Needed for a disputed item.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close an assessed item; its open clocks are cancelled."""
    state = _move(
        ctx.obj, project, number, actor, CloseCommercial, handle_close_commercial, reason=reason
    )
    typer.echo(f"{number} is {state}")


@app.command("legal")
def legal(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str, typer.Option("--reason")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Take a disputed item to the legal route (the item is Escalated)."""
    state = _move(
        ctx.obj,
        project,
        number,
        actor,
        ReferCommercialToLegal,
        handle_refer_commercial_to_legal,
        reason=reason,
    )
    typer.echo(f"{number} is {state}")


@app.command("export")
def export_(
    ctx: typer.Context,
    project: _Project,
    classes: Annotated[
        list[str] | None,
        typer.Option(
            "--class",
            help="A class to write: internal or restricted. Repeat. Default internal, which holds "
            "none of the Commercial items; name restricted to export them.",
        ),
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here instead of the screen.")
    ] = None,
) -> None:
    """The pending and approved changes as CSV for the cost system (controller; bulk export)."""
    db: DbTarget = ctx.obj
    require_controller(db)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        result = export.commercial_export(
            uow.conn(), f"project:{project}", classes=tuple(classes or ["internal"])
        )
    text = export.csv_text(result)
    if out is not None:
        out.write_text(text, encoding="utf-8", newline="")
        typer.echo(f"wrote {len(result.rows)} changes to {out}")
    else:
        sys.stdout.write(text)
    for named, count in sorted(result.left_out.items()):
        typer.echo(
            f"{count} {named} items were left out: name the class with --class {named}", err=True
        )
