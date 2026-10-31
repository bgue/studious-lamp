"""What the caller may do on a record now (P1-UX2-S1; ADR-0010 addendum, ADR-0016).

``GET /records/{record_id}/addable-properties`` (P1-UX3 round 4) is the same kind of read: what the
caller could still add to the record (``tl_core.addable``).

``GET /records/{record_id}/actions`` asks the module that owns the record's type
(``tl_core.actions.allowed_actions``). It is a read, so the caller needs the reader's access
(`record.read`); what it offers follows the caller's own roles, built from the principal exactly as
the accept route of a proposal builds it. A record the caller may not read answers as one that does
not exist (404 `record_not_found`, the same body), and an agent is offered nothing: agents propose,
they never change a record. An offer is advice for a screen; the command route still checks the
state and the access when it runs. The access words come from the module role table at the
record's own project (ADR-0021), so the list offers nothing the command route would refuse for
lack of the word.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from tl_core.actions import RecordActions, allowed_actions
from tl_core.addable import AddableProperties, addable_properties
from tl_core.auth.module_roles import holder_for_principal
from tl_core.auth.types import Principal

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.routes.proposals import holds_access

router = APIRouter(tags=["records"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("record.read"))]
Who = Annotated[Principal, Depends(current_principal)]


@router.get("/records/{record_id}/actions", operation_id="get_record_actions")
def get_record_actions(ctx: Ctx, actor: Reader, principal: Who, record_id: str) -> RecordActions:
    """The commands of the record's module that the caller may run on it now, with plain labels.

    404 `record_not_found` when the record is missing or the caller may not read it; an agent token
    gets an empty list.
    """
    with ctx.backend(True) as uow:
        return allowed_actions(
            uow,
            record_id,
            actor=actor,
            holds=lambda level: holds_access(principal, actor, level),
            holder=holder_for_principal(principal),
        )


@router.get("/records/{record_id}/addable-properties", operation_id="get_record_addable_properties")
def get_record_addable_properties(
    ctx: Ctx, actor: Reader, principal: Who, record_id: str
) -> AddableProperties:
    """What could be added to the record: the standard properties its type allows and it lacks, the
    optional sets the project has not adopted (and whether the caller may adopt them, with
    `POST /commands/AdoptSchemaPackage`), and each set's custom-section rule.

    404 `record_not_found` when the record is missing or the caller may not read it. Writing the
    values is `POST /commands/SetPsetValues`, which checks everything again.
    """
    with ctx.backend(True) as uow:
        return addable_properties(
            uow,
            record_id,
            actor=actor,
            holds=lambda level: holds_access(principal, actor, level),
            holder=holder_for_principal(principal),
        )
