"""The read routes of the forms module (V3-F1a; ADR-0029, ADR-0031): templates, one template version
as JSON Schema or SurveyJS, the form a record offers, and submissions.

Thin: one call into ``tl_mod_forms.views`` per route, read as the request's viewer (the API
middleware sets it), never the views' LOWEST default. Every route first passes
``guard("forms.read")`` (authentication and the agent rules; no agent holds ``forms.read``), then
the module word ``forms.view`` for the caller (on the company for templates, on the project for
the rest), before any read. A hidden submission, a draft of another author, an unknown key and a
record with no form all answer the one 404 of their route, byte for byte: no key or id is echoed.
Nothing here writes. The writes are the module's commands (``POST /commands/<name>``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_core.auth.module_roles import holder_for_principal, normalise_word, require_word
from tl_core.auth.types import Principal
from tl_core.confidentiality import current_viewer
from tl_core.forms.types import FormBinding
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record

from tl_mod_forms import MODULE, read, views
from tl_mod_forms.names import VIEW

router = APIRouter(tags=["forms"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
READ_ACTION: Final = "forms.read"
COMPANY: Final = "company"
#: One text per route family, so a missing, hidden and other-project record answer alike.
MSG_TEMPLATE: Final = "no such template"
MSG_SUBMISSION: Final = "no such submission"
MSG_FORM: Final = "no such form"
Projection = read.Projection
TemplateState = Literal["Draft", "Published", "Retired"]
SubmissionState = Literal["Draft", "Submitted", "Returned", "Accepted", "Voided", "Discarded"]


def _require_view(ctx: ApiContext, principal: Principal, scope: str) -> None:
    with ctx.backend(True) as uow:
        require_word(
            uow.conn(),
            holder_for_principal(principal),
            scope=scope,
            module=MODULE,
            word=normalise_word(VIEW),
            what=VIEW,
        )


def _template_reader(
    ctx: Ctx,
    actor: Annotated[str, Depends(guard(READ_ACTION))],
    principal: Annotated[Principal, Depends(current_principal)],
) -> str:
    """Authentication and the agent rules, then ``forms.view`` on the company (templates)."""
    _require_view(ctx, principal, COMPANY)
    return actor


def _project_reader(
    ctx: Ctx,
    actor: Annotated[str, Depends(guard(READ_ACTION))],
    principal: Annotated[Principal, Depends(current_principal)],
    project: Annotated[str, Query(max_length=120, description="The project.")],
) -> str:
    """Authentication and the agent rules, then ``forms.view`` on the project."""
    _require_view(ctx, principal, f"project:{project}")
    return actor


TemplateReader = Annotated[str, Depends(_template_reader)]
ProjectReader = Annotated[str, Depends(_project_reader)]


@router.get("/forms/templates", operation_id="list_form_templates")
def list_form_templates(
    ctx: Ctx,
    _actor: TemplateReader,
    state: Annotated[TemplateState | None, Query(description="The template state.")] = None,
    intake: Annotated[Literal["public"] | None, Query(description="public.")] = None,
    limit: Annotated[int, Query(ge=1, le=views.MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> views.Page[views.TemplateRow]:
    """The templates the viewer may read, by title, version and id. ``total`` counts them."""
    with ctx.backend(True) as uow:
        return views.template_list(
            uow.conn(),
            state=state,
            intake=intake,
            limit=limit,
            offset=offset,
            viewer=current_viewer(),
        )


@router.get("/forms/templates/{key}/versions/{version}", operation_id="get_form_template_version")
def get_form_template_version(
    key: str,
    version: int,
    request: Request,
    ctx: Ctx,
    _actor: TemplateReader,
    projection: Annotated[
        Projection | None,
        Query(alias="as", description="jsonschema or surveyjs: the form as that projection."),
    ] = None,
) -> Response:
    """One version of a template with its fields; with ``as`` the JSON Schema of its answers or
    the SurveyJS model. The ETag is the content hash of the fields (and the projection); a request
    that names it in ``If-None-Match`` gets 304 with no body."""
    with ctx.backend(True) as uow:
        made = read.version_body(uow.conn(), key, version, projection, current_viewer())
    if made is None:
        raise RecordNotFoundError(MSG_TEMPLATE)
    tag, body = made
    headers = {"ETag": tag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(body, headers=headers)


@router.get("/forms/for/{key}", operation_id="get_form_for_record")
def get_form_for_record(
    key: str,
    ctx: Ctx,
    _actor: ProjectReader,
    project: Annotated[str, Query(max_length=120, description="The project.")],
) -> FormBinding:
    """The form a record offers (its binding). A record that is absent, hidden from the viewer or
    of a type with no form source answers the same 404."""
    now = datetime.now(UTC)
    with ctx.backend(True) as uow:
        found = get_record(uow, f"project:{project}", key)
        binding = (
            None
            if found is None
            else views.form_for(uow.conn(), str(found["id"]), now=now, viewer=current_viewer())
        )
    if binding is None:
        raise RecordNotFoundError(MSG_FORM)
    return binding


@router.get("/forms/submissions", operation_id="list_form_submissions")
def list_form_submissions(
    ctx: Ctx,
    _actor: ProjectReader,
    project: Annotated[str, Query(max_length=120, description="The project.")],
    state: Annotated[SubmissionState | None, Query(description="The submission state.")] = None,
    template: Annotated[str | None, Query(max_length=60, description="A template id.")] = None,
    subject: Annotated[str | None, Query(max_length=60, description="A record id.")] = None,
    author: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=views.MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> views.Page[views.SubmissionRow]:
    """The submissions of a project, the latest first. A draft is listed for its author alone and
    a hidden submission is left out of the rows and of ``total``."""
    with ctx.backend(True) as uow:
        return views.submission_list(
            uow.conn(),
            f"project:{project}",
            state=state,
            template_id=template,
            subject_id=subject,
            author=author,
            limit=limit,
            offset=offset,
            viewer=current_viewer(),
        )


@router.get("/forms/submissions/{key}", operation_id="get_form_submission")
def get_form_submission(
    key: str,
    ctx: Ctx,
    _actor: ProjectReader,
    project: Annotated[str, Query(max_length=120, description="The project.")],
) -> views.SubmissionDetail:
    """One submission (by key, or by id for a draft, which has no key yet) with its answers."""
    with ctx.backend(True) as uow:
        detail = views.submission_detail(
            uow.conn(), f"project:{project}", key, viewer=current_viewer()
        )
    if detail is None:
        raise RecordNotFoundError(MSG_SUBMISSION)
    return detail
