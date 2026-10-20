"""Registering enrichers: register, revise, switch on and off (brief §18.9; FANOUT D6, D12).

All three are admin commands (the API table declares it; the handlers do not check roles). An
enricher is registered *by the name of an installed plugin*: nobody supplies code, and Phase 1
refuses a plugin that names a model. A registration declares which events it follows (``when``), the
properties of its own layer ``enrich.<name>`` it may fill, and per property the acceptance policy:
``auto`` above a threshold, ``propose`` (the default) or ``shadow``. It starts **disabled**. Its
service actor ``svc:enricher-<name>`` is made here, never named by a client, and holds the access
the registration declares (``user`` or ``controller``, never ``admin``).

Every revision is a new ``version`` that carries the whole registration and refreshes
``code_version`` from the installed plugin, so a value's provenance names the code that made it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text

from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    ENRICH_DEFAULT_AUTO_THRESHOLD,
    ENRICHER_NAME_RE,
    SERVICE_ACTOR_RE,
    AcceptancePolicy,
    AutomationAccess,
    Problem,
)
from tl_core.integration.enrichers.registry import load_enricher, why_unusable
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.streams import (
    ENRICHER_DISABLED,
    ENRICHER_ENABLED,
    ENRICHER_REGISTERED,
    ENRICHER_REVISED,
    ENRICHER_STREAM_TYPE,
)
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import as_list, as_object, load_json

#: What a revision may change. The name, scope and service actor are the enricher's identity.
REVISABLE = frozenset({"when", "properties", "access", "owner", "integration_app"})
MAX_PROPERTIES = 50
_MAX_REASON = 1_000


def _check_reason(value: str | None) -> str | None:
    if value is not None and (not value.strip() or len(value) > _MAX_REASON):
        raise ValueError(f"reason must be 1 to {_MAX_REASON} characters")
    return value


class EnricherProperty(BaseModel):
    """One property of the layer ``enrich.<name>`` and what happens to a value proposed for it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    kind: Literal["string", "number", "boolean", "list"]
    policy: AcceptancePolicy = "propose"
    #: Used by ``auto``: a value at or above it is accepted at once. Stored for every policy.
    threshold: float = Field(default=ENRICH_DEFAULT_AUTO_THRESHOLD, ge=0.0, le=1.0)


class RegisterEnricher(Command):
    """A new enricher registration. It starts disabled."""

    name: str
    when: dict[str, Any]
    properties: list[dict[str, Any]]
    access: AutomationAccess = "user"
    owner: str | None = None  # defaults to the actor
    integration_app: str | None = None


class ReviseEnricher(Command):
    """A new version of a registration. ``reason`` says why; ``expected_version`` is the ledger
    stream version the caller read (None: whatever it is now)."""

    enricher_id: str
    changes: dict[str, Any]
    reason: str
    expected_version: int | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _check_reason(value) or ""


class SetEnricherEnabled(Command):
    enricher_id: str
    enabled: bool
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _check_reason(value)


def registration_problems(
    *, name: str, when: dict[str, Any], properties: list[EnricherProperty]
) -> list[Problem]:
    """Why a registration cannot be stored (empty means it can). Looks the plugin up."""
    problems: list[Problem] = []
    if (
        ENRICHER_NAME_RE.fullmatch(name) is None
        or SERVICE_ACTOR_RE.fullmatch(f"svc:enricher-{name}") is None
    ):
        problems.append(
            Problem(code="bad_name", message="A name is a-z, 0-9 and _, starting with a letter.")
        )
    unusable = why_unusable(load_enricher(name), name)
    if unusable is not None:
        problems.append(Problem(code="no_plugin", message=unusable[:200]))
    try:
        parsed = WebhookFilter.from_dict(when)
    except ValueError as exc:
        problems.append(Problem(code="bad_when", message=f"when: {exc}"[:200]))
    else:
        if not parsed.to_dict():
            problems.append(
                Problem(
                    code="when_too_wide",
                    message="when must narrow: an empty filter is every event.",
                )
            )
    if not properties or len(properties) > MAX_PROPERTIES:
        problems.append(
            Problem(code="bad_properties", message=f"Declare 1 to {MAX_PROPERTIES} properties.")
        )
    names = [p.name for p in properties]
    if len(set(names)) != len(names):
        problems.append(Problem(code="bad_properties", message="A property is declared once."))
    return problems


