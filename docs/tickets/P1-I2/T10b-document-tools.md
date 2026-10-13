# P1-I2-T10b — MCP read tools for documents

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket (the read models `tl_mod_documents.views` are in the tree)
Branch: `p1/i2-t10b-mcp-document-tools`

## Goal
An agent reads the document register, a document's revisions and links, the diff between two revisions, the stale links, the overdue reviews and the transmittals through seven read-only MCP tools. `packages/tl-mcp/src/tl_mcp/document_tools.py` has the registration function (final, complete) and the seven `*_impl` functions' signatures and docstrings; the seven bodies raise `NotImplementedError`. The tools are already registered in `tl_mcp/server.py` and every one is an explicit entry of `MCP_ACTIONS` in `tl_mcp/identity.py`. You implement the bodies. One provided test file must pass.

## Brief references (pasted)
> **Brief 9 M1, 7.3, 15.** Documents, pinned links that go stale, overdue reviews and the transmittal log are what a document-control agent needs to read. Changing any of it stays a person's work: issuing, superseding and voiding are the admin's acts (ADR-0011) and an agent only proposes. These tools write nothing.
>
> **Existing pattern.** `tl_mcp/engineering_tools.py` (`list_code_values`, `list_tag_classes`, `get_tag`): an `*_impl` function reads through a module call inside `ctx.factory(True)`, the registered tool wraps it in `guarded(...)`, and the response model is the module's, so an agent and the API see the same fields.

### Specification
- Each `*_impl` makes one module call inside a read-only unit of work (`with ctx.factory(True) as uow:`) and returns its result. The rules are in `tl_mod_documents.views`.
- The registered tools (final) check the action `mcp.<tool>` through `guarded` before the body runs; a new tool is closed to agents until it is in `MCP_ACTIONS` (done).
- An unknown document or transmittal raises the module's error, which `guarded` turns into the tool error the test matches.
- A listing is capped at 500 rows.
- Do not change `server.py`, `identity.py` or any other file.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-mcp/src/tl_mcp/document_tools.py` (the stub you complete):
```python
"""Document control read tools: documents, revisions, stale links, reviews, transmittals (P1-I2).

Seven read-only tools. An agent that proposes a link to a document, or reports on what is overdue,
needs to know which revisions exist, what is current, which links went stale and what is waiting
for an answer; these answer from the register. Changing any of it stays a person's work (issuing,
superseding and voiding are an admin's acts, ADR-0011, and an agent only proposes): none of these
tools writes. The response models are the module's (``tl_mod_documents.views`` and ``reports``),
so an agent, the API and a screen see the same fields.

STUB (P1-I2-T10b): the bodies of the seven functions raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_mod_documents import reports, views

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Number = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The document number, `ISO-1234`."),
]


def list_documents_impl(
    ctx: McpContext,
    *,
    project: str,
    state: str | None,
    doc_type: str | None,
    discipline: str | None,
    include_void: bool,
) -> list[views.DocumentView]:
    """The project's documents by number, without revisions or links."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` (a read-only unit of work).
    # 2. Return views.document_views(uow.conn(), f"project:{project}", doc_type=doc_type,
    #    discipline=discipline, state=state, include_void=include_void, limit=500).
    raise NotImplementedError


def get_document_impl(ctx: McpContext, *, project: str, number: str) -> views.DocumentView:
    """One document with its revisions, renditions and the links to it."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` and return views.document_view(uow.conn(),
    #    f"project:{project}", number). An unknown number raises DocumentNotFoundError, which
    #    `guarded` turns into the tool error.
    raise NotImplementedError


def get_document_diff_impl(
    ctx: McpContext, *, project: str, number: str, from_code: str, to_code: str
) -> views.RevisionDiffView:
    """What changed between two issued revisions of a document."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` and return views.revision_diff_view(uow.conn(),
    #    f"project:{project}", number, from_code, to_code).
    raise NotImplementedError


