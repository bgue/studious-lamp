"""Extension type tools and resources: list and read the types, read an object-backed body.

Brief 31.3 ("generic ... MCP tools"). All three tools are read-only. Creating an instance stays
what it is for every record type: `create_record` with `record_type="<ns>.<Name>"` records a
*proposal* that a person accepts (FANOUT D3); it works for a managed type (its `psets` are the
values). An object-backed type needs a body, and a proposal carries none yet, so `create_record`
answers that it is object-backed: such records are created through the API, the CLI or the TUI
(a proposable `store_body` is a follow-up).
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_core.extypes import body as bodies
from tl_core.extypes import registry
from tl_core.extypes.errors import BodyNotFoundError
from tl_core.extypes.service import BodyView, TypeDetail, TypeSummary, summarise, type_detail
from tl_core.extypes.types import TypeStatus

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.resources import dump
from tl_mcp.tools import resolve_record_id

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
NO_STORE = "no object store is configured on this server, so record bodies cannot be read"


def list_record_types_impl(ctx: McpContext, *, status: TypeStatus | None) -> list[TypeSummary]:
    """Registered extension type versions, optionally of one status, by type ref.

    One read-only unit of work (``ctx.factory(True)``); ``registry.list_types(uow.conn(),
    status=status)``; each view through ``summarise``.
    """
    with ctx.factory(True) as uow:
        views = registry.list_types(uow.conn(), status=status)
    return [summarise(view) for view in views]


def get_record_type_impl(ctx: McpContext, *, type_ref: str) -> TypeDetail:
    """One registered version with its generated form (``type_detail``).

    Raises ``UnknownTypeError`` (mapped by ``guarded``) when there is no such registration.
    """
    with ctx.factory(True) as uow:
        return type_detail(uow, type_ref)


def get_record_body_impl(ctx: McpContext, *, record: str, scope: str | None) -> BodyView:
    """The verified body of an object-backed record, with the pointer it was verified against.

    ``ctx.objects`` ``None``: raise ``ValueError(NO_STORE)``. Otherwise, in a read-only unit of
    work, ``resolve_record_id(uow, record, scope)`` and ``bodies.body_pointer(uow.conn(), id)``
    (``BodyNotFoundError`` when there is none); then ``bodies.read_body(ctx.factory, ctx.objects,
    stream_id=id)``, which quarantines the record when the object fails verification and raises
    ``BodyHashMismatchError`` (mapped by ``guarded``).
    """
    if ctx.objects is None:
        raise ValueError(NO_STORE)
    with ctx.factory(True) as uow:
        record_id = resolve_record_id(uow, record, scope)
        pointer = bodies.body_pointer(uow.conn(), record_id)
    if pointer is None:
        raise BodyNotFoundError(f"record {record_id!r} has no stored body")
    body = bodies.read_body(ctx.factory, ctx.objects, stream_id=record_id)
    return BodyView(record_id=record_id, pointer=pointer, body=body)


def types_resource(ctx: McpContext) -> str:
    """The registered versions as JSON (``list_record_types_impl`` with no status)."""
    return dump([row.model_dump(mode="json") for row in list_record_types_impl(ctx, status=None)])


def type_resource(ctx: McpContext, *, type_ref: str) -> str:
    """One version with its form as JSON (``get_record_type_impl``)."""
    return dump(get_record_type_impl(ctx, type_ref=type_ref).model_dump(mode="json"))


TypeRef = Annotated[
    str,
    Field(
        min_length=3,
        max_length=MAX_PART,
        description="Type version, for example `co.acme.LiftPlan@1.0.0`.",
    ),
]


def register_type_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the three read tools and two resources to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_record_types(
        status: Annotated[
            Literal["active", "quarantined", "deprecated"] | None,
            Field(description="Only types with this status; empty lists every version."),
        ] = None,
    ) -> list[TypeSummary]:
        """List the extension record types (brief 31): `co.acme.LiftPlan` and the like.

        Each entry is a registered version with its status, where its instances keep their body
        (`managed`: in the ledger; `object-backed`: in the object store) and its index fields,
        the only body fields the query language can filter. To create an instance, call
        `create_record` with `record_type` set to the type name (managed types only).
        """
        with guarded(ctx, "list_record_types", resource_name("types", status or "all")):
            return list_record_types_impl(ctx, status=status)

    @server.tool(annotations=READ_ONLY)
    def get_record_type(type_ref: TypeRef) -> TypeDetail:
        """Get one extension type version: its state, and its form (every field, grouped).

        A quarantined version has no form; its `report` says why it was refused.
        """
        with guarded(ctx, "get_record_type", resource_name("type", type_ref)):
            return get_record_type_impl(ctx, type_ref=type_ref)

    @server.tool(annotations=READ_ONLY)
    def get_record_body(
        record: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="Record id or key.")
        ],
        scope: Annotated[
            str | None,
            Field(max_length=MAX_PART, description="Needed when `record` is a key."),
        ] = None,
    ) -> BodyView:
        """Get the body of an object-backed record, verified against its recorded hash.

        A body that fails verification is never returned: the record is quarantined and the call
        fails. The index fields are also in the record's psets (`get_record`).
        """
        with guarded(ctx, "get_record_body", resource_name("record", record)):
            return get_record_body_impl(ctx, record=record, scope=scope)

    @server.resource(
        "tl://types",
        name="types",
        title="Extension record types",
        description="Every registered extension type version, as JSON.",
        mime_type="application/json",
    )
    def types_resource_handler() -> str:
        with guarded(ctx, "resource.types", "tl://types", error=ResourceError):
            return types_resource(ctx)

    @server.resource(
        "tl://types/{type_ref}",
        name="type",
        title="Extension record type",
        description="One extension type version with its generated form, as JSON.",
        mime_type="application/json",
    )
    def type_resource_handler(type_ref: str) -> str:
        with guarded(
            ctx,
            "resource.type",
            resource_name("type", type_ref),
            error=ResourceError,
            parts=[("type_ref", type_ref)],
        ):
            return type_resource(ctx, type_ref=type_ref)
