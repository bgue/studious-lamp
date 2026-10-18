"""The `tl thread` group: read a record's thread and post to it (P1-I7 WS-B; brief 21.5).

Each subcommand parses options, makes one call into `tl_core.threads` and prints. The rules live in
the services. A record is named by its key (with ``--project``) or by its id. A message never
dispatches: ``post`` stores a body that starts with ``/`` as text. The slash-command side
(`preview`, `dispatch`, `reminders`) is in `tl_cli.thread_dispatch` and is added to this group by
`tl_cli.main`.

STUB: message_lines, show, post, edit and retract are yours to write (ticket P1-I7-T09a). Remove
this paragraph, every STEPS comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. lines = []. For each message of page.messages:
    # 2. when = message.posted_at with "T" replaced by " ", cut to 16 characters. author =
    #    message.author without a leading "user:".
    # 3. first = the first line of message.body that is not blank ("" when there is none).
    #    text = "[retracted]" when message.retracted, else first. edited = "  (edited)" when
    #    message.edited and not message.retracted, else "".
    # 4. Append f"{message.message_id}  {when}  {author}  {text}{edited}" (two spaces
    #    between the columns).
    # 5. When message.dispatch is not None append f"    -> {verb}: {summary}" with four
    #    leading spaces; the summary is message.dispatch.summary, or "done" when it is
    #    empty.
    # 6. Return lines.
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 50,
    before: Annotated[int | None, typer.Option("--before", help="`older` of a page.")] = None,
) -> None:
    """Show the newest messages of RECORD's thread, oldest first."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with service_errors():` get record_id, _scope =
    #    record_of(db, project, record); then, in a read-only unit of work (open_uow(db,
    #    readonly=True)), page = read_thread(uow, record_id, actor=default_actor(db,
    #    local=not is_postgres(db)), limit=limit, before_seq=before).
    # 2. state = "on" if page.enabled else "off"; dispatch = "on" if page.dispatch_enabled
    #    else "off".
    # 3. Echo the header: f"thread {page.record.key or page.record.id}  threads {state}
    #    dispatch {dispatch}  {page.message_count} message", with "s" added unless
    #    page.message_count == 1 (two spaces between the columns).
    # 4. When page.participants is not empty echo "participants " followed by the
    #    participants joined by ", ", each written f"{p.actor} ({'/'.join(p.reasons)})".
    # 5. Echo each line of message_lines(page).
    # 6. When page.next_before is not None echo f"older: --before {page.next_before}".
    raise NotImplementedError


@app.command("post")
def post(
    ctx: typer.Context,
    project: Project,
    record: Annotated[str, typer.Argument(help="Record key (or id).")],
    body: Annotated[str, typer.Argument(help="The message. A leading / does not dispatch.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Post BODY to RECORD's thread."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. who = acting(db, actor).
    # 2. Inside `with service_errors():` get record_id, scope = record_of(db, project,
    #    record); build command = PostThreadMessage(actor=who, source=SOURCE, scope=scope,
    #    record_id=record_id, body=body); with open_uow(db) as uow: result =
    #    handle_post_thread_message(uow, command).
    # 3. Echo f"posted {result.key}" (the message id is result.key).
    # 4. posted = result.events[0].payload. When posted["mentions"] is not empty echo
    #    "mentions " and the mentions joined by ", ", each written f"@{m}". When
    #    posted["record_refs"] is not empty echo f"refs {len(posted['record_refs'])}".
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj. who = acting(db, actor).
    # 2. Inside `with service_errors():` get record_id, scope = record_of(db, project,
    #    record); build command = EditThreadMessage(actor=who, source=SOURCE, scope=scope,
    #    record_id=record_id, message_id=message_id, body=body); with open_uow(db) as uow:
    #    handle_edit_thread_message(uow, command).
    # 3. After the block echo f"edited {message_id}".
    raise NotImplementedError


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
    # STEPS
    # 1. db: DbTarget = ctx.obj. who = acting(db, actor).
    # 2. Inside `with service_errors():` get record_id, scope = record_of(db, project,
    #    record); build command = RetractThreadMessage(actor=who, source=SOURCE,
    #    scope=scope, record_id=record_id, message_id=message_id, reason=reason); with
    #    open_uow(db) as uow: handle_retract_thread_message(uow, command).
    # 3. After the block echo f"retracted {message_id}".
    raise NotImplementedError
