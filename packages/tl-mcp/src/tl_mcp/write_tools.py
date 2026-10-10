"""The write tools: four that propose a change and one that posts to the feed (brief 11.3, 21.3).

``create_record``, ``update_psets``, ``link_records`` and ``transition_workflow`` never change a
record. Each builds the same command the API would run, has it checked by the handler's own rules
(``tl_core.services.proposals.submit``) and returns the pending proposal; a person accepts it
(``tl proposal accept``, ``POST /proposals/{id}/accept``). Everything done on the agent's behalf
carries ``source`` ``mcp:<id>``. ``post_feed`` writes directly: a post is a message, not a record,
and the feed labels it with the agent's actor (``agent:<id>``).

Every tool runs inside ``guarded`` (identifier parts checked, authorise hook, errors mapped) and
every string and container input is bounded. ``server.py`` calls :func:`register_write_tools`.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from tl_core.feed.types import Importance
from tl_core.proposals.types import PROPOSABLE_TOOLS, ProposalView, ToolMode
from tl_core.services import proposals, queries
from tl_core.services.commands import CreateRecord
from tl_core.services.feed import MAX_BODY_LENGTH, PostToFeed, handle_post
from tl_core.services.links import AddLink
from tl_core.services.psets import SetPsetValues
from tl_core.services.workflow import TransitionWorkflow

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.tools import resolve_record_id

MAX_TITLE = 500
MAX_DESCRIPTION = 10_000
MAX_NOTE = 1_000
MAX_JSON_CHARS = 64_000  # psets, values: the JSON text of the whole object
MAX_NUMBERING_ITEMS = 20

PROPOSES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
POSTS = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)

Scope = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="`company` or `project:<id>`."),
]
RecordRef = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="A record id (ULID), or a record key such as `P123-NCR-0042`.",
    ),
]
ScopeForKey = Annotated[
    str | None,
    Field(max_length=MAX_PART, description="The scope of the key. Required when giving a key."),
]
Summary = Annotated[
    str | None,
    Field(
        max_length=proposals.MAX_SUMMARY,
        description="One line for the person who reviews the proposal (default: derived).",
    ),
]
ExpectedVersion = Annotated[
    int | None,
    Field(
        ge=1,
        le=2**31,
        description="The record version you based this on (`version` of get_record). Default: "
        "the version now. If the record changes before a person accepts, the proposal fails.",
    ),
]


class ProposalResult(BaseModel):
    """What a proposing tool returns: the pending proposal and what happens next."""

    proposal: ProposalView
    message: str


class PostResult(BaseModel):
    """What ``post_feed`` returns."""

    post_id: str
    scope: str
    author: str
    suggested_links: int  # record tags in the post that became suggested `references` links


def check_json(name: str, value: Any) -> None:
    """Raise ``ValueError`` when ``value`` is not JSON or its text exceeds ``MAX_JSON_CHARS``."""
    try:
        size = len(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be JSON data") from exc
    if size > MAX_JSON_CHARS:
        raise ValueError(f"{name} is longer than {MAX_JSON_CHARS} characters as JSON")


def _short(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _result(view: ProposalView) -> ProposalResult:
    return ProposalResult(
        proposal=view,
        message=(
            f"Proposal {view.proposal_id} is pending review. Nothing has changed yet: a person "
            "accepts or rejects it in the review queue."
        ),
    )


def _envelope(ctx: McpContext, record: str, scope: str | None) -> dict[str, Any]:
    """The record's envelope (read once, in its own read-only unit of work)."""
    with ctx.factory(True) as uow:
        found = queries.get_record_by_id(uow, resolve_record_id(uow, record, scope))
    assert found is not None
    return found


def create_record_impl(
    ctx: McpContext,
    *,
    scope: str,
    title: str,
    record_type: str,
    description: str | None,
    key: str | None,
    psets: dict[str, Any] | None,
    numbering: dict[str, str] | None,
    summary: str | None,
) -> ProposalResult:
    check_json("psets", psets or {})
    command = CreateRecord(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        record_type=record_type,
        title=title,
        description=description,
        key=key,
        psets=psets or {},
        numbering=numbering or {},
    )
    line = summary or f"Create {record_type} {_short(title)!r} in {scope}"
    view = proposals.submit(
        ctx.factory, tool="create_record", agent=ctx.actor, command=command, summary=line
    )
    return _result(view)


