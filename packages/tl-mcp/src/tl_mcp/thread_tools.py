"""Thread tools: read a record's thread, post to it, propose a dispatch (brief 21.5).

``read_thread`` only reads, as the acting agent: a thread is as visible as its record, so a record
the agent cannot read gives the record error. ``post_thread_message`` writes directly, like
``post_feed``: a message changes no record and never dispatches, even when the text starts with
``/``; the thread labels it with the agent's actor. ``propose_dispatch`` never changes anything: it
plans the line as the agent, has it checked, and files a proposal a person accepts;
accepting plans it again as that person, so it runs only what that person may run and only if the
plan is unchanged (ADR-0018). ``threads.agents.can_dispatch = none`` refuses the tool.

Every tool runs inside ``guarded`` (identifier parts checked, authorise hook, errors mapped).
``server.py`` calls :func:`register_thread_tools`.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from tl_api.thread_runner import thread_runner
from tl_core.services import proposals
from tl_core.threads.contract import (
    MAX_MESSAGE_CHARS,
    READ_THREAD_MAX_PAGE,
)
from tl_core.threads.dispatch import build_dispatch_proposal
from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message
from tl_core.threads.queries import ThreadPage
from tl_core.threads.queries import read_thread as read_thread_page

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.tools import resolve_record_id
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    POSTS,
    PROPOSES,
    ProposalResult,
    Summary,
    _envelope,
    _result,
    _short,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Record = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A record id (ULID), or a record key such as `P123-NCR-0042` (with `scope`).",
    ),
]
ScopeOfKey = Annotated[
    str | None,
    Field(max_length=MAX_PART, description="The scope of the key. Required when giving a key."),
]


class ThreadPostResult(BaseModel):
    """What ``post_thread_message`` returns."""

    message_id: str
    record_id: str
    author: str
    mentions: list[str]
    record_refs: list[str]


def read_thread_impl(
    ctx: McpContext, *, record: str, scope: str | None, limit: int, before_seq: int | None
) -> ThreadPage:
    """The newest ``limit`` messages of the record's thread, oldest first, with its participants.

    Resolve the record with ``resolve_record_id``, then ``read_thread`` in a read-only unit of work
    as ``ctx.actor``. ``next_before`` of the page is the ``before_seq`` of the older one.
    """
    with ctx.factory(True) as uow:
        record_id = resolve_record_id(uow, record, scope)
        return read_thread_page(uow, record_id, actor=ctx.actor, limit=limit, before_seq=before_seq)


def post_thread_message_impl(
    ctx: McpContext, *, record: str, scope: str | None, body: str
) -> ThreadPostResult:
    """Post ``body`` to the record's thread as the agent. It never dispatches.

    The command's scope is the record's own (``_envelope`` gives the envelope), ``source`` is
    ``proposals.source_for(ctx.actor)`` (``mcp:<id>``). The handler's refusals (threads off, record
    not found) propagate to ``guarded``.
    """
    envelope = _envelope(ctx, record, scope)
    command = PostThreadMessage(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=str(envelope["scope"]),
        record_id=str(envelope["id"]),
        body=body,
    )
    with ctx.factory(False) as uow:
        result = handle_post_thread_message(uow, command)
    posted = result.events[0].payload
    return ThreadPostResult(
        message_id=str(result.key),
        record_id=command.record_id,
        author=ctx.actor,
        mentions=[str(m) for m in posted["mentions"]],
        record_refs=[str(r) for r in posted["record_refs"]],
    )


def propose_dispatch_impl(
    ctx: McpContext, *, record: str, scope: str | None, text: str, summary: str | None
) -> ProposalResult:
    """Plan ``text`` as the agent and file the proposal of the dispatch (never run it).

    The plan is made with the agent's identity and the typed command table; a plan with problems,
    a text that is not a command line, threads or dispatch switched off, or
    ``threads.agents.can_dispatch = none`` raise the service's refusal. The proposal carries the
    plan's token: a person's acceptance must find the same plan.
    """
    envelope = _envelope(ctx, record, scope)
    runner = thread_runner()
    command = build_dispatch_proposal(
        ctx.factory,
        scope=str(envelope["scope"]),
        record_id=str(envelope["id"]),
        text=text,
        agent=ctx.actor,
        runner=runner,
    )
    label = summary or f"Dispatch on {envelope.get('key') or envelope['id']}: {_short(text, 120)}"
    view = proposals.submit(
        ctx.factory,
        tool="propose_dispatch",
        agent=ctx.actor,
        command=command,
        summary=label,
        runner=runner,
    )
    return _result(view)


def register_thread_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add ``read_thread``, ``post_thread_message`` and ``propose_dispatch`` to ``server``."""

    @server.tool(name="read_thread", annotations=READ_ONLY)
    def read_thread_tool(
        record: Record,
        scope: ScopeOfKey = None,
        limit: Annotated[int, Field(ge=1, le=READ_THREAD_MAX_PAGE)] = 50,
        before_seq: Annotated[
            int | None, Field(ge=0, description="`next_before` of the previous page.")
        ] = None,
    ) -> ThreadPage:
        """Read the message thread of a record: the newest messages, oldest first.

        Each message has its author, text, mentions and the records its text names. A dispatch
        message carries what its commands did. `enabled` says whether the record may have a thread;
        the thread is as visible as the record.
        """
        with guarded(ctx, "read_thread", resource_name("record", record)):
            return read_thread_impl(
                ctx, record=record, scope=scope, limit=limit, before_seq=before_seq
            )

    @server.tool(annotations=POSTS)
    def post_thread_message(
        record: Record,
        body: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_CHARS)],
        scope: ScopeOfKey = None,
    ) -> ThreadPostResult:
        """Post a message to a record's thread, labelled with your agent name.

        A message changes no record and never dispatches, even when it starts with `/`. To ask for
        work, use `propose_dispatch`. Mention people with `@name` and records with `#KEY`.
        """
        with guarded(ctx, "post_thread_message", resource_name("record", record)):
            return post_thread_message_impl(ctx, record=record, scope=scope, body=body)

    @server.tool(annotations=PROPOSES)
    def propose_dispatch(
        record: Record,
        text: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_MESSAGE_CHARS,
                description="A slash command: `/link #KEY`, `/status Issued`, "
                "`/raise record <title>`, `/dispatch <action> name=value`, `/remind +2h @x`.",
            ),
        ],
        scope: ScopeOfKey = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a dispatch from a record's thread. A person must accept it before anything runs.

        The command is planned now, as you, with the rules that apply when it is accepted; an
        error means it could not run. When a person accepts, it is planned again as that person
        and runs only if every command is allowed to them and nothing it depends on has changed.
        """
        with guarded(ctx, "propose_dispatch", resource_name("record", record)):
            return propose_dispatch_impl(
                ctx, record=record, scope=scope, text=text, summary=summary
            )