def list_stale_links_impl(ctx: McpContext, *, project: str) -> list[reports.StalePinLine]:
    """Links to documents whose pin is behind or whose document was voided or superseded."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` and return views.stale_links(uow.conn(),
    #    f"project:{project}").
    raise NotImplementedError


def list_overdue_reviews_impl(
    ctx: McpContext, *, project: str, on: str | None
) -> list[reports.OverdueLine]:
    """Open reviews with a reviewer who has not answered by their date."""
    # STEPS
    # 1. day = date.fromisoformat(on) when `on` is given, else None; a bad date raises ValueError,
    #    which `guarded` turns into the tool error.
    # 2. `with ctx.factory(True) as uow:` and return views.overdue_reviews(uow.conn(),
    #    f"project:{project}", on=day).
    raise NotImplementedError


def list_transmittals_impl(
    ctx: McpContext, *, project: str, state: str | None, direction: str | None
) -> list[views.TransmittalView]:
    """The project's transmittals by number, without items."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` and return views.transmittal_views(uow.conn(),
    #    f"project:{project}", state=state, direction=direction, limit=500).
    raise NotImplementedError


def get_transmittal_impl(ctx: McpContext, *, project: str, number: str) -> views.TransmittalView:
    """One transmittal with its items."""
    # STEPS
    # 1. `with ctx.factory(True) as uow:` and return views.transmittal_view(uow.conn(),
    #    f"project:{project}", number).
    raise NotImplementedError


def register_document_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the seven read tools to ``server``."""

    @server.tool(annotations=READ_ONLY)
    def list_documents(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="A document state, e.g. `Issued`.")
        ] = None,
        doc_type: Annotated[
            str | None, Field(max_length=MAX_PART, description="A document type code, e.g. `ISO`.")
        ] = None,
        discipline: Annotated[
            str | None, Field(max_length=MAX_PART, description="A discipline code, e.g. `PIP`.")
        ] = None,
        include_void: Annotated[bool, Field(description="Include void documents.")] = False,
    ) -> list[views.DocumentView]:
        """List a project's controlled documents (brief 9 M1) by number.

        Each row has the document's state and its current revision (code, issue status, class and
        date). A listing has no revisions or links: use `get_document` for those.
        """
        with guarded(ctx, "list_documents", resource_name("documents", project)):
            return list_documents_impl(
                ctx,
                project=project,
                state=state,
                doc_type=doc_type,
                discipline=discipline,
                include_void=include_void,
            )

    @server.tool(annotations=READ_ONLY)
    def get_document(project: Project, number: Number) -> views.DocumentView:
        """Get one document: its revisions with their renditions, and the links to it.

        A link has a `pin` (a revision code, or none when it floats) and a `pin_state`:
        `current`, `stale` (a later revision was issued), `floating`, `no_current` or `unknown`.
        """
        with guarded(ctx, "get_document", resource_name("document", project, number)):
            return get_document_impl(ctx, project=project, number=number)

    @server.tool(annotations=READ_ONLY)
    def get_document_diff(
        project: Project,
        number: Number,
        from_code: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The earlier revision.")
        ],
        to_code: Annotated[
            str, Field(min_length=1, max_length=MAX_PART, description="The later revision.")
        ],
    ) -> views.RevisionDiffView:
        """Say what changed between two issued revisions of a document.

        `summary` is the heading and then the facts: the status change, each revision issued in
        between and each rendition that was added, removed or replaced. Use it before proposing
        that a stale link be re-pinned.
        """
        with guarded(
            ctx, "get_document_diff", resource_name("document", project, number, from_code, to_code)
        ):
            return get_document_diff_impl(
                ctx, project=project, number=number, from_code=from_code, to_code=to_code
            )

    @server.tool(annotations=READ_ONLY)
    def list_stale_links(project: Project) -> list[reports.StalePinLine]:
        """List links to documents that are stale (brief 7.3).

        A link is stale when a revision was issued after the one it is pinned to, or its document
        was voided or superseded. Each row names the document, the pinned revision, the current
        one, the revisions in between and the record that links.
        """
        with guarded(ctx, "list_stale_links", resource_name("stale_links", project)):
            return list_stale_links_impl(ctx, project=project)

    @server.tool(annotations=READ_ONLY)
    def list_overdue_reviews(
        project: Project,
        on: Annotated[
            str | None,
            Field(max_length=10, description="Judge on this day (YYYY-MM-DD). Default today."),
        ] = None,
    ) -> list[reports.OverdueLine]:
        """List overdue review answers: the cycle is open and the reviewer has not replied."""
        with guarded(ctx, "list_overdue_reviews", resource_name("overdue_reviews", project)):
            return list_overdue_reviews_impl(ctx, project=project, on=on)

    @server.tool(annotations=READ_ONLY)
    def list_transmittals(
        project: Project,
        state: Annotated[
            str | None, Field(max_length=MAX_PART, description="A state, e.g. `Issued`.")
        ] = None,
        direction: Annotated[
            str | None, Field(max_length=MAX_PART, description="`outgoing` or `incoming`.")
        ] = None,
    ) -> list[views.TransmittalView]:
        """List a project's transmittals by number (void ones only with `state=Void`).

        A listing has no items: use `get_transmittal` for the revisions a transmittal carries.
        """
        with guarded(ctx, "list_transmittals", resource_name("transmittals", project)):
            return list_transmittals_impl(ctx, project=project, state=state, direction=direction)

    @server.tool(annotations=READ_ONLY)
    def get_transmittal(project: Project, number: Number) -> views.TransmittalView:
        """Get one transmittal by number: recipients, dates, the answer and its revisions."""
        with guarded(ctx, "get_transmittal", resource_name("transmittal", project, number)):
            return get_transmittal_impl(ctx, project=project, number=number)
```

`packages/tl-modules/documents/src/tl_mod_documents/views.py` (excerpts; read-only, do not edit):
```python
class DocumentView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None
    revision_scheme: str
    pattern_code: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None  # the number of the document that replaced it
    conformance: str
    version: int
    revisions: list[RevisionView] = []
    links: list[DocumentLinkView] = []


class TransmittalView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, str | None]]
    version: int
    items: list[TransmittalItemView] = []


class RevisionDiffView(BaseModel):
    document_number: str
    from_code: str
    to_code: str
    from_status: str | None
    to_status: str | None
    summary: list[str]


def document_views(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    include_void: bool = False,
    limit: int = 1000,
) -> list[DocumentView]:
    """The documents of ``scope`` by number, without revisions or links."""
    ...


def document_view(conn: Connection, scope: str, number: str) -> DocumentView:
    """One document with its revisions (renditions included) and the links to it."""
    ...


def stale_links(conn: Connection, scope: str) -> list[reports.StalePinLine]:
    """Links whose pin is behind or whose target was voided or superseded (the report rows)."""
    ...


def overdue_reviews(
    conn: Connection, scope: str, *, on: date | None = None
) -> list[reports.OverdueLine]:
    """Open reviews with a reviewer who has not answered by the date (the report rows)."""
    ...


def revision_diff_view(
    conn: Connection, scope: str, number: str, from_code: str, to_code: str
) -> RevisionDiffView:
    """What changed between two issued revisions. Raises ``DocumentNotFoundError`` and"""
    ...


def transmittal_views(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    limit: int = 500,
) -> list[TransmittalView]:
    """The transmittals of ``scope`` by number, without items."""
    ...


def transmittal_view(conn: Connection, scope: str, number: str) -> TransmittalView:
    """One transmittal with its items. Raises ``TransmittalNotFoundError``."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/reports.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class OverdueLine:
    """A reviewer who should have answered by now."""

    document_number: str
    revision_code: str
    cycle_key: str
    reviewer: str
    due_date: str
    days_overdue: int


