"""Reference reads: relations, key detection, workflow status, form metadata, conformance.

Thin: one tl_core call per route. These are what a remote client needs besides records and links
to run the same screens as an embedded one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.links.provider import get_vocabulary
from tl_core.links.vocabulary import default_relation
from tl_core.numbering.detect import KeyChip, suggest_chips
from tl_core.services import psets
from tl_core.services.workflow import WorkflowStatus, workflow_status
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
    vocabulary = get_vocabulary()
    out: list[RelationOut] = []
    for code in vocabulary.codes():
        r = vocabulary.get(code)
        out.append(
            RelationOut(
                code=r.code,
                label=r.label,
                inverse_code=r.inverse_code,
                inverse_label=r.inverse_label,
            )
        )
    return out


@router.get("/relations/default", operation_id="get_default_relation")
def get_default_relation(
    ctx: Ctx,
    actor: Reader,
    from_type: Annotated[str, Query()],
    to_type: Annotated[str, Query()],
) -> DefaultRelationOut:
    """The relation to pre-select when linking a record of `from_type` to one of `to_type`."""
    return DefaultRelationOut(relation=default_relation(from_type, to_type))


@router.post("/keys/detect", operation_id="detect_keys")
def detect_keys(ctx: Ctx, actor: Reader, body: DetectKeysBody) -> list[KeyChip]:
    """Keys found in the text that fit a numbering pattern of the scope, resolved to records."""
    with ctx.backend(True) as uow:
        return suggest_chips(uow, body.scope, body.text, linked_to=body.linked_to)


@router.get("/records/{record_id}/workflow", operation_id="get_workflow_status")
def get_workflow_status(
    ctx: Ctx,
    actor: Reader,
    record_id: str,
    role: Annotated[list[str] | None, Query(description="Roles for the role guards.")] = None,
) -> WorkflowStatus:
    """State, state-entered time and every transition with its guard results."""
    with ctx.backend(True) as uow:
        return workflow_status(uow, record_id, roles=tuple(role or ()))


@router.get("/schema/forms", operation_id="get_form_metadata")
def get_form_metadata(
    ctx: Ctx,
    actor: Reader,
    scope: Annotated[str, Query()],
    record_type: Annotated[str, Query()],
) -> FormMetadata:
    """Form and grid metadata for a record type under the scope's effective schema."""
    with ctx.backend(True) as uow:
        return psets.form_metadata(uow, scope, record_type)


@router.get("/records/{record_id}/conformance", operation_id="get_conformance")
def get_conformance(ctx: Ctx, actor: Reader, record_id: str) -> ConformanceReport:
    """Conformance of the record's current values against its scope's effective schema."""
    with ctx.backend(True) as uow:
        return psets.conformance(uow, record_id)