def update_psets_impl(
    ctx: McpContext,
    *,
    record: str,
    scope: str | None,
    pset: str,
    layer: Literal["standard", "custom", "project"],
    values: dict[str, Any],
    expected_version: int | None,
    summary: str | None,
) -> ProposalResult:
    check_json("values", values)
    found = _envelope(ctx, record, scope)
    command = SetPsetValues(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=found["scope"],
        stream_id=found["id"],
        expected_version=expected_version if expected_version is not None else found["version"],
        pset=pset,
        layer=layer,
        values=values,
    )
    label = found["key"] or found["id"]
    line = summary or f"Set {pset} on {label}: {_short(', '.join(sorted(values)))}"
    view = proposals.submit(
        ctx.factory, tool="update_psets", agent=ctx.actor, command=command, summary=line
    )
    return _result(view)


def link_records_impl(
    ctx: McpContext,
    *,
    from_record: str,
    to_record: str,
    scope: str | None,
    relation: str | None,
    note: str | None,
    summary: str | None,
) -> ProposalResult:
    with ctx.factory(True) as uow:
        from_id = resolve_record_id(uow, from_record, scope)
        to_id = resolve_record_id(uow, to_record, scope)
        source_record = queries.get_record_by_id(uow, from_id)
    assert source_record is not None
    command = AddLink(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=source_record["scope"],
        from_id=from_id,
        to_id=to_id,
        relation=relation,
        note=note,
    )
    line = summary or f"Link {_short(from_record)} to {_short(to_record)}" + (
        f" ({relation})" if relation else ""
    )
    view = proposals.submit(
        ctx.factory, tool="link_records", agent=ctx.actor, command=command, summary=line
    )
    return _result(view)


def transition_workflow_impl(
    ctx: McpContext,
    *,
    record: str,
    scope: str | None,
    transition: str,
    expected_version: int | None,
    reason: str | None,
    summary: str | None,
) -> ProposalResult:
    found = _envelope(ctx, record, scope)
    command = TransitionWorkflow(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=found["scope"],
        stream_id=found["id"],
        expected_version=expected_version if expected_version is not None else found["version"],
        transition=transition,
        reason=reason,
    )
    label = found["key"] or found["id"]
    line = summary or f"Run transition {transition!r} on {label}"
    view = proposals.submit(
        ctx.factory, tool="transition_workflow", agent=ctx.actor, command=command, summary=line
    )
    return _result(view)


def post_feed_impl(ctx: McpContext, *, scope: str, body: str, importance: Importance) -> PostResult:
    command = PostToFeed(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        body=body,
        importance=importance,
    )
    with ctx.factory(False) as uow:
        result = handle_post(uow, command)
    return PostResult(
        post_id=result.stream_id,
        scope=scope,
        author=ctx.actor,
        suggested_links=sum(1 for e in result.events if e.event_type == "Link.Suggested"),
    )


