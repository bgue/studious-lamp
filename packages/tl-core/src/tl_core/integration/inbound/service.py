"""Authoring inbound endpoints: create, revise, switch, rotate the secret (brief §18.5; FANOUT D4).

All are admin commands (the API table declares it). An endpoint starts **disabled and in dry-run
mode**; going live is a revision (``dry_run`` false) and then ``enabled``. A mapping is stored only
when the restricted runtime's ``check`` returns nothing. The service actor is made here from the
app and endpoint names (``svc:inbound-<app>-<endpoint>``); the declared access is ``user`` or
``controller``, never ``admin``. Every revision is a new version and a snapshot of it is kept
(``cur_inbound_endpoint_version``), because a delivery is mapped by the version it was received
under.

The signing secret is made here, returned once and kept in ``int_secret`` only; the events name
``secret_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import Field, ValidationError
from sqlalchemy import text

from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    INBOUND_MAX_RATE_PER_MINUTE,
    AutomationAccess,
    InboundAuth,
    InboundEndpoint,
    MappingRuntime,
    Problem,
)
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.inbound.mapping import JsonataRestricted
from tl_core.integration.secrets import IssuedSecret, issue_secret, rotate_secret
from tl_core.integration.streams import (
    ENDPOINT_CREATED,
    ENDPOINT_DISABLED,
    ENDPOINT_ENABLED,
    ENDPOINT_REVISED,
    ENDPOINT_SECRET_ROTATED,
    ENDPOINT_STREAM_TYPE,
)
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow
from tl_core.webhooks.rows import as_list, load_json

#: What a revision may change. The app, name, scope and actor are the endpoint's identity.
REVISABLE = frozenset(
    {
        "auth",
        "mapping",
        "external_schema",
        "allowed_commands",
        "access",
        "max_body_bytes",
        "rate_per_minute",
        "dry_run",
        "owner",
    }
)
_MAX_REASON = 1_000
MAX_ACTOR_SLUG = 80


class CreateInboundEndpoint(Command):
    """A new endpoint at ``/in/{app}/{name}``. It starts disabled, in dry-run mode."""

    app: str
    name: str
    mapping: str
    allowed_commands: list[str]
    auth: InboundAuth = "hmac_sha256"
    access: AutomationAccess = "user"
    external_schema: str | None = Field(default=None, max_length=500)
    max_body_bytes: int | None = None
    rate_per_minute: int | None = None
    owner: str | None = None


class ReviseInboundEndpoint(Command):
    endpoint_id: str
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=_MAX_REASON)
    expected_version: int | None = None


class SetInboundEndpointEnabled(Command):
    endpoint_id: str
    enabled: bool
    reason: str | None = Field(default=None, max_length=_MAX_REASON)


class RotateInboundSecret(Command):
    endpoint_id: str
    overlap_hours: float = 24.0


@dataclass
class EndpointIssued:
    """The result of creating an endpoint or rotating its secret. ``secret`` is shown once."""

    endpoint_id: str
    secret_id: str
    version: int
    events: list[Event] = field(default_factory=list[Event])
    secret: IssuedSecret | None = field(default=None, repr=False)


def actor_for(app: str, name: str) -> str:
    return f"svc:inbound-{app}-{name}"


def _row(uow: UnitOfWork, endpoint_id: str, scope: str) -> Any:
    found = (
        uow.conn()
        .execute(
            text("SELECT * FROM cur_inbound_endpoint WHERE endpoint_id = :i"), {"i": endpoint_id}
        )
        .mappings()
        .first()
    )
    if found is None or found["scope"] != scope:
        raise IntegrationNotFoundError(f"no inbound endpoint {endpoint_id} in {scope}")
    return found


def endpoint_of_row(row: Any) -> InboundEndpoint:
    """The contract model of a stored row."""
    return InboundEndpoint.model_validate(
        {
            "app": row["app"],
            "name": row["name"],
            "scope": row["scope"],
            "version": int(row["version"]),
            "auth": row["auth"],
            "mapping": row["mapping"],
            "mapping_language": row["mapping_language"],
            "external_schema": row["external_schema"],
            "allowed_commands": as_list(load_json(row["allowed_commands_json"])),
            "service_actor": row["service_actor"],
            "access": row["access"],
            "max_body_bytes": int(row["max_body_bytes"]),
            "rate_per_minute": int(row["rate_per_minute"]),
            "dry_run": bool(row["dry_run"]),
            "enabled": bool(row["enabled"]),
            "current_secret_id": row["current_secret_id"],
            "owner": row["owner"],
        }
    )


def endpoint_problems(endpoint: InboundEndpoint, runtime: MappingRuntime) -> list[Problem]:
    """Why ``endpoint`` cannot be stored (empty means it can)."""
    problems = runtime.check(endpoint.mapping)
    if len(f"{endpoint.app}-{endpoint.name}") > MAX_ACTOR_SLUG:
        problems.append(
            Problem(
                code="name_too_long",
                message=f"App and endpoint names total at most {MAX_ACTOR_SLUG} characters.",
            )
        )
    return problems


def _require_valid(endpoint: InboundEndpoint, runtime: MappingRuntime) -> None:
    problems = endpoint_problems(endpoint, runtime)
    if problems:
        raise InvalidIntegrationError("; ".join(p.message for p in problems)[:500])


def _app_must_exist(uow: UnitOfWork, app: str) -> None:
    found = (
        uow.conn()
        .execute(text("SELECT 1 FROM cur_integration_app WHERE name = :n"), {"n": app})
        .first()
    )
    if found is None:
        raise InvalidIntegrationError(f"no integration app named {app}")


def _definition(endpoint: InboundEndpoint) -> dict[str, Any]:
    """The event payload of an endpoint: the model without the scope and the secret id."""
    return endpoint.model_dump(mode="json", exclude={"scope", "current_secret_id"})


def _append(
    uow: UnitOfWork,
    cmd: Command,
    endpoint_id: str,
    expected: int,
    kind: str,
    payload: dict[str, Any],
) -> tuple[int, list[Event]]:
    result = uow.append(
        stream_id=endpoint_id,
        stream_type=ENDPOINT_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[NewEvent(event_type=kind, payload=payload)],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return result.new_version, result.events


def create_endpoint(
    uow: UnitOfWork,
    cmd: CreateInboundEndpoint,
    *,
    runtime: MappingRuntime | None = None,
    now: datetime | None = None,
) -> EndpointIssued:
    runtime = runtime or JsonataRestricted()
    values: dict[str, Any] = {
        "app": cmd.app,
        "name": cmd.name,
        "scope": cmd.scope,
        "auth": cmd.auth,
        "mapping": cmd.mapping,
        "external_schema": cmd.external_schema,
        "allowed_commands": cmd.allowed_commands,
        "service_actor": actor_for(cmd.app, cmd.name),
        "access": cmd.access,
        "owner": cmd.owner or cmd.actor,
        "dry_run": True,
        "enabled": False,
    }
    if cmd.max_body_bytes is not None:
        values["max_body_bytes"] = cmd.max_body_bytes
    if cmd.rate_per_minute is not None:
        values["rate_per_minute"] = cmd.rate_per_minute
    try:
        endpoint = InboundEndpoint.model_validate(values)
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _require_valid(endpoint, runtime)
    _app_must_exist(uow, endpoint.app)
    taken = (
        uow.conn()
        .execute(
            text("SELECT 1 FROM cur_inbound_endpoint WHERE app = :a AND name = :n"),
            {"a": endpoint.app, "n": endpoint.name},
        )
        .first()
    )
    if taken is not None:
        raise DuplicateIntegrationError(f"/in/{endpoint.app}/{endpoint.name} exists")
    endpoint_id = new_ulid()
    issued = issue_secret(uow.conn(), "inbound", endpoint_id, now=now or utcnow())
    version, events = _append(
        uow,
        cmd,
        endpoint_id,
        0,
        ENDPOINT_CREATED,
        {"endpoint_id": endpoint_id, **_definition(endpoint), "secret_id": issued.secret_id},
    )
    return EndpointIssued(
        endpoint_id=endpoint_id,
        secret_id=issued.secret_id,
        version=version,
        events=events,
        secret=issued,
    )


def handle_revise_endpoint(
    uow: UnitOfWork, cmd: ReviseInboundEndpoint, *, runtime: MappingRuntime | None = None
) -> CommandResult:
    runtime = runtime or JsonataRestricted()
    row = _row(uow, cmd.endpoint_id, cmd.scope)
    unknown = sorted(set(cmd.changes) - REVISABLE)
    if unknown:
        raise InvalidIntegrationError(f"an endpoint's {', '.join(unknown)} cannot be changed")
    if not cmd.changes:
        raise InvalidIntegrationError("nothing to change")
    current = endpoint_of_row(row).model_dump(mode="json")
    merged = {**current, **cmd.changes, "version": int(row["version"]) + 1}
    try:
        endpoint = InboundEndpoint.model_validate(merged)
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _require_valid(endpoint, runtime)
    if endpoint.model_dump(mode="json") == {**current, "version": endpoint.version}:
        raise InvalidIntegrationError("nothing changes")
    expected = (
        cmd.expected_version if cmd.expected_version is not None else int(row["stream_version"])
    )
    version, events = _append(
        uow,
        cmd,
        cmd.endpoint_id,
        expected,
        ENDPOINT_REVISED,
        {
            "endpoint_id": cmd.endpoint_id,
            "version": endpoint.version,
            "endpoint": _definition(endpoint),
            "reason": cmd.reason.strip(),
        },
    )
    return CommandResult(stream_id=cmd.endpoint_id, key=None, version=version, events=events)


def handle_set_endpoint_enabled(uow: UnitOfWork, cmd: SetInboundEndpointEnabled) -> CommandResult:
    row = _row(uow, cmd.endpoint_id, cmd.scope)
    if bool(row["enabled"]) is cmd.enabled:
        raise IntegrationStateError(
            f"/in/{row['app']}/{row['name']} is already {'on' if cmd.enabled else 'off'}"
        )
    version, events = _append(
        uow,
        cmd,
        cmd.endpoint_id,
        int(row["stream_version"]),
        ENDPOINT_ENABLED if cmd.enabled else ENDPOINT_DISABLED,
        {"endpoint_id": cmd.endpoint_id, "reason": cmd.reason},
    )
    return CommandResult(stream_id=cmd.endpoint_id, key=None, version=version, events=events)


def rotate_endpoint_secret(
    uow: UnitOfWork, cmd: RotateInboundSecret, *, now: datetime | None = None
) -> EndpointIssued:
    row = _row(uow, cmd.endpoint_id, cmd.scope)
    rotation = rotate_secret(
        uow.conn(),
        "inbound",
        cmd.endpoint_id,
        now=now or utcnow(),
        overlap_hours=cmd.overlap_hours,
    )
    version, events = _append(
        uow,
        cmd,
        cmd.endpoint_id,
        int(row["stream_version"]),
        ENDPOINT_SECRET_ROTATED,
        {
            "endpoint_id": cmd.endpoint_id,
            "secret_id": rotation.issued.secret_id,
            "previous_secret_id": rotation.previous_secret_id,
            "previous_expires_at": rotation.previous_expires_at,
        },
    )
    return EndpointIssued(
        endpoint_id=cmd.endpoint_id,
        secret_id=rotation.issued.secret_id,
        version=version,
        events=events,
        secret=rotation.issued,
    )


__all__ = [
    "INBOUND_MAX_RATE_PER_MINUTE",
    "REVISABLE",
    "CreateInboundEndpoint",
    "EndpointIssued",
    "ReviseInboundEndpoint",
    "RotateInboundSecret",
    "SetInboundEndpointEnabled",
    "actor_for",
    "create_endpoint",
    "endpoint_of_row",
    "endpoint_problems",
    "handle_revise_endpoint",
    "handle_set_endpoint_enabled",
    "rotate_endpoint_secret",
]
