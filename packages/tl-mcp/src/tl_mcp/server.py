"""``build_server``: the MCP server, its tool schemas and its resources (§11.3, ADR-0005).

Phase 0 has read tools only (``search_records``, ``get_record``, ``get_links``, ``trace``); write
tools are propose-only and arrive in P0-I6. The actor is fixed per server (``--actor`` on the
command line); every tool and resource calls the shared ``authorize`` hook first (allow-all
today). The bodies live in ``tools.py`` and ``resources.py``; this module owns names, parameter
schemas, the text agents read, and error handling.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_api.auth import authorize
from tl_api.tokens import check_actor
from tl_core.services.link_queries import LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode

from tl_mcp import resources, tools
from tl_mcp.context import Authorizer, McpContext, UowFactory
from tl_mcp.errors import guarded
from tl_mcp.models import SearchResult

INSTRUCTIONS = (
    "Read-only access to a Throughline construction ledger. Records live in a scope: `company` or "
    "`project:<id>`. Use `search_records` with the query language (for example "
    "`status:Review linked:NCR`), then `get_record`, `get_links` and `trace` with a record id or a "
    "key plus its scope. Resources: tl://record/{scope}/{key}, tl://schema/{scope}/{record_type}, "
    "tl://relations."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Scope = Annotated[str, Field(description="`company` or `project:<id>`, e.g. `project:P123`.")]
RecordRef = Annotated[
    str, Field(description="A record id (ULID), or a record key such as `P123-NCR-0042`.")
]
ScopeForKey = Annotated[
    str | None, Field(description="The scope of the key. Required when `record` is a key.")
]


def build_server(
    factory: UowFactory, *, actor: str, authorize_hook: Authorizer = authorize
) -> MCPServer:
    """An MCP server over ``factory`` acting as ``actor`` (``agent:<id>`` or ``user:<id>``)."""
    check_actor(actor)
    ctx = McpContext(factory=factory, actor=actor, authorize=authorize_hook)
    server = MCPServer("throughline", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    def search_records(
        scope: Scope,
        q: Annotated[
            str,
            Field(
                description="Filter in the query language; empty lists every record of the scope."
            ),
        ] = "",
        limit: Annotated[int, Field(ge=1, le=500, description="Page size.")] = 50,
        offset: Annotated[int, Field(ge=0)] = 0,
        order_by: Annotated[
            str | None,
            Field(description="Comma-separated `column[:asc|:desc]`, e.g. `updated_at:desc`."),
        ] = None,
    ) -> SearchResult:
        """Find records with the Throughline query language (the same one the TUI filter bar uses).

        Examples: `status:open`, `title~bevel`, `psets.valve_data.size_in>=2`,
        `linked:NCR`, `count(linked:NCR)>0`, `missing(link:permit)`, `-status:void`, `a or b`.
        Returns one page of record envelopes and the total number of matches. A syntax error is
        reported with its character position.
        """
        with guarded(ctx, "search_records", scope):
            return tools.search_records_impl(
                ctx, scope=scope, q=q, limit=limit, offset=offset, order_by=order_by
            )

    @server.tool(annotations=READ_ONLY)
    def get_record(record: RecordRef, scope: ScopeForKey = None) -> dict[str, object]:
        """Get one record: its envelope with title, status, psets, version and conformance."""
        with guarded(ctx, "get_record", record):
            return tools.get_record_impl(ctx, record=record, scope=scope)

    @server.tool(annotations=READ_ONLY)
    def get_links(
        record: RecordRef,
        scope: ScopeForKey = None,
        include_retracted: Annotated[bool, Field(description="Also list retracted links.")] = False,
    ) -> list[LinkView]:
        """List a record's links in both directions, with each relation label as read from it."""
        with guarded(ctx, "get_links", record):
            return tools.get_links_impl(
                ctx, record=record, scope=scope, include_retracted=include_retracted
            )

    @server.tool(annotations=READ_ONLY)
    def trace(
        record: RecordRef,
        scope: ScopeForKey = None,
        depth: Annotated[int, Field(ge=0, le=6, description="How many link hops to follow.")] = 2,
        direction: Annotated[
            TraceDirection, Field(description="Follow `out`bound, `in`bound or `both` links.")
        ] = "both",
    ) -> TraceNode:
        """Trace the records reachable through links as a tree (for example deficiency to weld)."""
        with guarded(ctx, "trace", record):
            return tools.trace_impl(
                ctx, record=record, scope=scope, depth=depth, direction=direction
            )

    @server.resource(
        "tl://record/{scope}/{key}",
        name="record",
        title="Record with its links",
        description="A record by scope and key, with its links, as JSON.",
        mime_type="application/json",
    )
    def record_resource(scope: str, key: str) -> str:
        with guarded(ctx, "resource.record", f"{scope}/{key}", error=ResourceError):
            return resources.record_resource(ctx, scope=scope, key=key)

    @server.resource(
        "tl://schema/{scope}/{record_type}",
        name="schema",
        title="Form schema of a record type",
        description="Fields and psets of a record type under the scope's effective schema.",
        mime_type="application/json",
    )
    def schema_resource(scope: str, record_type: str) -> str:
        with guarded(ctx, "resource.schema", f"{scope}/{record_type}", error=ResourceError):
            return resources.schema_resource(ctx, scope=scope, record_type=record_type)

    @server.resource(
        "tl://relations",
        name="relations",
        title="Link relations",
        description="The relation vocabulary with forward and inverse labels.",
        mime_type="application/json",
    )
    def relations_resource() -> str:
        with guarded(ctx, "resource.relations", "tl://relations", error=ResourceError):
            return resources.relations_resource(ctx)

    return server