def register_write_tools(server: MCPServer, ctx: McpContext, modes: dict[str, ToolMode]) -> None:
    """Add the five write tools to ``server``. ``modes`` is ``resolve_tool_modes()``'s answer."""
    assert set(modes) == set(PROPOSABLE_TOOLS) and set(modes.values()) == {"propose"}

    @server.tool(annotations=PROPOSES)
    def create_record(
        scope: Scope,
        title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)],
        record_type: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="Phase 0: `core.Record`.")
        ] = "core.Record",
        description: Annotated[str | None, Field(max_length=MAX_DESCRIPTION)] = None,
        key: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Leave empty to let numbering assign one."),
        ] = None,
        psets: Annotated[
            dict[str, Any] | None,
            Field(description="Initial property sets: `{pset: {property: value}}`."),
        ] = None,
        numbering: Annotated[
            dict[
                Annotated[str, Field(max_length=MAX_PART)],
                Annotated[str, Field(max_length=MAX_PART)],
            ]
            | None,
            Field(
                max_length=MAX_NUMBERING_ITEMS,
                description="Values for other numbering pattern fields, e.g. `{discipline: PIP}`.",
            ),
        ] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a new record. A person must accept the proposal before the record exists.

        The proposal is checked now with the rules that apply when it is accepted (duplicate key,
        unknown property set, scope), so an error here means it could not be applied.
        """
        with guarded(ctx, "create_record", resource_name("scope", scope)):
            return create_record_impl(
                ctx,
                scope=scope,
                title=title,
                record_type=record_type,
                description=description,
                key=key,
                psets=psets,
                numbering=numbering,
                summary=summary,
            )

    @server.tool(annotations=PROPOSES)
    def update_psets(
        record: RecordRef,
        pset: Annotated[
            str,
            Field(
                min_length=1, max_length=MAX_PART, description="Property set, e.g. `valve_data`."
            ),
        ],
        values: Annotated[
            dict[str, Any],
            Field(min_length=1, description="`{property: value}`; `null` clears a property."),
        ],
        scope: ScopeForKey = None,
        layer: Annotated[
            Literal["standard", "custom", "project"],
            Field(description="Which layer of the property set the values belong to."),
        ] = "standard",
        expected_version: ExpectedVersion = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose property values for a record. A person must accept before anything changes.

        Pass `expected_version` (from get_record) to say what you based the values on; the proposal
        fails on acceptance if the record changed since.
        """
        with guarded(ctx, "update_psets", resource_name("record", record)):
            return update_psets_impl(
                ctx,
                record=record,
                scope=scope,
                pset=pset,
                layer=layer,
                values=values,
                expected_version=expected_version,
                summary=summary,
            )

    @server.tool(annotations=PROPOSES)
    def link_records(
        from_record: RecordRef,
        to_record: RecordRef,
        scope: ScopeForKey = None,
        relation: Annotated[
            str | None,
            Field(
                max_length=MAX_PART,
                description="Forward relation code (`requires`, `references`); default: by type.",
            ),
        ] = None,
        note: Annotated[str | None, Field(max_length=MAX_NOTE)] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a link between two records. A person must accept before the link exists."""
        with guarded(ctx, "link_records", resource_name("record", from_record)):
            return link_records_impl(
                ctx,
                from_record=from_record,
                to_record=to_record,
                scope=scope,
                relation=relation,
                note=note,
                summary=summary,
            )

    @server.tool(annotations=PROPOSES)
    def transition_workflow(
        record: RecordRef,
        transition: Annotated[str, Field(min_length=1, max_length=MAX_PART)],
        scope: ScopeForKey = None,
        expected_version: ExpectedVersion = None,
        reason: Annotated[str | None, Field(max_length=MAX_NOTE)] = None,
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose a workflow transition. A person must accept before the record moves.

        Guards other than role checks are evaluated now; role guards are evaluated for the person
        who accepts, with the roles they hold.
        """
        with guarded(ctx, "transition_workflow", resource_name("record", record)):
            return transition_workflow_impl(
                ctx,
                record=record,
                scope=scope,
                transition=transition,
                expected_version=expected_version,
                reason=reason,
                summary=summary,
            )

    @server.tool(annotations=POSTS)
    def post_feed(
        scope: Scope,
        body: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_BODY_LENGTH,
                description="Text with `#tags` and `@mentions`; `#<record key>` suggests a link.",
            ),
        ],
        importance: Annotated[
            Importance, Field(description="`low`, `normal` or `high`.")
        ] = "normal",
    ) -> PostResult:
        """Post to a project's feed, labelled as you. This writes directly, no review.

        A post is a message, not a record: hashtags never change a record. A record tag only
        suggests a `references` link that a person accepts or declines.
        """
        with guarded(ctx, "post_feed", resource_name("scope", scope)):
            return post_feed_impl(ctx, scope=scope, body=body, importance=importance)
