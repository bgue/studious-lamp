# P1-I1-T09c — API reads: standards, code lists, tag classes, tags

Status: ready
Tier: haiku
Labels: api
Depends on: P1-I1-T06, T07 and T03 (merged), the loader and the API commands (on `p1/i1`); no other ticket
Branch: `p1/i1-t09c-api-reads`

## Goal
A client reads the standards registry, the tag classes and a project's tags over HTTP. `packages/tl-api/src/tl_api/routes/engineering.py` has the response models and the seven routes' signatures, queries and docstrings final; the bodies raise `NotImplementedError`. The router is already included in `tl_api/app.py`, the actions `standards.read` and `tag.read` are decided (open to agents) and `docs/reference/openapi.json` is regenerated. You implement the bodies. One provided test file (`8` test functions) must pass.

## Brief references (pasted)
> **Brief 11.1 API.** Reads and commands are the same services the TUI and the CLI use; an agent may read what a person reads.
>
> **Brief 9 M2.** A tag has a number parsed into segments, a class, a workflow status and a conformance level; its class says which property sets it must carry.

### Specification
- Each route makes one registry call inside `ctx.backend(True)` (a read-only unit of work) and returns a model built with the model's own `of(...)`. No rule lives here.
- Missing things are answered by raising the module's error, never `HTTPException`: `StandardNotFoundError` (404 `standard_not_found`), `TagClassNotFoundError` (404 `tag_class_not_found`), `TagNotFoundError` (404 `tag_not_found`); `UnknownCodeListError` comes from `codelists.values` (404 `unknown_code_list`). The error table already maps them.
- The routes need no authorisation code: `guard(...)` is in the signature.
- `GET /projects/{project}/tags` has the query `class` (the Python name is `class_code`; do not rename the alias).

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-api/src/tl_api/routes/engineering.py` (the stub you complete):
```python
"""Reads of the engineering module: the standards registry, tag classes and tags (P1-I1-T09c).

Thin, like the other read routes: one registry call per route. Writes are the module's commands
(``POST /commands/RegisterCodeList``, ``CreateTag`` and the rest; ``tl_mod_engineering.commands``).
A standards or tag-class read needs the action ``standards.read``, a tag read ``tag.read``; both
are open to agents (they only read).

STUB (P1-I1-T09c): the bodies of the route functions raise NotImplementedError; their signatures,
docstrings and the response models (`StandardOut`, `CodeValueOut`, `TagClassOut`, `TagOut`,
`TagDetail`) are final. Each body has a STEPS comment. Implement them, then delete this paragraph,
the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tl_core.services.psets import conformance
from tl_mod_engineering import codelists, registry
from tl_mod_engineering.errors import (
    StandardNotFoundError,
    TagClassNotFoundError,
    TagNotFoundError,
)
from tl_mod_engineering.names import COMPANY
from tl_schema.forms import ConformanceIssue

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["engineering"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
StandardsReader = Annotated[str, Depends(guard("standards.read"))]
TagReader = Annotated[str, Depends(guard("tag.read"))]
StandardKind = Literal["code_list", "mnemonic", "numbering_pattern"]


class StandardOut(BaseModel):
    """A code list, mnemonic or numbering pattern (``data`` holds the kind's own fields)."""

    id: str
    kind: StandardKind
    code: str
    label: str
    definition: str | None
    edition: str
    owner: str | None
    adoption: str
    value_list_policy: str | None
    effective_from: str | None
    effective_to: str | None
    lifecycle: str
    superseded_by: str | None
    key: str | None
    version: int
    data: dict[str, Any]

    @classmethod
    def of(cls, row: registry.StandardRow) -> StandardOut:
        return cls(
            id=row.id,
            kind=row.kind,  # type: ignore[arg-type]
            code=row.code,
            label=row.label,
            definition=row.definition,
            edition=row.edition,
            owner=row.owner,
            adoption=row.adoption,
            value_list_policy=row.value_list_policy,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            lifecycle=row.lifecycle,
            superseded_by=row.superseded_by,
            key=row.key,
            version=row.version,
            data=row.data,
        )


class CodeValueOut(BaseModel):
    """A value of a code list as a scope sees it."""

    code_list: str
    code: str
    label: str
    scope: str
    origin: str  # company | project
    company_code: str | None  # the company value it stands for (itself, for a company value)
    lifecycle: str
    usable: bool  # active and inside its effective dates today


class TagClassOut(BaseModel):
    id: str
    code: str
    label: str
    description: str | None
    family: str
    required_psets: list[str]
    itr_templates: list[str]
    mnemonics: list[str]
    lifecycle: str
    superseded_by: str | None
    edition: str
    key: str | None
    version: int

    @classmethod
    def of(cls, row: registry.TagClassRow) -> TagClassOut:
        return cls(**{name: getattr(row, name) for name in cls.model_fields})


class TagOut(BaseModel):
    id: str
    number: str
    title: str
    class_code: str | None
    status: str | None
    area: str | None
    mnemonic: str | None
    sequence: int | None
    segments: dict[str, str]
    pattern_code: str | None
    number_status: str  # ok | violation
    violations: list[dict[str, Any]]
    origin: str
    conformance: str
    version: int
    psets: dict[str, Any]

    @classmethod
    def of(cls, row: registry.TagRow) -> TagOut:
        return cls(**{name: getattr(row, name) for name in cls.model_fields})


class TagDetail(TagOut):
    """A tag with what it still lacks: the conformance issues now."""

    issues: list[ConformanceIssue]


@router.get("/standards", operation_id="list_standards")
def list_standards(
    ctx: Ctx,
    actor: StandardsReader,
    kind: Annotated[StandardKind | None, Query(description="Only this kind.")] = None,
    include_closed: Annotated[bool, Query(description="Include superseded and retired.")] = False,
) -> list[StandardOut]:
    """Registry entries of the company, by kind then code."""
    # STEPS
    # 1. kinds = [kind] when given, else ["code_list", "mnemonic", "numbering_pattern"].
    # 2. With `ctx.backend(True) as uow:` for each kind collect
    #    registry.find_standards(uow.conn(), scope=COMPANY, kind=k, active_only=not
    #    include_closed); return [StandardOut.of(row) for row in the collected rows].
    raise NotImplementedError


@router.get("/standards/{kind}/{code}", operation_id="get_standard")
def get_standard(ctx: Ctx, actor: StandardsReader, kind: StandardKind, code: str) -> StandardOut:
    """One registry entry (the newest edition). 404 `standard_not_found` when there is none."""
    # STEPS
    # 1. With `ctx.backend(True) as uow:` rows = registry.find_standards(uow.conn(),
    #    scope=COMPANY, kind=kind, code=code).
    # 2. No rows: raise StandardNotFoundError(f"no {kind} {code!r} in the registry"). Otherwise
    #    return StandardOut.of(rows[-1]).
    raise NotImplementedError


@router.get("/code-lists/{name}/values", operation_id="list_code_values")
def list_code_values(
    ctx: Ctx,
    actor: StandardsReader,
    name: str,
    project: Annotated[str | None, Query(description="Also this project's own values.")] = None,
    include_all: Annotated[bool, Query(description="Include closed and expired values.")] = False,
) -> list[CodeValueOut]:
    """The values of a code list as a scope sees them: the company's, then the project's own."""
    # STEPS
    # 1. scope = COMPANY, or f"project:{project}" when project is given.
    # 2. With `ctx.backend(True) as uow:` found = codelists.values(uow.conn(), scope, name,
    #    on=date.today(), usable_only=not include_all). It raises UnknownCodeListError (a 404).
    # 3. Return one CodeValueOut per item: code_list, code, label, scope, origin, company_code,
    #    lifecycle and usable, from the item's attributes of the same names.
    raise NotImplementedError


@router.get("/tag-classes", operation_id="list_tag_classes")
def list_tag_classes(
    ctx: Ctx,
    actor: StandardsReader,
    include_closed: Annotated[bool, Query(description="Include superseded and retired.")] = False,
) -> list[TagClassOut]:
    """The company's tag classes by code."""
    # STEPS
    # 1. With `ctx.backend(True) as uow:` rows = registry.find_tag_classes(uow.conn(), COMPANY,
    #    active_only=not include_closed).
    # 2. Return [TagClassOut.of(row) for row in rows].
    raise NotImplementedError


@router.get("/tag-classes/{code}", operation_id="get_tag_class")
def get_tag_class(ctx: Ctx, actor: StandardsReader, code: str) -> TagClassOut:
    """One tag class: the active one if there is one, else the newest. 404 when unknown."""
    # STEPS
    # 1. With `ctx.backend(True) as uow:` rows = registry.find_tag_classes(uow.conn(), COMPANY,
    #    code=code).
    # 2. No rows: raise TagClassNotFoundError(f"no tag class {code!r}"). Otherwise the active
    #    rows (row.active) if any, else all rows; return TagClassOut.of(the last of them).
    raise NotImplementedError


@router.get("/projects/{project}/tags", operation_id="list_tags")
def list_tags(
    ctx: Ctx,
    actor: TagReader,
    project: str,
    class_code: Annotated[str | None, Query(alias="class")] = None,
    status: Annotated[str | None, Query()] = None,
    mnemonic: Annotated[str | None, Query()] = None,
    area: Annotated[str | None, Query()] = None,
    number_status: Annotated[Literal["ok", "violation"] | None, Query()] = None,
    include_ended: Annotated[bool, Query(description="Include superseded and deleted.")] = False,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TagOut]:
    """A project's tags by number, with the filters given."""
    # STEPS
    # 1. With `ctx.backend(True) as uow:` rows = registry.list_tags(uow.conn(),
    #    f"project:{project}", class_code=class_code, status=status, mnemonic=mnemonic,
    #    area=area, number_status=number_status, include_ended=include_ended, limit=limit,
    #    offset=offset).
    # 2. Return [TagOut.of(row) for row in rows].
    raise NotImplementedError


@router.get("/projects/{project}/tags/{number}", operation_id="get_tag")
def get_tag(ctx: Ctx, actor: TagReader, project: str, number: str) -> TagDetail:
    """One tag by number with its conformance issues. 404 `tag_not_found` when there is none."""
    # STEPS
    # 1. With `ctx.backend(True) as uow:` row = registry.find_tag(uow.conn(), f"project:{project}",
    #    number). None: raise TagNotFoundError(f"no tag {number!r} in project {project!r}").
    # 2. Still inside the block: report = conformance(uow, row.id).
    # 3. Return TagDetail(**TagOut.of(row).model_dump(), issues=report.issues).
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py` (reads you use; rows are frozen dataclasses with the fields the response models name):
```python
def find_standards(conn, *, scope: str, kind: str, code: str | None = None, active_only: bool = False) -> list[StandardRow]: ...  # by code then edition (newest last)
def find_tag_classes(conn, scope: str, *, code: str | None = None, active_only: bool = False) -> list[TagClassRow]: ...
def find_tag(conn, scope: str, number: str) -> TagRow | None: ...
def list_tags(conn, scope: str, *, class_code=None, status=None, mnemonic=None, area=None, number_status=None, include_ended: bool = False, limit: int = 1000, offset: int = 0) -> list[TagRow]: ...  # by number
```

`packages/tl-modules/engineering/src/tl_mod_engineering/codelists.py`:
```python
def values(conn, scope: str, name: str, *, on: date | None = None, usable_only: bool = True) -> list[Resolution]: ...
    # Resolution: code_list, scope, code, label, company_code, origin, lifecycle, usable
```

`tl_core.services.psets`:
```python
def conformance(uow: UnitOfWork, record_id: str) -> ConformanceReport: ...   # .status, .issues (list[ConformanceIssue]), .effective_schema_hash
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/engineering.py` (the file you edit)
- `packages/tl-api/src/tl_api/routes/reference.py` (a finished router of the same shape; read it for style)
- `docs/tickets/P1-I1/provided/t09c-test_api_engineering_reads.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-api`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- The API tests use the `harness` fixture of `packages/tl-api/tests/conftest.py` (a real app over a real SQLite file).
- `from __future__ import annotations` is already at the top of the stub; FastAPI reads the annotations of these route functions at run time and they only use module-level names, so keep it.
- Do not regenerate `docs/reference/openapi.json`: the routes' signatures are final and the file is already current. `just check` verifies it.


## Allowed paths
- `packages/tl-api/src/tl_api/routes/engineering.py` (edit)
- `packages/tl-api/tests/test_api_engineering_reads.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t09c-test_api_engineering_reads.py.txt` to `packages/tl-api/tests/test_api_engineering_reads.py`.
3. Implement the seven routes by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-api/tests/test_api_engineering_reads.py -q
uv run pytest packages/tl-api -q
```
Expected: `just check` clean; `8` passed; the whole tl-api package passes.

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
