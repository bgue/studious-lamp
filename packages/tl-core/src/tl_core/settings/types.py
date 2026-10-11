"""Settings (about:config v1) contracts for P0-I8 (brief §30).

Frozen for the increment: change only by orchestrator decision.

Every tunable behaviour is a named, typed, documented setting. Definitions are data: the platform
ships them in ``schema/settings/platform.yaml`` (validated against the LinkML class
``SettingDefinition`` in ``schema/core/settings.yaml``); an extension type package may ship its own
``settings.yaml`` (brief §31.1, P0-I8 WS-B registers them through :func:`register_definitions`).

Layers resolve ``platform default → company → project → user (UI keys only)``. Values are ledger
events on stream type ``core.Setting``:

- stream id ``setting:<layer>:<key>`` where layer is ``company``, ``project:<id>`` or
  ``user:<id>``;
- event scope: ``project:<id>`` for a project layer, else ``company``.

Secret settings (``sensitivity: secret``) are refused in Phase 0: a vault is a human gate (P0-I5
D15, KMS follow-up). No platform definition is secret.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# Setting.Changed: {key, layer, old_value, new_value, reason, applies_at, accept_risk}
#   old_value / new_value are JSON values; new_value null with "reset": true means "inherit".
SETTING_CHANGED = "Setting.Changed"
# Setting.Locked: {key, layer: "company", locked: bool, bounds: dict | None, reason}
#   Only the company layer locks or bounds a key for its projects (brief §30.2).
SETTING_LOCKED = "Setting.Locked"

SettingType = Literal[
    "bool", "int", "decimal", "string", "enum", "list", "duration", "size", "date", "json"
]
SettingScope = Literal["platform", "company", "project", "user"]
SettingEffect = Literal["live", "reindex", "rebuild", "restart"]
SettingSensitivity = Literal["normal", "secret"]
SettingRisk = Literal["normal", "advanced", "dangerous"]


class SettingValidation(BaseModel):
    minimum: float | None = None
    maximum: float | None = None
    choices: list[Any] | None = None  # enum, or allowed list items
    pattern: str | None = None  # regex for string values


class SettingDefinition(BaseModel):
    """Mirrors the LinkML class; the generated model and this one must agree (test)."""

    key: str  # dotted, namespaced: "feed.reactions.enabled"
    type: SettingType
    default: Any
    description: str
    docs: str | None = None
    scopes: list[SettingScope]  # where a value may be set; "platform" = the default only
    lockable: bool = False
    validation: SettingValidation | None = None
    effect: SettingEffect = "live"
    sensitivity: SettingSensitivity = "normal"
    risk: SettingRisk = "normal"
    since: str  # package or platform version
    deprecated: str | None = None
    owner: str = "platform"  # "platform" or "<namespace>.<TypeName>" for extension packages


class ScheduledChange(BaseModel):
    applies_at: str  # ISO 8601 UTC "Z"
    new_value: Any
    seq: int


Origin = Literal["default", "company", "project", "user"]


class EffectiveSetting(BaseModel):
    key: str
    value: Any
    origin: Origin  # the layer the value came from
    modified_here: bool  # set at the layer being viewed (the ● marker)
    locked: bool  # the company locked the key for projects
    bounds: dict[str, Any] | None  # company-set bounds for project values
    scheduled: list[ScheduledChange]  # future changes at the viewed layer, soonest first
    pending_effect: SettingEffect | None  # reindex/rebuild/restart still owed after a change


class SettingChange(BaseModel):
    """One row of a key's history at one layer (brief §30.3 full per-key history)."""

    seq: int
    key: str
    layer: str
    old_value: Any
    new_value: Any
    reset: bool
    actor: str
    reason: str | None
    recorded_at: str
    applies_at: str | None


class SettingDiff(BaseModel):
    key: str
    left: EffectiveSetting
    right: EffectiveSetting


# Service signatures (implemented in tl_core.settings; supervisor-built: resolver and service):
#   definitions() -> dict[str, SettingDefinition]
#   register_definitions(defs: list[SettingDefinition], *, owner: str) -> None
#       Extension-type keys must start with `<namespace>.<snake_case(TypeName)>.` (D15, amending
#       "the package namespace"), the first segment of a type namespace is never a platform one,
#       and a secret definition is refused; a clash raises.
#   resolve(conn, key, *, project: str | None = None, user: str | None = None,
#           at: datetime | None = None) -> EffectiveSetting
#   resolve_all(conn, *, project=None, user=None, prefix: str | None = None)
#       -> list[EffectiveSetting]
#   set_setting(uow, *, key, layer, value, actor, source, reason: str | None = None,
#               accept_risk: bool = False, applies_at: datetime | None = None) -> EffectiveSetting
#       Refuses (ServiceError subclasses, mapped in tl_api.errors):
#         UnknownSettingError (404 unknown_setting), InvalidSettingValueError (422),
#         SettingScopeError (422 setting_scope: layer not in scopes; user layer only for "ui.*"),
#         SettingLockedError (409 setting_locked), SettingOutOfBoundsError (422),
#         ReasonRequiredError (422 reason_required: advanced or dangerous),
#         RiskNotAcceptedError (422 risk_not_accepted: dangerous without accept_risk),
#         SecretSettingUnavailableError (422 secret_setting_unavailable).
#   reset_setting(uow, *, key, layer, actor, source, reason=None, accept_risk=False)
#   lock_setting(uow, *, key, locked: bool, bounds: dict | None, actor, source, reason)
#   history(conn, key, *, layer: str | None = None) -> list[SettingChange]
#   diff(conn, *, left: str, right: str) -> list[SettingDiff]  # layers; differing keys only
#   export_yaml(conn, *, layer: str) -> str ; import_yaml(uow, text, *, layer, actor, source)
#       -> list[EffectiveSetting]   # all-or-nothing in one unit of work
#   reader(conn_factory) -> SettingsReader  # cached get(key, project=...); invalidated by the
#       bus on Setting.* events, so "live" changes apply without a restart (brief §30.3).