def _parse_properties(raw: list[dict[str, Any]]) -> list[EnricherProperty]:
    try:
        return [EnricherProperty.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise InvalidIntegrationError(f"properties: {first_error(exc)}") from exc


def _require_valid(name: str, when: dict[str, Any], properties: list[EnricherProperty]) -> None:
    problems = registration_problems(name=name, when=when, properties=properties)
    if problems:
        raise InvalidIntegrationError("; ".join(p.message for p in problems)[:500])


def _row(uow: UnitOfWork, enricher_id: str, scope: str) -> Any:
    row = (
        uow.conn()
        .execute(text("SELECT * FROM cur_enricher WHERE enricher_id = :i"), {"i": enricher_id})
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise IntegrationNotFoundError(f"no enricher {enricher_id} in {scope}")
    return row


def _app_must_exist(uow: UnitOfWork, app: str | None) -> None:
    if app is None:
        return
    found = (
        uow.conn()
        .execute(text("SELECT 1 FROM cur_integration_app WHERE name = :n"), {"n": app})
        .first()
    )
    if found is None:
        raise InvalidIntegrationError(f"no integration app named {app}")


def registration_of_row(row: Any) -> dict[str, Any]:
    """The whole registration of a stored row, as the events carry it (no scope, no switch)."""
    return {
        "name": row["name"],
        "version": int(row["version"]),
        "code_version": row["code_version"],
        "model_ref": row["model_ref"],
        "when": as_object(load_json(row["when_json"])),
        "properties": as_list(load_json(row["properties_json"])),
        "service_actor": row["service_actor"],
        "access": row["access"],
        "owner": row["owner"],
        "integration_app": row["integration_app"],
    }


def _append(
    uow: UnitOfWork,
    cmd: Command,
    enricher_id: str,
    expected: int,
    kind: str,
    payload: dict[str, Any],
) -> CommandResult:
    result = uow.append(
        stream_id=enricher_id,
        stream_type=ENRICHER_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[NewEvent(event_type=kind, payload=payload)],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=enricher_id, key=None, version=result.new_version, events=result.events
    )


def handle_register_enricher(uow: UnitOfWork, cmd: RegisterEnricher) -> CommandResult:
    properties = _parse_properties(cmd.properties)
    _require_valid(cmd.name, cmd.when, properties)
    _app_must_exist(uow, cmd.integration_app)
    taken = (
        uow.conn()
        .execute(text("SELECT 1 FROM cur_enricher WHERE name = :n"), {"n": cmd.name})
        .first()
    )
    if taken is not None:
        raise DuplicateIntegrationError(f"an enricher named {cmd.name} is registered")
    plugin = load_enricher(cmd.name)
    assert plugin is not None  # _require_valid found it
    enricher_id = new_ulid()
    return _append(
        uow,
        cmd,
        enricher_id,
        0,
        ENRICHER_REGISTERED,
        {
            "enricher_id": enricher_id,
            "name": cmd.name,
            "version": 1,
            "code_version": plugin.version,
            "model_ref": None,
            "when": WebhookFilter.from_dict(cmd.when).to_dict(),
            "properties": [p.model_dump(mode="json") for p in properties],
            "service_actor": f"svc:enricher-{cmd.name}",
            "access": cmd.access,
            "owner": cmd.owner or cmd.actor,
            "enabled": False,
            "integration_app": cmd.integration_app,
        },
    )


def handle_revise_enricher(uow: UnitOfWork, cmd: ReviseEnricher) -> CommandResult:
    row = _row(uow, cmd.enricher_id, cmd.scope)
    unknown = sorted(set(cmd.changes) - REVISABLE)
    if unknown:
        raise InvalidIntegrationError(f"an enricher's {', '.join(unknown)} cannot be changed")
    if not cmd.changes:
        raise InvalidIntegrationError("nothing to change")
    current = registration_of_row(row)
    merged = {**current, **cmd.changes}
    if merged["access"] not in ("user", "controller"):
        raise InvalidIntegrationError("access is user or controller")
    if not isinstance(merged["owner"], str) or not merged["owner"].strip():
        raise InvalidIntegrationError("owner must be text")
    properties = _parse_properties(list(merged["properties"]))
    when = as_object(merged["when"])
    _require_valid(row["name"], when, properties)
    _app_must_exist(uow, merged["integration_app"])
    plugin = load_enricher(row["name"])
    assert plugin is not None  # _require_valid found it
    revised = {
        **merged,
        "version": int(row["version"]) + 1,
        "code_version": plugin.version,
        "when": WebhookFilter.from_dict(when).to_dict(),
        "properties": [p.model_dump(mode="json") for p in properties],
    }
    if {k: v for k, v in revised.items() if k != "version"} == {
        k: v for k, v in current.items() if k != "version"
    }:
        raise InvalidIntegrationError("nothing changes")
    expected = (
        cmd.expected_version if cmd.expected_version is not None else int(row["stream_version"])
    )
    return _append(
        uow,
        cmd,
        cmd.enricher_id,
        expected,
        ENRICHER_REVISED,
        {
            "enricher_id": cmd.enricher_id,
            "version": revised["version"],
            "enricher": revised,
            "reason": cmd.reason.strip(),
        },
    )


def handle_set_enricher_enabled(uow: UnitOfWork, cmd: SetEnricherEnabled) -> CommandResult:
    row = _row(uow, cmd.enricher_id, cmd.scope)
    if bool(row["enabled"]) is cmd.enabled:
        raise IntegrationStateError(
            f"enricher {row['name']} is already {'on' if cmd.enabled else 'off'}"
        )
    if cmd.enabled:  # a plugin that was removed, or now names a model, does not start
        unusable = why_unusable(load_enricher(row["name"]), row["name"])
        if unusable is not None:
            raise InvalidIntegrationError(unusable)
    return _append(
        uow,
        cmd,
        cmd.enricher_id,
        int(row["stream_version"]),
        ENRICHER_ENABLED if cmd.enabled else ENRICHER_DISABLED,
        {"enricher_id": cmd.enricher_id, "reason": cmd.reason},
    )


__all__ = [
    "REVISABLE",
    "EnricherProperty",
    "RegisterEnricher",
    "ReviseEnricher",
    "SetEnricherEnabled",
    "handle_register_enricher",
    "handle_revise_enricher",
    "handle_set_enricher_enabled",
    "registration_of_row",
    "registration_problems",
]
