# P0-I8-T03 — `/settings` routes

Status: merged
Tier: haiku
Labels: api
Depends on: — (the settings service, the route module, `POST /commands/ChangeSetting` and the accept body are on the base)
Branch: `p0/i8a-t03-api-settings`

## Goal
The REST API serves about:config: `GET /settings` and `GET /settings/{key}` (with the project or user being viewed), `GET /settings/{key}/history`, `PUT /settings/{key}` (set, optionally scheduled), `POST /settings/{key}/reset|lock|revert`, `GET /settings/diff`, `GET /settings/export` (YAML) and `POST /settings/import`. The module `routes/settings.py` has the router, the request bodies, the helper `view_at` and every route's decorator, parameters and docstring (they make the committed OpenAPI document); the ten route functions raise `NotImplementedError`. A provided test file (18 tests) must pass and `docs/reference/openapi.json` must not change.

## Brief references (pasted)
> **30.2 Layers and resolution.** `platform default -> company -> project -> user (UI keys only)`. The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified"). A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
> **30.3 Change control.** Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time. **Scheduled changes** take effect at a future time. **Dangerous keys** need explicit confirmation ("I accept the risk"). Changes apply live. Full per-key history, with revert.
> **30.4 Interfaces.** CLI: `tl config get | set | reset | lock | diff | export | import`. API: `/settings` endpoints. MCP: `get_settings` (read), `propose_setting_change` (draft for human approval). Export/import as YAML for templates and reviews.
> **B15 (orchestrator ruling, P0-I6).** An `agent:` token never changes a record or a setting over REST: it answers 403 `agent_must_propose`; agents propose through MCP and a person accepts. The rule is `guard(..., changes_records=True)`. Reads are open to every authenticated actor.

