"""Record threads over HTTP: read a thread, preview a slash command, confirm it (brief 21.5).

Messages are written with the generated command routes (``POST /commands/PostThreadMessage``,
``EditThreadMessage``, ``RetractThreadMessage``): a message never dispatches. Dispatch has its own
two routes because it needs the caller's access, which only this layer knows:

* ``POST /records/{id}/thread/preview`` plans the line as the caller and returns the preview;
* ``POST /records/{id}/thread/dispatch`` confirms it with the preview's token.

Both load the record first, so a thread is as visible as its record (an unreadable record is the
record route's 404). The access the planner checks is ``holds`` of the caller's own principal, never
a field of the request; an agent cannot use either route (it proposes with the MCP tool).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from tl_core.auth.types import Principal
from tl_core.services.commands import CommandResult
from tl_core.threads.contract import MAX_MESSAGE_CHARS, READ_THREAD_MAX_PAGE, ParseProblem
from tl_core.threads.dispatch import DispatchFromThread, handle_dispatch_from_thread
from tl_core.threads.planner import PreviewResult, ThreadPlanner
from tl_core.threads.queries import ThreadPage, read_thread
from tl_core.threads.visibility import readable_record

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.routes.proposals import holds_access
from tl_api.thread_runner import thread_runner

router = APIRouter(tags=["threads"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("thread.read"))]
Previewer = Annotated[str, Depends(guard("thread.preview", changes_records=True))]
Dispatcher = Annotated[str, Depends(guard("command.DispatchFromThread", changes_records=True))]
Who = Annotated[Principal, Depends(current_principal)]

API_SOURCE = "api"


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class DispatchBody(BaseModel):
    """What a confirmation carries: the line, the token the preview returned and its expiry."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: str | None = Field(default=None, max_length=64)


@router.get("/records/{record_id}/thread", operation_id="get_thread")
def get_thread(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    limit: Annotated[int, Query(ge=1, le=READ_THREAD_MAX_PAGE)] = 50,
    before_seq: Annotated[
        int | None, Query(ge=0, description="`next_before` of the previous page.")
    ] = None,
) -> ThreadPage:
    """The newest messages of a record's thread (oldest first), with its participants.

    A record the caller cannot read is a 404 `record_not_found`; a record whose type has no thread
    answers with `enabled` false and no messages.
    """
    with ctx.backend(True) as uow:
        return read_thread(uow, record_id, actor=actor, limit=limit, before_seq=before_seq)


@router.post("/records/{record_id}/thread/preview", operation_id="preview_dispatch")
def preview_dispatch(
    ctx: Ctx, actor: Previewer, principal: Who, record_id: str, body: PreviewBody
) -> PreviewResult:
    """Plan a slash command as the caller. Nothing is written.

    `preview` holds what the command would do, each planned command with the access it needs and
    whether the caller holds it, and the `token` to confirm with. A line that does not parse gives
    `problem` instead.
    """
    planner = ThreadPlanner(factory=ctx.backend)
    with ctx.backend(True) as uow:
        found = planner.preview(
            uow,
            record_id=record_id,
            text=body.text,
            actor=actor,
            holds=lambda level: holds_access(principal, actor, level),
            runner=thread_runner(),
        )
    if isinstance(found, ParseProblem):
        return PreviewResult(problem=found)
    return PreviewResult(preview=found)


@router.post("/records/{record_id}/thread/dispatch", operation_id="dispatch_from_thread")
def dispatch_from_thread(
    ctx: Ctx, actor: Dispatcher, principal: Who, record_id: str, body: DispatchBody
) -> CommandResult:
    """Run what the preview showed, in one transaction, as the caller.

    409 `dispatch_stale` when the plan is not the previewed one or the preview expired; 422
    `dispatch_refused` when a planned command is not permitted or is refused; 403
    `dispatch_forbidden` or `dispatch_disabled` when the caller's role or the settings say no.
    Any refusal rolls back everything, the message included.
    """
    with ctx.backend(False) as uow:
        record = readable_record(uow, record_id, actor=actor)
        command = DispatchFromThread(
            actor=actor,
            source=API_SOURCE,
            scope=record.scope,
            record_id=record_id,
            text=body.text,
            token=body.token,
            expires_at=body.expires_at,
        )
        return handle_dispatch_from_thread(
            uow,
            command,
            holds=lambda level: holds_access(principal, actor, level),
            runner=thread_runner(),
        )
