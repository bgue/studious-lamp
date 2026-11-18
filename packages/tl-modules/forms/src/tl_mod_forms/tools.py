"""The agent tools of the forms module (V3-F2): four reads and one proposal.

The reads answer from ``tl_mod_forms.views`` under ``confidentiality.current_viewer()``, the viewer
``guarded`` sets (the lowest clearance for an agent, with no name), so a hidden submission answers
as a missing one: no row, no count, the same fixed text with no key in it. A draft is a person's
own work and an agent is never an author: no tool lists or reads one (the viewer rule leaves it
out, and each tool also drops a ``Draft`` row, so a widened viewer cannot show it).

``propose_form_submission`` files a pending proposal of ``SubmitForm`` (``proposals.submit``);
nothing is submitted until a person who holds ``forms.submit`` accepts it, and that person becomes
the author. A template that is hidden, unpublished or unknown, and a subject record that is hidden
or unknown, are refused with the one text a missing one gets. There is no tool that saves a draft
or reviews, voids, publishes or retires anything. The routes of the module stay closed to agents
(``forms.read``): agents read through these tools only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core import confidentiality
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.intent_param import IntentParam
from tl_mcp.schedule_read_tools import READ_ONLY
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

from tl_mod_forms import read, views
from tl_mod_forms.commands import MAX_ANSWERS, SubmitForm
from tl_mod_forms.names import DRAFT, PROPOSE_SUBMISSION, PUBLISHED

#: The ``mcp.<tool>`` actions this module's tools ask the authorizer about. ``identity.py`` ORs
#: them into ``MCP_ACTIONS``; a tool not listed there is refused.
FORMS_MCP_ACTIONS: frozenset[str] = frozenset(
    {
        "mcp.list_form_templates",
        "mcp.get_form",
        "mcp.list_form_submissions",
        "mcp.get_form_submission",
        f"mcp.{PROPOSE_SUBMISSION}",
    }
)

DEFAULT_LIMIT: Final = 50
#: One text per family, the routes' own: a missing, hidden and unpublished item answer alike.
MSG_TEMPLATE: Final = read.MSG_TEMPLATE
MSG_SUBMISSION: Final = "no such submission"
MSG_SUBJECT: Final = "no record with that key"


@dataclass(frozen=True)
class TemplatePage:
    """One page of published templates; ``total`` counts only those the viewer may read."""

    rows: list[views.TemplateRow]
    total: int


@dataclass(frozen=True)
class SubmissionPage:
    """One page of submissions; ``total`` counts only those the viewer may read."""

    rows: list[views.SubmissionRow]
    total: int


Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Limit = Annotated[int, Field(ge=1, le=views.MAX_LIMIT, description="The most rows to return.")]


def _scope(project: str) -> str:
    return f"project:{project}"


def _published(ctx: McpContext, key: str, version: int | None) -> views.TemplateRow:
    """The published template ``key`` (the latest version, or ``version``) the viewer may read."""
    with ctx.factory(True) as uow:
        page = views.template_list(
            uow.conn(),
            key=key,
            state=PUBLISHED,
            limit=views.MAX_LIMIT,
            viewer=confidentiality.current_viewer(),
        )
    rows = [r for r in page.rows if version is None or r.version == version]
    if not rows:
        raise RecordNotFoundError(MSG_TEMPLATE)
    return max(rows, key=lambda r: r.version or 0)


def list_form_templates_impl(ctx: McpContext, *, limit: int, offset: int) -> TemplatePage:
    """The published templates the viewer may read, by title and version."""
    with ctx.factory(True) as uow:
        page = views.template_list(
            uow.conn(),
            state=PUBLISHED,
            limit=limit,
            offset=offset,
            viewer=confidentiality.current_viewer(),
        )
    return TemplatePage(rows=page.rows, total=page.total)


def get_form_impl(
    ctx: McpContext, *, key: str, version: int | None, projection: read.Projection
) -> Any:
    """One published version as its JSON Schema (or SurveyJS model)."""
    row = _published(ctx, key, version)
    with ctx.factory(True) as uow:
        made = read.version_body(
            uow.conn(), key, row.version or 1, projection, confidentiality.current_viewer()
        )
    if made is None:
        raise RecordNotFoundError(MSG_TEMPLATE)
    return made[1]


def list_form_submissions_impl(
    ctx: McpContext, *, project: str, state: str | None, limit: int, offset: int,
) -> SubmissionPage:  # fmt: skip
    """The project's submissions the viewer may read, the latest first. Never a draft."""
    with ctx.factory(True) as uow:
        page = views.submission_list(
            uow.conn(),
            _scope(project),
            state=state,
            limit=limit,
            offset=offset,
            viewer=confidentiality.current_viewer(),
        )
    rows = [r for r in page.rows if r.state != DRAFT]
    return SubmissionPage(rows=rows, total=page.total - (len(page.rows) - len(rows)))


