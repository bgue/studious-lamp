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