@dataclass(frozen=True)
class StalePinLine:
    """A link pinned to a revision that a newer issue has replaced (or flagged stale)."""

    document_number: str
    document_title: str
    pinned_code: str | None
    current_code: str | None
    current_status: str | None
    linked_key: str | None
    linked_type: str
    link_id: str
    link_status: str
    newer_codes: list[str]
```

`tl_mcp.context.McpContext.factory(readonly: bool)` opens a unit of work (`with ctx.factory(True) as uow:`; `uow.conn()` is the SQLAlchemy connection).

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/document_tools.py` (the file you edit)
- `packages/tl-mcp/src/tl_mcp/engineering_tools.py` (a finished module of the same shape; style)
- `packages/tl-modules/documents/src/tl_mod_documents/views.py`
- `packages/tl-mcp/tests/test_mcp_engineering_tools.py` (how the engineering tools are tested; read only)
- `docs/tickets/P1-I2/provided/t10b-test_mcp_document_tools.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-cli`, `packages/tl-mcp` and `packages/tl-api`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/document_tools.py` (edit)
- `packages/tl-mcp/tests/test_mcp_document_tools.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T10b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t10b-test_mcp_document_tools.py.txt` to `packages/tl-mcp/tests/test_mcp_document_tools.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_mcp_document_tools.py -q
(The MCP tests run on SQLite only; there is no Postgres variant to run.)
uv run pytest packages/tl-mcp -q
```
Expected: `just check` clean; 7 test functions pass on SQLite; the whole tl-mcp package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_documents` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
