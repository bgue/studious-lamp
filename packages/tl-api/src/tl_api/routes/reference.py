"""Reference reads: relations, key detection, workflow status, form metadata, conformance.

STUB (P0-I4-T42): the route bodies below raise ``NotImplementedError``. Signatures, decorators,
parameters and response models are final (the committed OpenAPI document depends on them);
implement the bodies only, then delete this paragraph.

Thin: one tl_core call per route. These are what a remote client needs besides records and links
to run the same screens as an embedded one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.numbering.detect import KeyChip
from tl_core.services.workflow import WorkflowStatus
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx
from tl_api.models import DefaultRelationOut, DetectKeysBody, RelationOut

router = APIRouter(tags=["reference"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("reference.read"))]


@router.get("/relations", operation_id="list_relations")
def list_relations(ctx: Ctx, actor: Reader) -> list[RelationOut]:
    """The relation vocabulary in display order."""
    raise NotImplementedError("STUB (P0-I4-T42)")


@router.get("/relations/default", operation_id="get_default_relation")
def get_default_relation(
    ctx: Ctx,
    actor: Reader,
    from_type: Annotated[str, Query()],
    to_type: Annotated[str, Query()],
) -> DefaultRelationOut:
    """The relation to pre-select when linking a record of `from_type` to one of `to_type`."""
    raise NotImplementedError("STUB (P0-I4-T42)")


@router.post("/keys/detect", operation_id="detect_keys")
def detect_keys(ctx: Ctx, actor: Reader, body: DetectKeysBody) -> list[KeyChip]:
    """Keys found in the text that fit a numbering pattern of the scope, resolved to records."""
    raise NotImplementedError("STUB (P0-I4-T42)")


@router.get("/records/{record_id}/workflow", operation_id="get_workflow_status")
def get_workflow_status(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    role: Annotated[list[str] | None, Query(description="Roles for the role guards.")] = None,
) -> WorkflowStatus:
    """State, state-entered time and every transition with its guard results."""
    raise NotImplementedError("STUB (P0-I4-T42)")


@router.get("/schema/forms", operation_id="get_form_metadata")
def get_form_metadata(
    ctx: Ctx,
    actor: Reader,
    scope: Annotated[str, Query()],
    record_type: Annotated[str, Query()],
) -> FormMetadata:
    """Form and grid metadata for a record type under the scope's effective schema."""
    raise NotImplementedError("STUB (P0-I4-T42)")


@router.get("/records/{record_id}/conformance", operation_id="get_conformance")
def get_conformance(ctx: Ctx, actor: Reader, record_id: str) -> ConformanceReport:
    """Conformance of the record's current values against its scope's effective schema."""
    raise NotImplementedError("STUB (P0-I4-T42)")
