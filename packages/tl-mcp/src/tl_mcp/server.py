"""``build_server``: the MCP server, its tool schemas and its resources (§11.3, ADR-0005).

Phase 0 has read tools only (``search_records``, ``get_record``, ``get_links``, ``trace``); write
tools are propose-only and arrive in P0-I6. The actor is fixed per server (``--actor`` on the
command line); every tool and resource calls the shared ``authorize`` hook first (allow-all
today). The bodies live in ``tools.py`` and ``resources.py``; this module owns names, parameter
schemas, the text agents read, and error handling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_api.auth import authorize
from tl_api.tokens import check_actor
from tl_core.query.parser import MAX_QUERY_LENGTH
from tl_core.services.link_queries import LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_lake import LakeConfig, LakeQueryService
from tl_lake.guard import MAX_SQL_CHARS

from tl_mcp import resources, tools
from tl_mcp.context import Authorizer, McpContext, UowFactory
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.models import LakeQueryOutput, SearchResult

INSTRUCTIONS = (
    "Read-only access to a Throughline construction ledger. Records live in a scope: `company` or "
    "`project:<id>`. Use `search_records` with the query language (for example "
    "`status:Review linked:NCR`), then `get_record`, `get_links` and `trace` with a record id or a "
    "key plus its scope. For analytics over everything (counts, trends, joins) use `lake_query`, "
    "read-only SQL over the lake copy; read `tl://lake/schema` for its tables first. Resources: "
    "tl://record/{scope}/{key}, tl://schema/{scope}/{record_type}, tl://relations, "
    "tl://lake/schema."
)

LAKE_DEFAULT_LIMIT = 100
LAKE_MAX_LIMIT = 1000
LAKE_MAX_BYTES = 1024 * 1024  # an agent's context is smaller than the service's own 8 MiB cap

MAX_ORDER_BY = 256

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

MAX_QUERY = MAX_QUERY_LENGTH  # the query parser's own limit: longer text could never parse
Scope = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PART,
        description="`company` or `project:<id>`, e.g. `project:P123`.",
    ),
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
    Field(
        max_length=MAX_PART, description="The scope of the key. Required when `record` is a key."
    ),
]


def build_server(
    factory: UowFactory,
    *,
    actor: str,
    authorize_hook: Authorizer = authorize,
    lake_dir: str | Path | None = None,
) -> MCPServer:
    """An MCP server over ``factory`` acting as ``actor`` (``agent:<id>`` or ``user:<id>``).

    ``lake_dir`` is the DuckLake directory ``lake_query`` reads (default ``TL_LAKE_DIR``, else
    ``./dev/data/lake``). The lake is opened per call, so it may not exist yet.
    """
    check_actor(actor)
    lake = LakeQueryService(
        LakeConfig.at(lake_dir),
        default_limit=LAKE_DEFAULT_LIMIT,
        max_limit=LAKE_MAX_LIMIT,
        max_bytes=LAKE_MAX_BYTES,
    )
    ctx = McpContext(factory=factory, actor=actor, authorize=authorize_hook, lake=lake)
    server = MCPServer("throughline", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    def search_records(
        scope: Scope,
        q: Annotated[
            str,
            Field(
                max_length=MAX_QUERY,
                description="Filter in the query language; empty lists every record of the scope.",
            ),
        ] = "",
        limit: Annotated[int, Field(ge=1, le=500, description="Page size.")] = 50,
        offset: Annotated[int, Field(ge=0)] = 0,
        order_by: Annotated[
            str | None,
            Field(
                max_length=MAX_ORDER_BY,
                description="Comma-separated `column[:asc|:desc]`, e.g. `updated_at:desc`.",
            ),
        ] = None,
    ) -> SearchResult:
        """Find records with the Throughline query language (the same one the TUI filter bar uses).

        Examples: `status:open`, `title~bevel`, `psets.valve_data.size_in>=2`,
        `linked:NCR`, `count(linked:NCR)>0`, `missing(link:permit)`, `-status:void`, `a or b`.
        Returns one page of record envelopes and the total number of matches. A syntax error is
        reported with its character position.
        """
        with guarded(ctx, "search_records", resource_name("scope", scope)):
            return tools.search_records_impl(
                ctx, scope=scope, q=q, limit=limit, offset=offset, order_by=order_by
            )

    @server.tool(annotations=READ_ONLY)
    def get_record(record: RecordRef, scope: ScopeForKey = None) -> dict[str, object]:
        """Get one record: its envelope with title, status, psets, version and conformance."""
        with guarded(ctx, "get_record", resource_name("record", record)):
            return tools.get_record_impl(ctx, record=record, scope=scope)

    @server.tool(annotations=READ_ONLY)
    def get_links(
        record: RecordRef,
        scope: ScopeForKey = None,
        include_retracted: Annotated[bool, Field(description="Also list retracted links.")] = False,
    ) -> list[LinkView]:
        """List a record's links in both directions, with each relation label as read from it."""
        with guarded(ctx, "get_links", resource_name("record", record)):
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
        with guarded(ctx, "trace", resource_name("record", record)):
            return tools.trace_impl(
                ctx, record=record, scope=scope, depth=depth, direction=direction
            )

    @server.tool(annotations=READ_ONLY)
    def lake_query(
        sql: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_SQL_CHARS,
                description="One SELECT statement over the lake tables (see tl://lake/schema).",
            ),
        ],
        limit: Annotated[
            int, Field(ge=1, le=LAKE_MAX_LIMIT, description="Maximum rows to return.")
        ] = LAKE_DEFAULT_LIMIT,
    ) -> LakeQueryOutput:
        """Run read-only SQL over the analytics copy of the ledger (the DuckLake lake).

        Tables: `events` (bronze, every ledger event), `cur_core_record`, `links` and
        `pset_values` (silver, the current state, including promoted `pset__<pset>__<property>`
        columns) and `_tl_sync` (one row per sync). Only one SELECT (or WITH ... SELECT) is
        allowed: no DDL, DML, ATTACH, INSTALL, LOAD, COPY, PRAGMA, SET or stacked statements, and
        no file functions such as `read_csv`. The answer says which ledger seq the lake reflected
        (`as_of_seq`), and the lake can be behind the ledger until the next sync. Time travel:
        `FROM cur_core_record AT (VERSION => <snapshot_id>)`. Rows are limited (default 100, at most
        1000) and the size of the answer is capped; `truncated` says when rows were left out. Every
        call is logged with your actor.
        """
        with guarded(ctx, "lake_query", resource_name("lake", "main")):
            return tools.lake_query_impl(ctx, sql=sql, limit=limit)

    @server.resource(
        "tl://lake/schema",
        name="lake_schema",
        title="Lake tables and columns",
        description="The tables and columns `lake_query` can read, as JSON.",
        mime_type="application/json",
    )
    def lake_schema_resource() -> str:
        with guarded(ctx, "resource.lake_schema", "tl://lake/schema", error=ResourceError):
            return resources.lake_schema_resource(ctx)

    @server.resource(
        "tl://record/{scope}/{key}",
        name="record",
        title="Record with its links",
        description="A record by scope and key, with its links, as JSON.",
        mime_type="application/json",
    )
    def record_resource(scope: str, key: str) -> str:
        with guarded(
            ctx,
            "resource.record",
            resource_name("record", scope, key),
            error=ResourceError,
            parts=[("scope", scope), ("key", key)],
        ):
            return resources.record_resource(ctx, scope=scope, key=key)

    @server.resource(
        "tl://schema/{scope}/{record_type}",
        name="schema",
        title="Form schema of a record type",
        description="Fields and psets of a record type under the scope's effective schema.",
        mime_type="application/json",
    )
    def schema_resource(scope: str, record_type: str) -> str:
        with guarded(
            ctx,
            "resource.schema",
            resource_name("schema", scope, record_type),
            error=ResourceError,
            parts=[("scope", scope), ("record_type", record_type)],
        ):
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
