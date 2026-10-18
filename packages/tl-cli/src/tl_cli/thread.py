"""The `tl thread` group: read a record's thread and post to it (P1-I7 WS-B; brief 21.5).

Each subcommand parses options, makes one call into `tl_core.threads` and prints. The rules live in
the services. A record is named by its key (with ``--project``) or by its id. A message never
dispatches: ``post`` stores a body that starts with ``/`` as text. The slash-command side
(`preview`, `dispatch`, `reminders`) is in `tl_cli.thread_dispatch` and is added to this group by
`tl_cli.main`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, is_postgres, open_uow
from tl_core.threads.messages import (
    EditThreadMessage,
    PostThreadMessage,
    RetractThreadMessage,
    handle_edit_thread_message,
    handle_post_thread_message,
    handle_retract_thread_message,
)
from tl_core.threads.queries import ThreadPage, read_thread

from tl_cli.derive_support import DEV_ACTOR, Actor, Project, acting, service_errors
from tl_cli.session import default_actor
from tl_cli.thread_common import SOURCE, record_of

app = typer.Typer(
    help="Read a record's thread, post to it, preview and confirm a slash command.",
    no_args_is_help=True,
)


def message_lines(page: ThreadPage) -> list[str]:
    """``<id>  <YYYY-MM-DD HH:MM>  <author>  <first line>`` per message, the outcome of a
    dispatch on the next line as ``    -> <verb>: <summary>``; retracted: ``[retracted]``."""
    lines: list[str] = []
    for message in page.messages:
        when = message.posted_at.replace("T", " ")[:16]
        author = message.author.removeprefix("user:")
        first = next((ln for ln in message.body.splitlines() if ln.strip()), "")
        text = "[retracted]" if message.retracted else first
        edited = "  (edited)" if message.edited and not message.retracted else ""
        lines.append(f"{message.message_id}  {when}  {author}  {text}{edited}")
        if message.dispatch is not None:
            lines.append(f"    -> {message.dispatch.verb}: {message.dispatch.summary or 'done'}")
    return lines


@app.command("show")
def show(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 50,
    before: Annotated[int | None, typer.Option("--before", help="`older` of a page.")] = None,
) -> None:
    """Show the newest messages of RECORD's thread, oldest first."""
    db: DbTarget = ctx.obj
    with service_errors():
        record_id, _scope = record_of(db, project, record)
        with open_uow(db, readonly=True) as uow:
            page = read_thread(
                uow,
                record_id,
                actor=default_actor(db, local=not is_postgres(db)),
                limit=limit,
                before_seq=before,
            )
    state = "on" if page.enabled else "off"
    dispatch = "on" if page.dispatch_enabled else "off"
    typer.echo(
        f"thread {page.record.key or page.record.id}  threads {state}  dispatch {dispatch}  "
        f"{page.message_count} message" + ("" if page.message_count == 1 else "s")
    )
    if page.participants:
        people = ", ".join(f"{p.actor} ({'/'.join(p.reasons)})" for p in page.participants)
        typer.echo(f"participants {people}")
    for line in message_lines(page):
        typer.echo(line)
    if page.next_before is not None:
        typer.echo(f"older: --before {page.next_before}")


@app.command("post")
def post(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    body: Annotated[str, typer.Argument(help="The message. A leading / does not dispatch.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Post BODY to RECORD's thread."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        record_id, scope = record_of(db, project, record)
        command = PostThreadMessage(
            actor=who, source=SOURCE, scope=scope, record_id=record_id, body=body
        )
        with open_uow(db) as uow:
            result = handle_post_thread_message(uow, command)
    typer.echo(f"posted {result.key}")
    posted = result.events[0].payload
    if posted["mentions"]:
        typer.echo("mentions " + ", ".join(f"@{m}" for m in posted["mentions"]))
    if posted["record_refs"]:
        typer.echo(f"refs {len(posted['record_refs'])}")


@app.command("edit")
def edit(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    message_id: Annotated[str, typer.Argument(help="The id `post` and `show` print.")],
    body: Annotated[str, typer.Argument(help="The new text.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Replace the text of your own message."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        record_id, scope = record_of(db, project, record)
        command = EditThreadMessage(
            actor=who,
            source=SOURCE,
            scope=scope,
            record_id=record_id,
            message_id=message_id,
            body=body,
        )
        with open_uow(db) as uow:
            handle_edit_thread_message(uow, command)
    typer.echo(f"edited {message_id}")


@app.command("retract")
def retract(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    message_id: Annotated[str, typer.Argument(help="The id `post` and `show` print.")],
    reason: Annotated[str, typer.Option("--reason", help="Why.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Retract your own message; a tombstone stays."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        record_id, scope = record_of(db, project, record)
        command = RetractThreadMessage(
            actor=who,
            source=SOURCE,
            scope=scope,
            record_id=record_id,
            message_id=message_id,
            reason=reason,
        )
        with open_uow(db) as uow:
            handle_retract_thread_message(uow, command)
    typer.echo(f"retracted {message_id}")
