"""`tl thread preview | dispatch | reminders`: plan a slash command, run it, post due reminders
(P1-I7 WS-B; brief 21.5, ADR-0018).

``preview`` plans a line as you and prints what it would do, with a token. ``dispatch`` runs the
previewed line in one transaction with that token, or with ``--yes`` (preview, print, run).
``reminders`` posts the ``/remind`` reminders that have fallen due. The commands are added to the
`tl thread` group by `tl_cli.main`.

STUB: preview_lines, _preview, preview, dispatch and reminders are yours to write (ticket
P1-I7-T09b). Remove this paragraph, every STEPS comment and the two lint-silencing lines below
when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. lines starts with f"token {found.token}" and f"expires {found.expires_at}".
    # 2. For each planned command (n counts from 1): state = f"problem {item.problem.code}"
    #    when item.problem is not None, else "ok" when item.permitted, else "not permitted".
    #    Append f"{n}. {item.command_type}  {item.access or '-'}  {state}  {item.summary}"
    #    (two spaces between the columns).
    # 3. For each link of found.links append f"link: new record dispatched_from
    #    {found.record.key or found.record.id}".
    # 4. For each problem of found.problems append f"problem: {problem.code}:
    #    {problem.message}". Then, for each planned command with a problem, append the same
    #    line for that problem.
    # 5. Append f"note: {note}" for each of found.notes.
    # 6. Last append "can dispatch: yes" when found.can_dispatch, else "can dispatch: no".
    #    Return lines.
    raise NotImplementedError


def _preview(db: DbTarget, record_id: str, line: str, who: str) -> DispatchPreview:
    # STEPS
    # 1. planner = ThreadPlanner(factory=lambda readonly=False: open_uow(db,
    #    readonly=readonly)).
    # 2. In a read-only unit of work found = planner.preview(uow, record_id=record_id,
    #    text=line, actor=who, holds=holds_of(db, who), runner=thread_runner()).
    # 3. When found is a ParseProblem call fail(f"{found.code}: {found.message}") (it
    #    exits). Otherwise return found.
    raise NotImplementedError


def preview(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    line: Annotated[str, typer.Argument(help="A slash command, e.g. '/link REC-2'.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Plan a slash command as you and print what it would do. Nothing is written."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. who = acting(db, actor).
    # 2. Inside `with service_errors():` get record_id, _scope = record_of(db, project,
    #    record) and found = _preview(db, record_id, line, who).
    # 3. After the block echo each line of preview_lines(found).
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj. When (token is None) == (not yes), that is neither or both
    #    were given, call fail("give --token (from `tl thread preview`) or --yes, and not
    #    both").
    # 2. who = acting(db, actor). Inside `with service_errors():` get record_id, scope =
    #    record_of(db, project, record).
    # 3. When yes: found = _preview(db, record_id, line, who); echo each line of
    #    preview_lines(found); token = found.token. Then assert token is not None.
    # 4. command = DispatchFromThread(actor=who, source=SOURCE, scope=scope,
    #    record_id=record_id, text=line, token=token). With open_uow(db) as uow: result =
    #    handle_dispatch_from_thread(uow, command, holds=holds_of(db, who),
    #    runner=thread_runner()).
    # 5. After the block echo f"dispatched {result.key}". posted = the payload of the event
    #    of result.events whose event_type is "Thread.Dispatched". Echo f"verb
    #    {posted['verb']}  {posted['summary']}".
    # 6. For each item of posted["results"] echo f"  {item['command_type']}  {name}
    #    v{item['version']}" where name is item["key"] or item["stream_id"].
    raise NotImplementedError


def reminders(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Most reminders to post.")] = 100,
) -> None:
    """Post the reminders that have fallen due (`/remind`), then stop."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. Import job_queue_for from tl_adapters.queue (inside the
    #    function, as written).
    # 2. Inside `with service_errors():` open a read-only unit of work and queue =
    #    job_queue_for(uow.conn()); runner = JobRunner(lambda readonly=False: open_uow(db,
    #    readonly=readonly), queue, [ThreadReminderKind()]); done =
    #    runner.run_until_idle(limit=limit).
    # 3. After the block echo f"ran {len(done)} reminder", with "s" added unless len(done)
    #    == 1.
    raise NotImplementedError