### Specification
Each route is one call into `tl_core.settings` inside `ctx.backend(readonly)`, as the comment in each stub body says. Writes use `Writer` (the guard that refuses an agent), the token's actor, and source `api`; they answer with the key as seen at the layer they changed (`view_at(uow.conn(), key, layer)`, read inside the same block so it sees the write). The errors are already mapped (`tl_api/errors.py`: 404 `unknown_setting`, 409 `setting_locked`, 422 for the rest); no route catches anything. The route order matters: `/settings/diff`, `/settings/export` and `/settings/import` are declared before `/settings/{key}`; do not reorder. `POST /commands/ChangeSetting` and the proposal accept body's `accept_risk` are already done; the provided test covers them as well.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails on this base (four extension-type event types are not catalogued yet; workstream B owns that). It is the only expected failure of a whole-repo run. Do not touch it.
- A route stub ticket must keep every decorator, parameter, annotation and docstring that reaches the OpenAPI document, because the document is committed and drift-checked: run `uv run python -m tl_api.openapi --check` before committing. You change function bodies only.
- This module does not import `settings` from `tl_api`: the name `settings` here is `tl_core.settings`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-api/src/tl_api/routes/settings.py` (the stub you complete):
```python
"""about:config over HTTP: read, set, reset, lock, revert, history, diff, export and import.

STUB (P0-I8-T03): the ten route functions raise NotImplementedError; their decorators, parameters,
annotations and docstrings are final (they make the committed OpenAPI document). Each body has a
comment with the steps. Implement them, then delete this paragraph and the comments.

Thin: one `tl_core.settings` call per route. Reads are open to every authenticated actor. Every
write is refused for an `agent:` token with 403 `agent_must_propose` (FANOUT decision D3: an agent
proposes through MCP and a person accepts); the person's token is recorded as the actor, the
source is `api`. A write answers with the key as seen at the layer it changed. The errors are the
`SettingError` rows of `tl_api.errors`: 404 `unknown_setting`, 409 `setting_locked`, 422
`invalid_setting_value`, `setting_scope`, `setting_out_of_bounds`, `reason_required`,
`risk_not_accepted`, `secret_setting_unavailable`, `setting_not_lockable`, `settings_document`.
Who may set or lock which key is the permission model, a human gate (ADR-0005).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection
from tl_core.settings.layers import parse_layer
from tl_core.settings.types import SettingChange, SettingDiff
from tl_core.settings.views import SettingView, get_view

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["settings"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("setting.read"))]
Writer = Annotated[str, Depends(guard("setting.write", changes_records=True))]
API_SOURCE = "api"
MAX_PART = 128
MAX_REASON = 1000
MAX_DOCUMENT = 262_144

Key = Annotated[str, Field(min_length=1, max_length=MAX_PART)]
Layer = Annotated[
    str,
    Field(
        min_length=1, max_length=MAX_PART, description="`company`, `project:<id>` or `user:<id>`."
    ),
]
Reason = Annotated[
    str | None,
    Field(max_length=MAX_REASON, description="Required for `advanced` and `dangerous` keys."),
]
AcceptRisk = Annotated[
    bool, Field(description='"I accept the risk": required for `dangerous` keys.')
]


class SetBody(BaseModel):
    """Body of ``PUT /settings/{key}``."""

    model_config = ConfigDict(extra="forbid")

    layer: Layer
    value: Any = Field(description="The new value, as JSON of the setting's type.")
    reason: Reason = None
    accept_risk: AcceptRisk = False
    applies_at: datetime | None = Field(
        default=None, description="A time with a zone, in the future: schedule the change."
    )


class ResetBody(BaseModel):
    """Body of ``POST /settings/{key}/reset``."""

    model_config = ConfigDict(extra="forbid")

    layer: Layer
    reason: Reason = None
    accept_risk: AcceptRisk = False
    applies_at: datetime | None = None


class LockBody(BaseModel):
    """Body of ``POST /settings/{key}/lock``."""

    model_config = ConfigDict(extra="forbid")

    locked: bool = Field(description="True: projects may not override the key.")
    bounds: dict[str, Any] | None = Field(
        default=None, description="`minimum`, `maximum` and/or `choices` for project values."
    )
    reason: Annotated[str, Field(min_length=1, max_length=MAX_REASON)]


class RevertBody(BaseModel):
    """Body of ``POST /settings/{key}/revert``."""

    model_config = ConfigDict(extra="forbid")

    layer: Layer
    seq: Annotated[int, Field(ge=1, description="The change number from the key's history.")]
    reason: Reason = None
    accept_risk: AcceptRisk = False


class ImportBody(BaseModel):
    """Body of ``POST /settings/import``."""

    model_config = ConfigDict(extra="forbid")

    layer: Layer
    document: Annotated[str, Field(max_length=MAX_DOCUMENT, description="The YAML document.")]
    reason: Reason = None
    accept_risk: AcceptRisk = False


class ImportResult(BaseModel):
    layer: str
    keys: list[str]


def view_at(conn: Connection, key: str, layer: str) -> SettingView:
    """``key`` as seen at ``layer`` (the project or user the layer names)."""
    ref = parse_layer(layer)
    return get_view(
        conn,
        key,
        project=ref.ident if ref.kind == "project" else None,
        user=ref.ident if ref.kind == "user" else None,
    )


@router.get("/settings", operation_id="list_settings")
def list_settings(
    ctx: Ctx,
    actor: Reader,
    project: Annotated[
        str | None, Query(max_length=MAX_PART, description="View as this project.")
    ] = None,
    user: Annotated[
        str | None, Query(max_length=MAX_PART, description="View as this user.")
    ] = None,
    prefix: Annotated[
        str | None, Query(max_length=MAX_PART, description="Only keys starting with this.")
    ] = None,
    modified: Annotated[bool, Query(description="Only keys set at the viewed layer (●).")] = False,
) -> list[SettingView]:
    """Every setting with its definition and effective state, sorted by key."""
    # STUB (P0-I8-T03): Open a read-only unit of work (`ctx.backend(True)`), call
    # `list_views(uow.conn(), project=project, user=user, prefix=prefix,
    # modified_only=modified)` and return the list.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.get("/settings/diff", operation_id="diff_settings")
def diff_settings(
    ctx: Ctx,
    actor: Reader,
    left: Annotated[
        str,
        Query(
            min_length=1,
            max_length=MAX_PART,
            description="default, company, project:<id> or user:<id>.",
        ),
    ],
    right: Annotated[
        str,
        Query(
            min_length=1,
            max_length=MAX_PART,
            description="default, company, project:<id> or user:<id>.",
        ),
    ],
) -> list[SettingDiff]:
    """The keys whose effective value differs between two layers."""
    # STUB (P0-I8-T03): Read-only unit of work; return `settings.diff(uow.conn(), left=left,
    # right=right)`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.get(
    "/settings/export",
    operation_id="export_settings",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/yaml": {}}, "description": "A YAML document."}},
)
def export_settings(
    ctx: Ctx, actor: Reader, layer: Annotated[str, Query(min_length=1, max_length=MAX_PART)]
) -> PlainTextResponse:
    """What a layer holds (and, for the company, its locks) as a YAML document."""
    # STUB (P0-I8-T03): Read-only unit of work; `text = settings.export_yaml(uow.conn(),
    # layer=layer)`; return `PlainTextResponse(text, media_type="text/yaml")`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.post("/settings/import", operation_id="import_settings")
def import_settings(ctx: Ctx, actor: Writer, body: ImportBody) -> ImportResult:
    """Apply a YAML document to a layer, all or nothing."""
    # STUB (P0-I8-T03): Write unit of work (`ctx.backend(False)`); `done =
    # settings.import_yaml(uow, body.document, layer=body.layer, actor=actor, source=API_SOURCE,
    # reason=body.reason, accept_risk=body.accept_risk)`. Return
    # `ImportResult(layer=parse_layer(body.layer).name, keys=[e.key for e in done])`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.get("/settings/{key}", operation_id="get_setting")
def get_setting(
    ctx: Ctx,
    actor: Reader,
    key: str,
    project: Annotated[str | None, Query(max_length=MAX_PART)] = None,
    user: Annotated[str | None, Query(max_length=MAX_PART)] = None,
) -> SettingView:
    """One setting with its definition and effective state."""
    # STUB (P0-I8-T03): Read-only unit of work; return `get_view(uow.conn(), key,
    # project=project, user=user)`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.get("/settings/{key}/history", operation_id="get_setting_history")
def get_setting_history(
    ctx: Ctx,
    actor: Reader,
    key: str,
    layer: Annotated[str | None, Query(max_length=MAX_PART)] = None,
) -> list[SettingChange]:
    """Every change of the key, oldest first."""
    # STUB (P0-I8-T03): Read-only unit of work; return `settings.history(uow.conn(), key,
    # layer=layer)`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.put("/settings/{key}", operation_id="set_setting")
def set_setting(ctx: Ctx, actor: Writer, key: str, body: SetBody) -> SettingView:
    """Set a key at a layer; answers with the key as seen there."""
    # STUB (P0-I8-T03): Write unit of work; `settings.set_setting(uow, key=key,
    # layer=body.layer, value=body.value, actor=actor, source=API_SOURCE, reason=body.reason,
    # accept_risk=body.accept_risk, applies_at=body.applies_at)`; then, still inside the block,
    # return `view_at(uow.conn(), key, body.layer)`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.post("/settings/{key}/reset", operation_id="reset_setting")
def reset_setting(ctx: Ctx, actor: Writer, key: str, body: ResetBody) -> SettingView:
    """Take the layer's own value away so it inherits again."""
    # STUB (P0-I8-T03): Write unit of work; `settings.reset_setting(uow, key=key,
    # layer=body.layer, actor=actor, source=API_SOURCE, reason=body.reason,
    # accept_risk=body.accept_risk, applies_at=body.applies_at)`; then, inside the block, return
    # `view_at(uow.conn(), key, body.layer)`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.post("/settings/{key}/lock", operation_id="lock_setting")
