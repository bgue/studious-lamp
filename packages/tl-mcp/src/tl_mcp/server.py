"""``build_server``: the MCP server, its tool schemas and its resources (§11.3, ADR-0005).

Six read tools (``search_records``, ``get_record``, ``get_links``, ``trace``, ``get_settings``,
``lake_query``), five tools that only *propose* a change (``create_record``, ``update_psets``,
``link_records``, ``transition_workflow``, ``propose_setting_change``) and ``post_feed``, which
posts directly, labelled with the agent
(``write_tools.py``). The actor is fixed per server (``--actor`` on the command line); every tool
and resource calls the shared ``authorize`` hook first (allow-all today). The read bodies live in
``tools.py`` and ``resources.py``; this module owns the read tools' names, parameter schemas, the
text agents read, and error handling.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_api.auth import authorize
from tl_api.tokens import check_actor
from tl_core.addable import AddableProperties
from tl_core.extypes.provider import attach as attach_extension_types
from tl_core.files.service import FileService
from tl_core.files.types import ObjectStore
from tl_core.modules import ModuleHookError, ModuleSpec, load_modules, refused_hook, resolve_hook
from tl_core.query.parser import MAX_QUERY_LENGTH
from tl_core.services.link_queries import LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_core.settings.views import SettingView
from tl_lake import LakeConfig, LakeQueryService
from tl_lake.guard import MAX_SQL_CHARS
from tl_mod_documents.derivation import store as derivation_store

from tl_mcp import resources, tools
from tl_mcp.context import Authorizer, McpContext, UowFactory
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.models import LakeQueryOutput, SearchResult
from tl_mcp.modes import resolve_tool_modes
from tl_mcp.thread_tools import register_thread_tools
from tl_mcp.type_tools import register_type_tools
from tl_mcp.write_tools import register_write_tools

INSTRUCTIONS = (
    "Access to a Throughline construction ledger. Records live in a scope: `company` or "
    "`project:<id>`. Read with `search_records` and the query language (for example "
    "`status:Review linked:NCR`), then `get_record`, `get_links` and `trace` with a record id or a "
    "key plus its scope. For analytics over everything (counts, trends, joins) use `lake_query`, "
    "read-only SQL over the lake copy; read `tl://lake/schema` for its tables first. You cannot "
    "change a record or a setting: `create_record`, `update_psets`, `link_records`, "
    "`transition_workflow` and `propose_setting_change` each file a proposal that a person "
    "reviews and accepts, and they return the pending proposal; read settings with "
    "`get_settings`. Each agent has a daily proposal budget. `post_feed` posts to a project feed "
    "directly, labelled as you. A company can add record types: `list_record_types` and "
    "`get_record_type` describe them, `get_record_body` reads the stored body of an "
    "object-backed record. `list_code_values`, `list_tag_classes` and `get_tag` read the "
    "engineering standards and a tag's conformance. Resources: tl://record/{scope}/{key}, "
    "tl://schema/{scope}/{record_type}, tl://types, tl://relations, tl://lake/schema."
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


_log = logging.getLogger("tl_mcp")


class _StagedServer:
    """What a module registrar sees as ``server``: tools are staged, not registered.

    ``tool`` and ``add_tool`` record the function and its keywords. Resources and prompts are
    refused (a module's concrete URI would beat a core template; SR-X4 F5): the registrar raises
    and ``_register_module_tools`` skips the module. Any other attribute is missing, so it is
    refused the same way. ``_register_module_tools`` checks the staged names and registers each
    function behind ``guarded`` (SR-X4 F1, F2).
    """

    def __init__(self) -> None:
        self.staged: list[tuple[str, Callable[..., Any], dict[str, Any]]] = []

    def tool(self, name: str | None = None, **kwargs: Any) -> Callable[[Any], Any]:
        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.add_tool(fn, name=name, **kwargs)
            return fn

        return decorate

    def add_tool(self, fn: Callable[..., Any], name: str | None = None, **kwargs: Any) -> None:
        self.staged.append((name or fn.__name__, fn, kwargs))

    def _refuse(self, *args: Any, **kwargs: Any) -> Any:
        raise ModuleHookError("a module may register tools only")

    resource = add_resource = prompt = add_prompt = _refuse


def _closed(ctx: McpContext, tool: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """``fn`` behind the access check: ``guarded(ctx, tool, ...)`` runs before its body."""

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def run_async(*args: Any, **kwargs: Any) -> Any:
            with guarded(ctx, tool, f"module:{tool}"):
                return await fn(*args, **kwargs)

        return run_async

    @functools.wraps(fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        with guarded(ctx, tool, f"module:{tool}"):
            return fn(*args, **kwargs)

    return run


def _register_module_tools(server: MCPServer, ctx: McpContext) -> None:
    """Register every installed module's tools (``ModuleSpec.tools``), module-name order.

    Called after every core tool is registered. Hooks are resolved once, before any registration.
    A module whose hook cannot be resolved, or that names a tool a core tool or an earlier module
    already has, registers none of its tools (fixed warning, no ref); the others still register.
    Each registered function runs ``guarded`` first, so a registrar that forgets it is still closed.
    """
    resolved: list[tuple[ModuleSpec, tuple[object, ...]]] = []
    for spec in load_modules():
        try:
            resolved.append((spec, resolve_hook(spec, "tools")))
        except ModuleHookError as exc:
            _log.warning("%s", exc)
    taken = {tool.name for tool in server._tool_manager.list_tools()}  # noqa: SLF001
    for spec, registrars in resolved:
        stage = _StagedServer()
        try:
            for register in registrars:
                register(stage, ctx)  # type: ignore[operator]
        except Exception:
            _log.warning("%s", refused_hook(spec, "tools"))
            continue
        names = [name for name, _, _ in stage.staged]
        if len(set(names)) != len(names) or taken.intersection(names):
            _log.warning("%s", refused_hook(spec, "tools"))
            continue
        for name, fn, kwargs in stage.staged:
            server.add_tool(_closed(ctx, name, fn), name=name, **kwargs)
        taken.update(names)


def build_server(
    factory: UowFactory,
    *,
    actor: str,
    authorize_hook: Authorizer = authorize,
    tool_modes: Mapping[str, str] | None = None,
    lake_dir: str | Path | None = None,
    object_store: ObjectStore | None = None,
    files: FileService | None = None,
) -> MCPServer:
    """An MCP server over ``factory`` acting as ``actor`` (``agent:<id>`` or ``user:<id>``).

    ``tool_modes`` maps a record-changing tool to its mode. The only mode is ``propose``; asking for
    ``write`` raises ``ToolModeError`` with the human-gate message (see ``tl_mcp.modes``).
    ``lake_dir`` is the DuckLake directory ``lake_query`` reads (default ``TL_LAKE_DIR``, else
    ``./dev/data/lake``). The lake is opened per call, so it may not exist yet. ``object_store``
    holds the bodies of object-backed extension records (default: none, so body reads say so).
    ``files`` is the file service the derivation tools read rows and reports with (default: none).
    The registered extension types of ``factory``'s ledger join the effective schema.
    """
    check_actor(actor)
    if files is not None:  # rows and reports of derived documents are files (ADR-0014)
        derivation_store.configure(files)
    attach_extension_types(factory, prime=True)
    modes = resolve_tool_modes(tool_modes)
    lake = LakeQueryService(
        LakeConfig.at(lake_dir),
        default_limit=LAKE_DEFAULT_LIMIT,
        max_limit=LAKE_MAX_LIMIT,
        max_bytes=LAKE_MAX_BYTES,
    )
    ctx = McpContext(
        factory=factory, actor=actor, authorize=authorize_hook, lake=lake, objects=object_store
    )
    server = MCPServer("throughline", instructions=INSTRUCTIONS)
    register_write_tools(server, ctx, modes)
    register_type_tools(server, ctx)
    register_thread_tools(server, ctx)  # P1-I7 WS-B

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
    def get_addable_properties(record: RecordRef, scope: ScopeForKey = None) -> AddableProperties:
        """What could be added to a record: the standard properties its type allows and it has no
        value for, the optional property sets its project has not adopted (an agent cannot adopt
        one; a person with the right does), and each set's custom-section rule (whether it takes
        custom fields, the most, how many are held, and the rule for a name). Propose a value
        with `update_psets`; a custom field is `layer: custom` with the key `x.<name>`."""
        with guarded(ctx, "get_addable_properties", resource_name("record", record)):
            return tools.get_addable_properties_impl(ctx, record=record, scope=scope)

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
    def get_settings(
        key: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="One setting, e.g. `feed.reactions.enabled`."),
        ] = None,
        prefix: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Only settings whose key starts with this."),
        ] = None,
        project: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="View as this project (an id such as `P123`)."),
        ] = None,
        modified_only: Annotated[
            bool, Field(description="Only settings set at the project (company when none).")
        ] = False,
    ) -> list[SettingView]:
        """Read settings: each with its definition (type, description, risk, effect, scopes) and its
        effective value, the layer it comes from, whether it is set at the viewed layer, whether the
        company locked or bounded it, and changes scheduled for later.

        You cannot change a setting: `propose_setting_change` files a proposal that a person
        accepts. A `dangerous` or `advanced` key needs a reason in the proposal.
        """
        with guarded(ctx, "get_settings", resource_name("setting", key or prefix or "*")):
            return tools.get_settings_impl(
                ctx, key=key, prefix=prefix, project=project, modified_only=modified_only
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

    _register_module_tools(server, ctx)  # last: a module never shadows a core tool
    return server