def get_form_submission_impl(ctx: McpContext, *, project: str, key: str) -> views.SubmissionDetail:
    """One submission by its number. A draft has none, so no draft is read; an id is no key."""
    with ctx.factory(True) as uow:
        found = views.submission_detail(
            uow.conn(), _scope(project), key, viewer=confidentiality.current_viewer()
        )
    if found is None or found.row.state == DRAFT or found.row.key != key:
        raise RecordNotFoundError(MSG_SUBMISSION)
    return found


def propose_form_submission_impl(
    ctx: McpContext,
    *,
    project: str,
    template_key: str,
    answers: list[dict[str, Any]],
    subject_key: str | None,
    summary: str | None,
    intent: Intent | None = None,
) -> ProposalResult:
    scope = _scope(project)
    template = _published(ctx, template_key, None)
    subject_id: str | None = None
    if subject_key is not None:
        with ctx.factory(True) as uow:
            found = get_record(uow, scope, subject_key)
        if found is None:
            raise RecordNotFoundError(MSG_SUBJECT)
        subject_id = str(found["id"])
    command = SubmitForm(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        intent=intent,
        template_id=template.id,
        subject_id=subject_id,
        answers=answers,
    )
    view = proposals.submit(
        ctx.factory,
        tool=PROPOSE_SUBMISSION,
        agent=ctx.actor,
        command=command,
        summary=summary or f"Submit form {template.title or template_key}",
    )
    return _result(view)


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the form reads and the proposing tool."""

    @server.tool(annotations=READ_ONLY)
    def list_form_templates(
        limit: Limit = DEFAULT_LIMIT,
        offset: Annotated[int, Field(ge=0, description="Rows to skip.")] = 0,
    ) -> TemplatePage:
        """List the published form templates by title and version, with the total.

        Use `get_form` for one template's questions as JSON Schema. Templates you may not read
        are left out of the rows and the total.
        """
        with guarded(ctx, "list_form_templates", resource_name("form_template", "company")):
            return list_form_templates_impl(ctx, limit=limit, offset=offset)

    @server.tool(annotations=READ_ONLY)
    def get_form(
        key: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="A template key, `TPL-0001`."),
        ],
        version: Annotated[
            int | None, Field(ge=1, description="A version; the latest published when omitted.")
        ] = None,
        projection: Annotated[
            Literal["jsonschema", "surveyjs"],
            Field(description="The form as `jsonschema` (default) or `surveyjs`."),
        ] = "jsonschema",
    ) -> dict[str, Any]:
        """Get a published form as the JSON Schema of the answers a submission takes.

        A template that does not exist, that you may not read or that is not published gives the
        same error.
        """
        with guarded(ctx, "get_form", resource_name("form_template", key)):
            return get_form_impl(ctx, key=key, version=version, projection=projection)

    @server.tool(annotations=READ_ONLY)
    def list_form_submissions(
        project: Project,
        state: Annotated[
            Literal["Submitted", "Returned", "Accepted", "Voided"] | None,
            Field(description="Only submissions in this state."),
        ] = None,
        limit: Limit = DEFAULT_LIMIT,
        offset: Annotated[int, Field(ge=0, description="Rows to skip.")] = 0,
    ) -> SubmissionPage:
        """List a project's form submissions, the latest first, with the total.

        Submissions you may not read are left out of the rows and the total. Drafts are never
        listed.
        """
        with guarded(ctx, "list_form_submissions", resource_name("form_submission", project)):
            return list_form_submissions_impl(
                ctx, project=project, state=state, limit=limit, offset=offset,
            )  # fmt: skip

    @server.tool(annotations=READ_ONLY)
    def get_form_submission(
        project: Project,
        key: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="A number, `P123-FRM-0001`."),
        ],
    ) -> views.SubmissionDetail:
        """Get one form submission with its answers.

        A submission that does not exist, that you may not read, that is in another project or
        that is a draft gives the same error.
        """
        with guarded(ctx, "get_form_submission", resource_name("form_submission", project, key)):
            return get_form_submission_impl(ctx, project=project, key=key)

    @server.tool(annotations=PROPOSES)
    def propose_form_submission(
        project: Project,
        template_key: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="A published template key."),
        ],
        answers: Annotated[
            list[dict[str, Any]],
            Field(
                max_length=MAX_ANSWERS,
                description="The answers, `{q, value, note}` each, complete for the template.",
            ),
        ],
        subject_key: Annotated[
            str | None,
            Field(min_length=1, max_length=MAX_PART, description="The record the form is about."),
        ] = None,
        summary: Summary = None,
        intent: IntentParam = None,
    ) -> ProposalResult:
        """Propose a filled form.

        Nothing is submitted now. A person who may submit forms accepts it in the review queue,
        and the accepting person becomes the author and takes the number.
        """
        with guarded(ctx, PROPOSE_SUBMISSION, resource_name("form_submission", project)):
            return propose_form_submission_impl(
                ctx, project=project, template_key=template_key, answers=answers,
                subject_key=subject_key, summary=summary, intent=intent,
            )  # fmt: skip
