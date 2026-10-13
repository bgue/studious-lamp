"""The `tl review` group: open a review of a revision, answer it, close it (brief 9 M1).

A review cycle asks named reviewers to review one draft revision by a date and collects an outcome
from each. Each subcommand parses options, makes one call into `tl_mod_documents` and prints. The
rules live in the module: reviewers are people with an account and not only the author; a reviewer
answers for themselves; a person cannot close milder than the worst answer; only the opener or the
revision's author closes. A cycle is named by its key (`ISO-1234@A/RC1`, as `tl review open` prints
it); the project comes from `--project`. Recording an answer on someone's behalf and overriding an
outcome are an admin's acts (ADR-0011).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.handlers.reviews import (
    CloseReviewCycle,
    OpenReviewCycle,
    OverrideReviewOutcome,
    RecordReviewOutcome,
    RecordReviewOutcomeOnBehalf,
    ReviewerRequest,
    handle_close_review_cycle,
    handle_open_review_cycle,
    handle_override_review_outcome,
    handle_record_review_outcome,
    handle_record_review_outcome_on_behalf,
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
from tl_cli.session import require_admin

app = typer.Typer(help="Open, answer and close reviews of revisions.", no_args_is_help=True)

_Cycle = Annotated[str, typer.Argument(help="The review cycle key, for example ISO-1234@A/RC1.")]
_Outcome = Annotated[
    str, typer.Option("--outcome", help="approved, approved_with_comments or rejected.")
]


def _cycle(uow: UnitOfWork, scope: str, project: str, key: str) -> registry.ReviewCycleRow:
    """The review cycle ``key``; exits `error: no review cycle 'X' in project 'P'`."""
    record = get_record(uow, scope, key)
    found = registry.get_review_cycle(uow.conn(), record["id"]) if record is not None else None
    if found is None:
        _fail(f"no review cycle {key!r} in project {project!r}")
    return found


@app.command("open")
def open_cycle(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    code: Annotated[str, typer.Argument(help="The draft revision to review, for example A.")],
    project: _Project,
    reviewers: Annotated[
        list[str],
        typer.Option("--reviewer", help="A reviewer, written user:<username>. Repeat it."),
    ],
    due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Open a review round on a draft revision. The revision moves to In Review."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` doc = _document(uow, scope, project,
    #    number); rev = registry.find_revision(uow.conn(), doc.id, code); if it is None,
    #    _fail(f"no revision {code!r} of {number}"). made = handle_open_review_cycle(uow,
    #    OpenReviewCycle(actor=actor, source="cli", scope=scope, revision_id=rev.id,
    #    reviewers=[ReviewerRequest(reviewer=r) for r in reviewers], due_date=due)).
    # 3. Print `opened <made.key> round <n>` where n is the number after "RC" in made.key, and
    #    then `reviewers <len(reviewers)>`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        doc = _document(uow, scope, project, number)
        rev = registry.find_revision(uow.conn(), doc.id, code)
        if rev is None:
            _fail(f"no revision {code!r} of {number}")
        made = handle_open_review_cycle(
            uow,
            OpenReviewCycle(
                actor=actor,
                source="cli",
                scope=scope,
                revision_id=rev.id,
                reviewers=[ReviewerRequest(reviewer=r) for r in reviewers],
                due_date=due,
            ),
        )
    typer.echo(f"opened {made.key} round {(made.key or '').rsplit('RC', 1)[-1]}")
    typer.echo(f"reviewers {len(reviewers)}")


@app.command("answer")
def answer(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: _Outcome,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record your own answer to a review: approved, approved with comments, or rejected."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_record_review_outcome(uow, RecordReviewOutcome.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "comment": comment})). The answer is the caller's own: do not pass a reviewer. A bad
    #    `--outcome` is reported by _service_errors as `error: outcome: ...`.
    # 3. Print `answered <cycle>: <outcome> by <actor>`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _cycle(uow, scope, project, cycle)
        handle_record_review_outcome(
            uow,
            RecordReviewOutcome.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "review_cycle_id": row.id,
                    "outcome": outcome,
                    "comment": comment,
                }
            ),
        )
    typer.echo(f"answered {cycle}: {outcome} by {actor}")


@app.command("on-behalf")
def on_behalf(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    reviewer: Annotated[str, typer.Option("--reviewer", help="Whose answer this is.")],
    outcome: _Outcome,
    comment: Annotated[str, typer.Option("--comment", help="How the answer reached you.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record a reviewer's answer for them (admin). The comment is required and kept."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_record_review_outcome_on_behalf(uow, RecordReviewOutcomeOnBehalf.model_validate(
    #    {"actor": actor, "source": "cli", "scope": scope, "review_cycle_id": row.id,
    #    "reviewer": reviewer, "outcome": outcome, "comment": comment})).
    # 3. Print `recorded <cycle>: <outcome> for <reviewer> by <actor>`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_admin(db)
    with _service_errors(), open_uow(db) as uow:
        row = _cycle(uow, scope, project, cycle)
        handle_record_review_outcome_on_behalf(
            uow,
            RecordReviewOutcomeOnBehalf.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "review_cycle_id": row.id,
                    "reviewer": reviewer,
                    "outcome": outcome,
                    "comment": comment,
                }
            ),
        )
    typer.echo(f"recorded {cycle}: {outcome} for {reviewer} by {actor}")


@app.command("close")
def close(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: Annotated[
        str | None,
        typer.Option("--outcome", help="Default: the worst answer. Never milder than it."),
    ] = None,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Required while a reviewer has not answered.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close a review cycle (its opener or the revision's author). The revision returns to Draft."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_close_review_cycle(uow, CloseReviewCycle.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "reason": reason})); after = _cycle(uow, scope, project, cycle).
    # 3. Print `closed <cycle>: <after.outcome>`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = _cycle(uow, scope, project, cycle)
        handle_close_review_cycle(
            uow,
            CloseReviewCycle.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "review_cycle_id": row.id,
                    "outcome": outcome,
                    "reason": reason,
                }
            ),
        )
        after = _cycle(uow, scope, project, cycle)
    typer.echo(f"closed {cycle}: {after.outcome}")


@app.command("override")
def override(
    ctx: typer.Context,
    cycle: _Cycle,
    project: _Project,
    outcome: _Outcome,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close a cycle with a stated outcome, even a milder one than the answers (admin)."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _cycle(uow, scope, project, cycle);
    #    handle_override_review_outcome(uow, OverrideReviewOutcome.model_validate({"actor": actor,
    #    "source": "cli", "scope": scope, "review_cycle_id": row.id, "outcome": outcome,
    #    "reason": reason})).
    # 3. Print `closed <cycle>: <outcome> (overridden)`.
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_admin(db)
    with _service_errors(), open_uow(db) as uow:
        row = _cycle(uow, scope, project, cycle)
        handle_override_review_outcome(
            uow,
            OverrideReviewOutcome.model_validate(
                {
                    "actor": actor,
                    "source": "cli",
                    "scope": scope,
                    "review_cycle_id": row.id,
                    "outcome": outcome,
                    "reason": reason,
                }
            ),
        )
    typer.echo(f"closed {cycle}: {outcome} (overridden)")


@app.command("ls")
def ls(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    code: Annotated[str, typer.Argument(help="The revision code.")],
    project: _Project,
) -> None:
    """List the review cycles of a revision, each followed by its reviewers."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc = _document(uow,
    #    scope, project, number); rev = registry.find_revision(uow.conn(), doc.id, code) (exit
    #    `error: no revision 'X' of N` when it is None); cycles =
    #    registry.review_cycles_of(uow.conn(), rev.id); and for each cycle its reviewers =
    #    registry.reviewers_of(uow.conn(), cycle.id).
    # 3. For each cycle print, joined by two spaces: cycle.key, f"round={round}", state,
    #    f"due={due_date or '-'}", f"outcome={outcome or '-'}". Under it one line per reviewer:
    #    two spaces, then joined by two spaces: reviewer, outcome or "pending", responded_on or
    #    "-", comment or "-".
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    shown: list[tuple[registry.ReviewCycleRow, list[registry.ReviewerRow]]] = []
    with _service_errors(), open_uow(db, readonly=True) as uow:
        doc = _document(uow, scope, project, number)
        rev = registry.find_revision(uow.conn(), doc.id, code)
        if rev is None:
            _fail(f"no revision {code!r} of {number}")
        for row in registry.review_cycles_of(uow.conn(), rev.id):
            shown.append((row, registry.reviewers_of(uow.conn(), row.id)))
    for row, people in shown:
        head = [
            row.key,
            f"round={row.round}",
            row.state,
            f"due={row.due_date or '-'}",
            f"outcome={row.outcome or '-'}",
        ]
        typer.echo("  ".join(head))
        for person in people:
            line = [
                person.reviewer,
                person.outcome or "pending",
                person.responded_on or "-",
                person.comment or "-",
            ]
            typer.echo("  " + "  ".join(line))
