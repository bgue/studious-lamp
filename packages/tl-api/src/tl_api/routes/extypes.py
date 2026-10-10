# ruff: noqa: F401  (STUB P0-I8-T21: delete this line when the unused imports are gone)
"""Extension types over HTTP: the registry, instances of a type, and object-backed bodies.

Brief 31.3 ("generic API"). The registry is read-only here: registering a package is `tl types sync`
(an operator action on the files), not a request. Instances are records, so reading them is
`GET /records?record_type=co.acme.LiftPlan` and the query language, as for any record; this module
adds what an extension type needs on top:

* ``GET /types`` and ``GET /types/{type_ref}``: the registrations, and one with its generated form;
* ``POST /types/{type_name}/records``: create an instance (psets for a managed type, a body for an
  object-backed one, in one unit of work);
* ``GET /records/{record_id}/body`` and ``PUT /records/{record_id}/body``: read the verified body,
  store a new one. A body that fails verification is answered 502 ``body_hash_mismatch`` and the
  record is quarantined; later reads are 403 ``body_quarantined``.

Writes are record changes, so an ``agent:`` token gets 403 ``agent_must_propose`` (FANOUT D3).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from tl_core.extypes import body as bodies
from tl_core.extypes import registry
from tl_core.extypes.errors import BodyNotFoundError
from tl_core.extypes.service import BodyView, TypeDetail, TypeSummary, summarise, type_detail
from tl_core.extypes.types import BodyPointer, TypeStatus
from tl_core.files.types import ObjectStore
from tl_core.services import queries
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.records import handle_create_record

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError

router = APIRouter(tags=["extension types"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("type.read"))]
Writer = Annotated[str, Depends(guard("record.write", changes_records=True))]
API_SOURCE = "api"


class PutBodyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Annotated[str, Field(min_length=1, max_length=128)]
    body: dict[str, Any]
    expected_version: int | None = Field(
        default=None, ge=1, description="The record version the editor saw; a newer one is a 409."
    )


class BodyStoredOut(BaseModel):
    pointer: BodyPointer
    version: int


class CreateInstanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Annotated[str, Field(min_length=1, max_length=128)]
    title: Annotated[str, Field(min_length=1, max_length=500)]
    key: Annotated[str | None, Field(max_length=128)] = None
    description: Annotated[str | None, Field(max_length=10_000)] = None
    psets: dict[str, Any] = Field(default_factory=dict, description="Managed: initial values.")
    body: dict[str, Any] | None = Field(default=None, description="Object-backed types: the body.")
    numbering: dict[str, str] = Field(default_factory=dict)


def _objects(ctx: ApiContext) -> ObjectStore:
    # Return ctx.objects. When it is None raise ApiError(503, "unavailable", "no object store is
    # configured for record bodies").
    raise NotImplementedError("STUB (P0-I8-T21)")


@router.get("/types", operation_id="list_types")
def list_types(
    ctx: Ctx,
    actor: Reader,
    status: Annotated[TypeStatus | None, Query(description="Only this status.")] = None,
) -> list[TypeSummary]:
    """Registered extension type versions, by type ref."""
    # Open ctx.backend(True) as uow. Return [summarise(v) for v in registry.list_types(uow.conn(),
    # status=status)].
    raise NotImplementedError("STUB (P0-I8-T21)")


@router.get("/types/{type_ref}", operation_id="get_type")
def get_type(ctx: Ctx, actor: Reader, type_ref: str) -> TypeDetail:
    """One version with its generated form, or why it was quarantined. 404 when unknown."""
    # Open ctx.backend(True) as uow and return type_detail(uow, type_ref). It raises
    # UnknownTypeError, which the error table maps to 404.
    raise NotImplementedError("STUB (P0-I8-T21)")


@router.post("/types/{type_name}/records", operation_id="create_instance")
def create_instance(
    ctx: Ctx, actor: Writer, type_name: str, request: CreateInstanceIn
) -> CommandResult:
    """Create an instance of an extension type; the token's actor is recorded."""
    # Build CreateRecord(actor=actor, source=API_SOURCE, scope=request.scope,
    # record_type=type_name, title=request.title, key=request.key,
    # description=request.description, psets=request.psets, numbering=request.numbering). Open
    # ctx.backend(False) as uow. When request.body is None return handle_create_record(uow,
    # command). Otherwise return bodies.create_extension_record(uow, _objects(ctx), command,
    # request.body). Call _objects only on the body path, so a managed type works without an
    # object store.
    raise NotImplementedError("STUB (P0-I8-T21)")


@router.get("/records/{record_id}/body", operation_id="get_record_body")
def get_record_body(ctx: Ctx, actor: Reader, record_id: str) -> BodyView:
    """The verified body of an object-backed record."""
    # store = _objects(ctx) first. In ctx.backend(True) read bodies.body_pointer(uow.conn(),
    # record_id). When it is None raise BodyNotFoundError(f"record {record_id!r} has no stored
    # body"). Then stored = bodies.read_body(ctx.backend, store, stream_id=record_id), outside the
    # unit of work: it opens its own and records the quarantine when the object fails
    # verification. Return BodyView(record_id=record_id, pointer=pointer, body=stored).
    raise NotImplementedError("STUB (P0-I8-T21)")


@router.put("/records/{record_id}/body", operation_id="put_record_body")
def put_record_body(
    ctx: Ctx, actor: Writer, record_id: str, request: PutBodyIn, response: Response
) -> BodyStoredOut:
    """Validate and store a new body; the index fields follow. 422 `body_invalid` lists problems."""
    # store = _objects(ctx) first. In one ctx.backend(False) block: row =
    # queries.get_record_by_id(uow, record_id). When row is None or row['scope'] != request.scope
    # raise RecordNotFoundError(f"no record {record_id!r} in scope {request.scope!r}"). pointer =
    # bodies.store_body(uow, store, stream_id=record_id, body=request.body, actor=actor,
    # source=API_SOURCE, expected_version=request.expected_version). Read the record again with
    # get_record_by_id. Set the ETag header to f'"{version}"' with the record's version after the
    # write. Return BodyStoredOut(pointer=pointer, version=version).
    raise NotImplementedError("STUB (P0-I8-T21)")
