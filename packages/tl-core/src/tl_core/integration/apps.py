"""Integration apps: register, revise, switch on and off (brief §19.2; FANOUT D11, D12).

An app is the name of an outside system or an internal integration. Its name is the first segment
of its inbound paths, so it is unique across the ledger. Switching an app off stops its inbound
endpoints (they answer the fixed 404), its rules, its actions and its enrichers together; the
engines read the app's switch with the record's own (L-P1-I0A-22). All three commands are admin
commands (the API table declares it).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from sqlalchemy import text

from tl_core.integration.contract import SLUG_RE
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.streams import (
    APP_DISABLED,
    APP_ENABLED,
    APP_REGISTERED,
    APP_REVISED,
    APP_STREAM_TYPE,
)
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

REVISABLE = frozenset({"label", "description", "owner"})
_MAX_REASON = 1_000


class RegisterIntegrationApp(Command):
    name: str
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    owner: str | None = None  # defaults to the actor


class ReviseIntegrationApp(Command):
    app_id: str
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=_MAX_REASON)


class SetIntegrationAppEnabled(Command):
    app_id: str
    enabled: bool
    reason: str | None = Field(default=None, max_length=_MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("reason must not be blank")
        return value


def _row(uow: UnitOfWork, app_id: str, scope: str) -> Any:
    found = (
        uow.conn()
        .execute(text("SELECT * FROM cur_integration_app WHERE app_id = :i"), {"i": app_id})
        .mappings()
        .first()
    )
    if found is None or found["scope"] != scope:
        raise IntegrationNotFoundError(f"no integration app {app_id} in {scope}")
    return found


def _append(
    uow: UnitOfWork, cmd: Command, app_id: str, expected: int, kind: str, payload: dict[str, Any]
) -> CommandResult:
    result = uow.append(
        stream_id=app_id,
        stream_type=APP_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[NewEvent(event_type=kind, payload=payload)],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=app_id, key=None, version=result.new_version, events=result.events
    )


def handle_register_app(uow: UnitOfWork, cmd: RegisterIntegrationApp) -> CommandResult:
    if SLUG_RE.fullmatch(cmd.name) is None:
        raise InvalidIntegrationError("A name is a slug: a-z, 0-9, - and _.")
    taken = (
        uow.conn()
        .execute(text("SELECT 1 FROM cur_integration_app WHERE name = :n"), {"n": cmd.name})
        .first()
    )
    if taken is not None:
        raise DuplicateIntegrationError(f"an integration app named {cmd.name} exists")
    app_id = new_ulid()
    return _append(
        uow,
        cmd,
        app_id,
        0,
        APP_REGISTERED,
        {
            "app_id": app_id,
            "name": cmd.name,
            "label": cmd.label,
            "description": cmd.description,
            "owner": cmd.owner or cmd.actor,
            "enabled": True,
        },
    )


def handle_revise_app(uow: UnitOfWork, cmd: ReviseIntegrationApp) -> CommandResult:
    row = _row(uow, cmd.app_id, cmd.scope)
    unknown = sorted(set(cmd.changes) - REVISABLE)
    if unknown:
        raise InvalidIntegrationError(f"an app's {', '.join(unknown)} cannot be changed")
    changes: dict[str, list[Any]] = {}
    for name, value in cmd.changes.items():
        if not isinstance(value, str) or (name != "description" and not value.strip()):
            raise InvalidIntegrationError(f"{name} must be text")
        if len(value) > (2_000 if name == "description" else 200):
            raise InvalidIntegrationError(f"{name} is too long")
        if value != row[name]:
            changes[name] = [row[name], value]
    if not changes:
        raise InvalidIntegrationError("nothing changes")
    return _append(
        uow,
        cmd,
        cmd.app_id,
        int(row["version"]),
        APP_REVISED,
        {"changes": changes, "reason": cmd.reason.strip()},
    )


def handle_set_app_enabled(uow: UnitOfWork, cmd: SetIntegrationAppEnabled) -> CommandResult:
    row = _row(uow, cmd.app_id, cmd.scope)
    if bool(row["enabled"]) is cmd.enabled:
        raise IntegrationStateError(
            f"app {row['name']} is already {'on' if cmd.enabled else 'off'}"
        )
    return _append(
        uow,
        cmd,
        cmd.app_id,
        int(row["version"]),
        APP_ENABLED if cmd.enabled else APP_DISABLED,
        {"reason": cmd.reason},
    )