def lock_setting(ctx: Ctx, actor: Writer, key: str, body: LockBody) -> SettingView:
    """Lock a key for projects (or unlock it) and/or bound their values; company layer only."""
    # STUB (P0-I8-T03): Write unit of work; `settings.lock_setting(uow, key=key,
    # locked=body.locked, bounds=body.bounds, actor=actor, source=API_SOURCE,
    # reason=body.reason)`; then, inside the block, return `view_at(uow.conn(), key,
    # "company")`.
    raise NotImplementedError("STUB (P0-I8-T03)")


@router.post("/settings/{key}/revert", operation_id="revert_setting")
def revert_setting(ctx: Ctx, actor: Writer, key: str, body: RevertBody) -> SettingView:
    """Undo the latest change of the key at a layer (409 `setting_revert_not_latest` otherwise)."""
    # STUB (P0-I8-T03): Write unit of work; `settings.revert_setting(uow, key=key,
    # layer=body.layer, seq=body.seq, actor=actor, source=API_SOURCE, reason=body.reason,
    # accept_risk=body.accept_risk)`; then, inside the block, return `view_at(uow.conn(), key,
    # body.layer)`.
    raise NotImplementedError("STUB (P0-I8-T03)")
```
```python
# imports to add to routes/settings.py (the stub's autofix removed them):
from tl_core import settings
from tl_core.settings.views import SettingView, get_view, list_views
```
```python
# tl_core.settings (already implemented; read-only for you)
# list_views(conn, *, project=None, user=None, prefix=None, modified_only=False) -> list[SettingView]
# get_view(conn, key, *, project=None, user=None) -> SettingView
# settings.history(conn, key, *, layer=None) -> list[SettingChange];  settings.diff(conn, *, left, right) -> list[SettingDiff]
# settings.export_yaml(conn, *, layer) -> str
# settings.import_yaml(uow, text, *, layer, actor, source, reason=None, accept_risk=False) -> list[EffectiveSetting]
# settings.set_setting(uow, *, key, layer, value, actor, source, reason=None, accept_risk=False, applies_at=None) -> EffectiveSetting
# settings.reset_setting(uow, *, key, layer, actor, source, reason=None, accept_risk=False, applies_at=None) -> EffectiveSetting
# settings.lock_setting(uow, *, key, locked, bounds, actor, source, reason) -> EffectiveSetting
# settings.revert_setting(uow, *, key, layer, seq, actor, source, reason=None, accept_risk=False) -> EffectiveSetting
# ctx.backend(readonly: bool) -> context manager yielding an entered UnitOfWork (uow.conn() is the connection)
# guard(action, *, changes_records=False) -> the FastAPI dependency; `Reader` and `Writer` in the stub are built with it
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/routes/settings.py`
- `packages/tl-api/src/tl_api/routes/proposals.py` (style: `ctx.backend`, `Reader`/`Acceptor`)
- `docs/tickets/P0-I8/provided/t03-test_api_settings.py.txt`
- `packages/tl-api/tests/harness.py` (what the provided test builds on; read only)
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/settings.py` (edit: bodies only)
- `packages/tl-api/tests/test_api_settings.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T03.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t03-test_api_settings.py.txt packages/tl-api/tests/test_api_settings.py`
2. Implement the ten route bodies from the comments; delete the comments and the STUB paragraph; add the imports you use.
3. Run the acceptance commands (the OpenAPI check must say nothing changed), write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_api_settings.py -q
uv run python -m tl_api.openapi --check
just check
uv run pytest packages/tl-api -q
```
Expected: 18 tests pass; the OpenAPI check passes without regenerating; `just check` is clean; the API package is green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste `git diff --stat` (it must show only the three Allowed paths) and the output of the OpenAPI check.

## Escalation triggers
- Stop and report *Blocked* if the OpenAPI check fails after your change (a decorator or signature moved), or a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
Reviewed in a fresh context: pass. Merged into p0/i8a as 18cd9cc.
