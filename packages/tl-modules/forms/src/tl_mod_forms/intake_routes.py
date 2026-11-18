"""The signed-in intake routes under ``/forms/intake/`` (V3-F4; I03r): the queue of a controller.

``GET /forms/intake/codes`` (needs ``forms.intake.issue``), ``GET /forms/intake/items`` and
``GET /forms/intake/items/{item_id}`` (need ``forms.intake.review``), all on the project and read as
the request's viewer. Every route first passes ``guard("forms.read")`` (authentication and the agent
rules: no agent holds it, so an agent is refused before any lookup), then the word, then the read.
A hidden item, an unknown id, an item of another project and a purged one answer the one 404, byte
for byte, and the id is not echoed. No route writes, and none is public: the public ``/i/<code>``
route is S6's and is not here. Nothing returned holds a code, a code hash, a salt or a body; only
the detail of a Pending item holds the sender's answers.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query
from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError

from tl_mod_forms import MODULE, intake_read, intake_views
from tl_mod_forms.names import INTAKE_ISSUE, INTAKE_REVIEW

router = APIRouter(tags=["forms"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
READ_ACTION: Final = "forms.read"
MSG_ITEM: Final = intake_read.MSG_ITEM
ItemState = Literal["Pending", "Accepted", "Rejected"]
CodeState = Literal["Active", "Revoked"]
Project = Annotated[str, Query(max_length=120, description="The project.")]


def _word_reader(word: str):  # noqa: ANN202 - a dependency factory
    def reader(
        ctx: Ctx,
        actor: Annotated[str, Depends(guard(READ_ACTION))],
        principal: Annotated[Principal, Depends(current_principal)],
        project: Project,
    ) -> str:
        with ctx.backend(True) as uow:
            require_word(
                uow.conn(),
                holder_for_principal(principal),
                scope=f"project:{project}",
                module=MODULE,
                word=normalise_word(word),
                what=word,
            )
        return actor

    return reader


_issuer = _word_reader(INTAKE_ISSUE)
_reviewer = _word_reader(INTAKE_REVIEW)
Issuer = Annotated[str, Depends(_issuer)]
Reviewer = Annotated[str, Depends(_reviewer)]


@router.get("/forms/intake/codes", operation_id="list_intake_codes")
def list_intake_codes(
    ctx: Ctx,
    _actor: Issuer,
    project: Project,
    state: Annotated[CodeState | None, Query(description="The code state.")] = None,
    limit: Annotated[int, Query(ge=1, le=intake_views.MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> intake_views.Page[intake_read.IntakeCodeRow]:
    """The intake codes of a project, oldest issue first, each with its Pending count."""
    with ctx.backend(True) as uow:
        return intake_read.code_page(
            uow.conn(),
            f"project:{project}",
            state=state,
            limit=limit,
            offset=offset,
            viewer=current_viewer(),
        )


@router.get("/forms/intake/items", operation_id="list_intake_items")
def list_intake_items(
    ctx: Ctx,
    _actor: Reviewer,
    project: Project,
    state: Annotated[ItemState | None, Query(description="The item state.")] = None,
    code: Annotated[str | None, Query(max_length=60, description="A code id.")] = None,
    limit: Annotated[int, Query(ge=1, le=intake_views.MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> intake_views.Page[intake_views.ItemRow]:
    """The intake items of a project, oldest first. A hidden item is left out of rows and total."""
    with ctx.backend(True) as uow:
        return intake_views.item_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            code_id=code,
            limit=limit,
            offset=offset,
            viewer=current_viewer(),
        )


@router.get("/forms/intake/items/{item_id}", operation_id="get_intake_item")
def get_intake_item(
    item_id: str,
    ctx: Ctx,
    _actor: Reviewer,
    project: Project,
) -> intake_read.ItemDetail:
    """One intake item and, while it is Pending, the sender's answers."""
    with ctx.backend(True) as uow:
        found = intake_read.item_detail(uow.conn(), f"project:{project}", item_id, current_viewer())
    if found is None:
        raise RecordNotFoundError(MSG_ITEM)
    return found
