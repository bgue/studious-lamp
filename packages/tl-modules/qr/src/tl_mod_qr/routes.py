"""The read routes of the QR module (P2-QR-T06; ADR-0029): the register of one record's codes, its
export, and a JSON resolve of one code.

Thin: one call into ``tl_mod_qr.views`` or ``tl_mod_qr.resolve`` per route, through the viewer's
class filter (the request's viewer, which the API middleware sets, not the views' LOWEST default).
Every route first passes ``guard("qr.read")`` (authentication and the agent rules; no agent holds
``qr.read``). The two register routes then check the module word ``qr.view`` for the caller on the
project, before any read. A hidden, unknown or other-project record answers the same 404 as a key
that does not exist. A resolve miss of any kind answers the one 404 text, with ``Cache-Control:
no-store``. Nothing here writes, and no answer carries a code or its hash.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import body_for
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record

from tl_mod_qr import MODULE
from tl_mod_qr.resolve import resolve
from tl_mod_qr.views import CodeRow, codes_for_record, export_rows

router = APIRouter(tags=["qr"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
VIEW_WORD = "qr.view"
READ_ACTION = "qr.read"
#: One text for a missing, hidden, unknown and other-project record: the key is not echoed.
MSG_RECORD = "no such record"
#: One text for every miss of the resolve route.
MSG_CODE = "no such code"
NO_STORE = {"Cache-Control": "no-store"}


def _view_reader(
    project: str,
    ctx: Ctx,
    actor: Annotated[str, Depends(guard(READ_ACTION))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules (``guard``), then the module word ``qr.view`` the caller
    holds on the project, before any read. A refusal is the API's 403 ``forbidden``."""
    with ctx.backend(True) as uow:
        require_word(
            uow.conn(),
            holder_for_principal(principal),
            scope=f"project:{project}",
            module=MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    return actor


Reader = Annotated[str, Depends(_view_reader)]


def _register(ctx: ApiContext, project: str, record: str) -> list[CodeRow]:
    """The codes of one record, newest first, as the viewer may see them."""
    with ctx.backend(True) as uow:
        found = get_record(uow, f"project:{project}", record)
        if found is None:
            raise RecordNotFoundError(MSG_RECORD)
        return codes_for_record(uow.conn(), str(found["id"]), viewer=current_viewer())


@router.get("/qr/codes", operation_id="list_qr_codes")
def list_qr_codes(
    ctx: Ctx,
    actor: Reader,
    project: Annotated[str, Query(max_length=120, description="The project.")],
    record: Annotated[str, Query(max_length=200, description="The key of the record.")],
) -> list[CodeRow]:
    """The scan codes of one record, newest first, at most 100. The code and its hash are never
    in a row. A record the viewer may not see answers the same 404 as a missing one."""
    return _register(ctx, project, record)


@router.get("/qr/codes/export", operation_id="export_qr_codes")
def export_qr_codes(
    ctx: Ctx,
    actor: Reader,
    project: Annotated[str, Query(max_length=120, description="The project.")],
    record: Annotated[str, Query(max_length=200, description="The key of the record.")],
    fmt: Annotated[Literal["csv", "jsonl"], Query(alias="format", description="csv or jsonl.")],
) -> Response:
    """The rows of the list route as CSV (``text/csv``) or JSON lines (``application/x-ndjson``)."""
    rows = _register(ctx, project, record)
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    return Response(content=export_rows(rows, fmt), media_type=media)


@router.get("/qr/resolve/{code}", operation_id="resolve_qr_code")
def resolve_qr_code(
    code: str,
    ctx: Ctx,
    _actor: Annotated[str, Depends(guard(READ_ACTION))],
) -> Response:
    """The status card of one code as the viewer sees it. Every miss (malformed, unknown, revoked,
    expired, hidden target, no view word, no provider) is the same 404 ``record_not_found``."""
    with ctx.backend(True) as uow:
        card = resolve(uow.conn(), code, current_viewer())
    if card is None:
        mapped = body_for(RecordNotFoundError(MSG_CODE))
        assert mapped is not None  # the error table maps RecordNotFoundError
        status, body = mapped
        return JSONResponse(
            body.model_dump(mode="json", exclude_none=True), status_code=status, headers=NO_STORE
        )
    return JSONResponse(card.model_dump(mode="json"), headers=NO_STORE)
