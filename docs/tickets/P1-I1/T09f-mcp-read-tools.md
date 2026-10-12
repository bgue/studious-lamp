# P1-I1-T09f — MCP read tools: list_code_values, list_tag_classes, get_tag

Status: ready
Tier: haiku
Labels: mcp
Depends on: P1-I1-T03, T06, T07 (merged) and the API response models (`tl_api.routes.engineering`, on `p1/i1`); no other ticket
Branch: `p1/i1-t09f-mcp-read-tools`

## Goal
An agent can read the engineering standards and a tag's conformance. `packages/tl-mcp/src/tl_mcp/engineering_tools.py` has the three tools' registration (names, parameter schemas, descriptions, read-only annotations) final and the three `*_impl` bodies raising `NotImplementedError`. The tools are already wired into `build_server`, the instructions and the agent action list (`MCP_ACTIONS`). You implement the bodies. One provided test file (`6` test functions) must pass.

## Brief references (pasted)
> **Brief 11.3 MCP.** An agent reads through tools that wrap one query each; it changes nothing directly (record changes are proposals a person accepts).
>
> **Brief 6.4 / 9 M2.** Code lists and tag classes are company standards; a tag class says which property sets a tag must carry; a tag that lacks them is non-conformant.

### Specification
- Each `*_impl` opens one read-only unit of work with `ctx.factory(True)` and makes registry calls; no rule lives here. `guarded(...)` (in the registered tool) authorises and turns the module's errors into tool errors; do not catch them.
- The response models are the API's: `CodeValueOut`, `TagClassOut` and `TagDetail` from `tl_api.routes.engineering` (already imported).
- An agent token may read these tools: the actions `mcp.list_code_values`, `mcp.list_tag_classes` and `mcp.get_tag` are in `MCP_ACTIONS`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-mcp/src/tl_mcp/engineering_tools.py` (the stub you complete):
```python
"""Engineering read tools: code-list values, tag classes and tags (brief 9 M2, 6.4; P1-I1-T09f).

Three read-only tools. An agent that proposes a tag, a pset value or a link needs to know which
values a code list allows, what a tag class requires and what a tag still lacks; these answer
from the registry. Changing any of it stays a person's work (the registry commands are admin-only
and a tag change is a proposal): none of these tools writes. The response models are the API's
(``tl_api.routes.engineering``), so an agent and a client see the same fields.

STUB (P1-I1-T09f): the bodies of the three `*_impl` functions raise NotImplementedError; their
signatures, docstrings and `register_engineering_tools` are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from tl_api.routes.engineering import CodeValueOut, TagClassOut, TagDetail
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
    # STEPS
    # 1. scope = COMPANY, or f"project:{project}" when ``project`` is given.
    # 2. In `with ctx.factory(True) as uow:` found = codelists.values(uow.conn(), scope, code_list,
    #    on=date.today(), usable_only=not include_all). It raises UnknownCodeListError (``guarded``
    #    turns it into a tool error the agent can read).
    # 3. One CodeValueOut per item: code_list, code, label, scope, origin, company_code, lifecycle
    #    and usable, from the item's attributes of the same names.
    raise NotImplementedError


def list_tag_classes_impl(ctx: McpContext, *, include_closed: bool) -> list[TagClassOut]:
    """The company's tag classes by code, with the property sets each requires."""
    # STEPS
    # 1. In `with ctx.factory(True) as uow:` rows = registry.find_tag_classes(uow.conn(), COMPANY,
    #    active_only=not include_closed).
    # 2. Return [TagClassOut.of(row) for row in rows].
    raise NotImplementedError


def get_tag_impl(ctx: McpContext, *, project: str, number: str) -> TagDetail:
    """One tag by number with its segments, class, state and what it still lacks."""
    # STEPS
    # 1. In `with ctx.factory(True) as uow:` row = registry.find_tag(uow.conn(),
    #    f"project:{project}", number). None: raise TagNotFoundError(f"no tag {number!r} in
    #    project {project!r}").
    # 2. Still inside the block: report = conformance(uow, row.id).
    # 3. Return TagDetail(**TagOut-fields of row, issues=report.issues): build it with
    #    TagDetail(**TagOut.of(row).model_dump(), issues=report.issues) (import TagOut from
    #    tl_api.routes.engineering).
    raise NotImplementedError


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
```

`packages/tl-api/src/tl_api/routes/engineering.py` (the response models; `of` builds one from a registry row):
```python
class CodeValueOut(BaseModel):  code_list: str; code: str; label: str; scope: str; origin: str; company_code: str | None; lifecycle: str; usable: bool
class TagClassOut(BaseModel):   id; code; label; description; family; required_psets: list[str]; itr_templates; mnemonics; lifecycle; superseded_by; edition; key; version
                                @classmethod def of(cls, row: registry.TagClassRow) -> TagClassOut
class TagOut(BaseModel):        id; number; title; class_code; status; area; mnemonic; sequence; segments; pattern_code; number_status; violations; origin; conformance; version; psets
                                @classmethod def of(cls, row: registry.TagRow) -> TagOut
class TagDetail(TagOut):        issues: list[ConformanceIssue]
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py` and `codelists.py`:
```python
def find_tag_classes(conn, scope: str, *, code: str | None = None, active_only: bool = False) -> list[TagClassRow]: ...
def find_tag(conn, scope: str, number: str) -> TagRow | None: ...
def values(conn, scope: str, name: str, *, on: date | None = None, usable_only: bool = True) -> list[Resolution]: ...
    # Resolution: code_list, scope, code, label, company_code, origin, lifecycle, usable; raises UnknownCodeListError
```
`tl_core.services.psets.conformance(uow, record_id) -> ConformanceReport` (`.issues`).

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/engineering_tools.py` (the file you edit)
- `packages/tl-mcp/src/tl_mcp/type_tools.py` (a finished set of read tools of the same shape; read it for style)
- `docs/tickets/P1-I1/provided/t09f-test_mcp_engineering_tools.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-mcp`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- The MCP tests use `McpHarness` (`tests/mcp_harness.py`): a real ledger and the server in process; `structured(tool, **args)` returns the tool's structured content (a list result is under `result`).
- Do not edit `server.py`, `identity.py` or `test_mcp_server.py`: the wiring and the action list are decided and already updated.


## Allowed paths
- `packages/tl-mcp/src/tl_mcp/engineering_tools.py` (edit)
- `packages/tl-mcp/tests/test_mcp_engineering_tools.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09f.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t09f-test_mcp_engineering_tools.py.txt` to `packages/tl-mcp/tests/test_mcp_engineering_tools.py`.
3. Implement the three `*_impl` functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_mcp_engineering_tools.py -q
uv run pytest packages/tl-mcp -q
```
Expected: `just check` clean; `6` passed; the whole tl-mcp package passes.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
