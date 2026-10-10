"""about:config over HTTP: read, set, reset, lock, revert, history, diff, export and import.

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
from tl_core import settings
from tl_core.settings.layers import parse_layer
from tl_core.settings.types import SettingChange, SettingDiff
from tl_core.settings.views import SettingView, get_view, list_views, view_at

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
    with ctx.backend(True) as uow:
        return list_views(
            uow.conn(), project=project, user=user, prefix=prefix, modified_only=modified
        )


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
    with ctx.backend(True) as uow:
        return settings.diff(uow.conn(), left=left, right=right)


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
    with ctx.backend(True) as uow:
        text = settings.export_yaml(uow.conn(), layer=layer)
    return PlainTextResponse(text, media_type="text/yaml")


@router.post("/settings/import", operation_id="import_settings")
def import_settings(ctx: Ctx, actor: Writer, body: ImportBody) -> ImportResult:
    """Apply a YAML document to a layer, all or nothing."""
    with ctx.backend(False) as uow:
        done = settings.import_yaml(
            uow,
            body.document,
            layer=body.layer,
            actor=actor,
            source=API_SOURCE,
            reason=body.reason,
            accept_risk=body.accept_risk,
        )
        return ImportResult(layer=parse_layer(body.layer).name, keys=[e.key for e in done])


@router.get("/settings/{key}", operation_id="get_setting")
def get_setting(
    ctx: Ctx,
    actor: Reader,
    key: str,
    project: Annotated[str | None, Query(max_length=MAX_PART)] = None,
    user: Annotated[str | None, Query(max_length=MAX_PART)] = None,
) -> SettingView:
    """One setting with its definition and effective state."""
    with ctx.backend(True) as uow:
        return get_view(uow.conn(), key, project=project, user=user)


@router.get("/settings/{key}/history", operation_id="get_setting_history")
def get_setting_history(
    ctx: Ctx,
    actor: Reader,
    key: str,
    layer: Annotated[str | None, Query(max_length=MAX_PART)] = None,
) -> list[SettingChange]:
    """Every change of the key, oldest first."""
    with ctx.backend(True) as uow:
        return settings.history(uow.conn(), key, layer=layer)


@router.put("/settings/{key}", operation_id="set_setting")
def set_setting(ctx: Ctx, actor: Writer, key: str, body: SetBody) -> SettingView:
    """Set a key at a layer; answers with the key as seen there."""
    with ctx.backend(False) as uow:
        settings.set_setting(
            uow,
            key=key,
            layer=body.layer,
            value=body.value,
            actor=actor,
            source=API_SOURCE,
            reason=body.reason,
            accept_risk=body.accept_risk,
            applies_at=body.applies_at,
        )
        return view_at(uow.conn(), key, body.layer)


@router.post("/settings/{key}/reset", operation_id="reset_setting")
def reset_setting(ctx: Ctx, actor: Writer, key: str, body: ResetBody) -> SettingView:
    """Take the layer's own value away so it inherits again."""
    with ctx.backend(False) as uow:
        settings.reset_setting(
            uow,
            key=key,
            layer=body.layer,
            actor=actor,
            source=API_SOURCE,
            reason=body.reason,
            accept_risk=body.accept_risk,
            applies_at=body.applies_at,
        )
        return view_at(uow.conn(), key, body.layer)


@router.post("/settings/{key}/lock", operation_id="lock_setting")
def lock_setting(ctx: Ctx, actor: Writer, key: str, body: LockBody) -> SettingView:
    """Lock a key for projects (or unlock it) and/or bound their values; company layer only."""
    with ctx.backend(False) as uow:
        settings.lock_setting(
            uow,
            key=key,
            locked=body.locked,
            bounds=body.bounds,
            actor=actor,
            source=API_SOURCE,
            reason=body.reason,
        )
        return view_at(uow.conn(), key, "company")


@router.post("/settings/{key}/revert", operation_id="revert_setting")
def revert_setting(ctx: Ctx, actor: Writer, key: str, body: RevertBody) -> SettingView:
    """Undo the latest change of the key at a layer (409 `setting_revert_not_latest` otherwise)."""
    with ctx.backend(False) as uow:
        settings.revert_setting(
            uow,
            key=key,
            layer=body.layer,
            seq=body.seq,
            actor=actor,
            source=API_SOURCE,
            reason=body.reason,
            accept_risk=body.accept_risk,
        )
        return view_at(uow.conn(), key, body.layer)
