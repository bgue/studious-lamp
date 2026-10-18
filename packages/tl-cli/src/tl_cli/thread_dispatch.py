"""`tl thread preview | dispatch | reminders`: plan a slash command, run it, post due reminders
(P1-I7 WS-B; brief 21.5, ADR-0018).

``preview`` plans a line as you and prints what it would do, with a token. ``dispatch`` runs the
previewed line in one transaction with that token, or with ``--yes`` (preview, print, run).
``reminders`` posts the ``/remind`` reminders that have fallen due. The commands are added to the
`tl thread` group by `tl_cli.main`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_api.thread_runner import thread_runner
from tl_core.jobs.runner import JobRunner
from tl_core.threads.contract import DispatchPreview, ParseProblem
from tl_core.threads.dispatch import DispatchFromThread, handle_dispatch_from_thread
from tl_core.threads.planner import ThreadPlanner
from tl_core.threads.reminders import ThreadReminderKind

from tl_cli.derive_support import DEV_ACTOR, Actor, Project, acting, fail, service_errors
from tl_cli.thread_common import SOURCE, holds_of, record_of


def preview_lines(found: DispatchPreview) -> list[str]:
    """The lines ``preview`` prints for a ``DispatchPreview``.

    ``token <hex>``, ``expires <iso>``, one ``<n>. <CommandType>  <access>  <ok|no|problem code>
    <summary>`` per planned command, ``link: <the new record> dispatched_from <the thread's
    record>`` per link, ``problem: <code>: <message>`` per problem (of the plan, then of an item),
    ``note: <note>`` per note, and last ``can dispatch: yes`` or ``can dispatch: no``.
    """
    lines = [f"token {found.token}", f"expires {found.expires_at}"]
    for n, item in enumerate(found.planned, start=1):
        if item.problem is not None:
            state = f"problem {item.problem.code}"
        else:
            state = "ok" if item.permitted else "not permitted"
        lines.append(f"{n}. {item.command_type}  {item.access or '-'}  {state}  {item.summary}")
    for _link in found.links:
        lines.append(f"link: new record dispatched_from {found.record.key or found.record.id}")
    for problem in found.problems:
        lines.append(f"problem: {problem.code}: {problem.message}")
    for item in found.planned:
        if item.problem is not None:
            lines.append(f"problem: {item.problem.code}: {item.problem.message}")
    lines.extend(f"note: {note}" for note in found.notes)
    lines.append("can dispatch: " + ("yes" if found.can_dispatch else "no"))
    return lines


def _preview(db: DbTarget, record_id: str, line: str, who: str) -> DispatchPreview:
    planner = ThreadPlanner(factory=lambda readonly=False: open_uow(db, readonly=readonly))
    with open_uow(db, readonly=True) as uow:
        found = planner.preview(
            uow,
            record_id=record_id,
            text=line,
            actor=who,
            holds=holds_of(db, who),
            runner=thread_runner(),
        )
    if isinstance(found, ParseProblem):
        fail(f"{found.code}: {found.message}")
    return found


def preview(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    line: Annotated[str, typer.Argument(help="A slash command, e.g. '/link REC-2'.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Plan a slash command as you and print what it would do. Nothing is written."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        record_id, _scope = record_of(db, project, record)
        found = _preview(db, record_id, line, who)
    for out in preview_lines(found):
        typer.echo(out)


def dispatch(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    line: Annotated[str, typer.Argument(help="The same slash command that was previewed.")],
    token: Annotated[
        str | None, typer.Option("--token", help="The token `preview` printed.")
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", help="Preview, print the plan and confirm it in one step.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Run a previewed slash command in one transaction, as you."""
    db: DbTarget = ctx.obj
    if (token is None) == (not yes):
        fail("give --token (from `tl thread preview`) or --yes, and not both")
    who = acting(db, actor)
    with service_errors():
        record_id, scope = record_of(db, project, record)
        if yes:
            found = _preview(db, record_id, line, who)
            for out in preview_lines(found):
                typer.echo(out)
            token = found.token
        assert token is not None
        command = DispatchFromThread(
            actor=who, source=SOURCE, scope=scope, record_id=record_id, text=line, token=token
        )
        with open_uow(db) as uow:
            result = handle_dispatch_from_thread(
                uow, command, holds=holds_of(db, who), runner=thread_runner()
            )
    typer.echo(f"dispatched {result.key}")
    posted = [e for e in result.events if e.event_type == "Thread.Dispatched"][0].payload
    typer.echo(f"verb {posted['verb']}  {posted['summary']}")
    for item in posted["results"]:
        typer.echo(
            f"  {item['command_type']}  {item['key'] or item['stream_id']}  v{item['version']}"
        )


def reminders(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Most reminders to post.")] = 100,
) -> None:
    """Post the reminders that have fallen due (`/remind`), then stop."""
    db: DbTarget = ctx.obj
    from tl_adapters.queue import job_queue_for

    with service_errors():
        with open_uow(db, readonly=True) as uow:
            queue = job_queue_for(uow.conn())
        runner = JobRunner(
            lambda readonly=False: open_uow(db, readonly=readonly), queue, [ThreadReminderKind()]
        )
        done = runner.run_until_idle(limit=limit)
    typer.echo(f"ran {len(done)} reminder" + ("" if len(done) == 1 else "s"))
