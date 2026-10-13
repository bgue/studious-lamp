"""Engineering read tools: code-list values, tag classes and tags (brief 9 M2, 6.4; P1-I1-T09f).

Three read-only tools. An agent that proposes a tag, a pset value or a link needs to know which
values a code list allows, what a tag class requires and what a tag still lacks; these answer
from the registry. Changing any of it stays a person's work (the registry commands are admin-only
and a tag change is a proposal): none of these tools writes. The response models are the API's
(``tl_api.routes.engineering``), so an agent and a client see the same fields.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_api.routes.engineering import CodeValueOut, TagClassOut, TagDetail, TagOut
from tl_core.services.psets import conformance
from tl_mod_engineering import codelists, registry
from tl_mod_engineering.errors import TagNotFoundError
from tl_mod_engineering.names import COMPANY

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def list_code_values_impl(
    ctx: McpContext, *, code_list: str, project: str | None, include_all: bool
) -> list[CodeValueOut]:
    """The values of ``code_list`` as a scope sees them: the company's, then the project's own."""
    scope = COMPANY if project is None else f"project:{project}"
    with ctx.factory(True) as uow:
        found = codelists.values(
            uow.conn(), scope, code_list, on=date.today(), usable_only=not include_all
        )
        return [
            CodeValueOut(
                code_list=item.code_list,
                code=item.code,
                label=item.label,
                scope=item.scope,
                origin=item.origin,
                company_code=item.company_code,
                lifecycle=item.lifecycle,
                usable=item.usable,
            )
            for item in found
        ]


def list_tag_classes_impl(ctx: McpContext, *, include_closed: bool) -> list[TagClassOut]:
    """The company's tag classes by code, with the property sets each requires."""
    with ctx.factory(True) as uow:
        rows = registry.find_tag_classes(uow.conn(), COMPANY, active_only=not include_closed)
        return [TagClassOut.of(row) for row in rows]


def get_tag_impl(ctx: McpContext, *, project: str, number: str) -> TagDetail:
    """One tag by number with its segments, class, state and what it still lacks."""
    with ctx.factory(True) as uow:
        row = registry.find_tag(uow.conn(), f"project:{project}", number)
        if row is None:
            raise TagNotFoundError(f"no tag {number!r} in project {project!r}")
        report = conformance(uow, row.id)
        return TagDetail(**TagOut.of(row).model_dump(), issues=report.issues)


Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]


def register_engineering_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the three read tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_code_values(
        code_list: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="The code list, e.g. `Area`."),
        ],
        project: Annotated[
            str | None,
            Field(
                max_length=MAX_PART,
                description="A project id: also that project's own values, each mapped to a "
                "company value (`company_code`).",
            ),
        ] = None,
        include_all: Annotated[
            bool, Field(description="Include closed values and values outside their dates.")
        ] = False,
    ) -> list[CodeValueOut]:
        """List the values of a code list (brief 6.4): the codes a pset or a tag may use.

        Company values come first, in list order, then the project's own. A project value of an
        extensible list names the company value it stands for in `company_code`.
        """
        with guarded(ctx, "list_code_values", resource_name("code_list", code_list)):
            return list_code_values_impl(
                ctx, code_list=code_list, project=project, include_all=include_all
            )

    @server.tool(annotations=READ_ONLY)
    def list_tag_classes(
        include_closed: Annotated[
            bool, Field(description="Include superseded and retired classes.")
        ] = False,
    ) -> list[TagClassOut]:
        """List the tag classes (brief 9 M2) with the property sets each one requires.

        A tag of a class must carry its `required_psets`; one that lacks them is non-conformant.
        `mnemonics` are the tag-number prefixes the class normally uses.
        """
        with guarded(ctx, "list_tag_classes", resource_name("tag_classes", "all")):
            return list_tag_classes_impl(ctx, include_closed=include_closed)

    @server.tool(annotations=READ_ONLY)
    def get_tag(
        project: Project,
        number: Annotated[
            str,
            Field(min_length=1, max_length=MAX_PART, description="The tag number, `47-FV-1001`."),
        ],
    ) -> TagDetail:
        """Get one tag by number: its parsed segments, class, state and conformance.

        `issues` lists what the tag still lacks (a property set its class requires, a value a
        state needs). `number_status` is `violation` when the number breaks the pattern.
        """
        with guarded(ctx, "get_tag", resource_name("tag", f"{project}/{number}")):
            return get_tag_impl(ctx, project=project, number=number)
