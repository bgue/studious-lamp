"""Commands on webhook subscriptions (brief 18.4): create, update, enable, disable, rotate a secret.

A subscription is a ledger stream (``core.WebhookSubscription``). Each handler validates, appends
one
event and, where a secret is involved, writes ``wh_secret`` in the same transaction. **Secrets never
enter the ledger, the logs or an error message**: events carry ``secret_id`` only, and the secret
text is returned once (``SecretIssued.secret``) to the caller that created or rotated it.

Rotation overlap: ``rotate_secret`` issues a new secret and lets the previous one keep signing for
``overlap_hours`` (default 24), so a receiver can switch without dropping deliveries. While both are
active every delivery carries two ``v1`` signatures. A secret that already had an expiry (rotated
out
earlier) is retired at once, so at most two secrets sign.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command
from tl_core.services.errors import NoChangesError, ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_core.webhooks.base import Clock, iso_z, utc_now
from tl_core.webhooks.envelope import PAYLOAD_MODES
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import load_json
from tl_core.webhooks.signing import generate_secret
from tl_core.webhooks.subscription_projector import (
    CREATED,
    DISABLED,
    ENABLED,
    SECRET_ROTATED,
    SUBSCRIPTION_STREAM_TYPE,
    UPDATABLE_FIELDS,
    UPDATED,
)

SUPPORTED_SCHEMA_VERSIONS = ("v1",)
DEFAULT_OVERLAP_HOURS = 24.0


class SubscriptionNotFoundError(ServiceError): ...


class InvalidSubscriptionError(ServiceError): ...


class AlreadyInStateError(ServiceError): ...


class CreateWebhookSubscription(Command):
    name: str = Field(min_length=1)
    target_url: str
    filter: dict[str, Any] = {}
    payload_mode: str = "thin"
    owner: str | None = None  # defaults to the actor
    integration_app: str | None = None
    event_schema_version: str = "v1"
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class UpdateWebhookSubscription(Command):
    subscription_id: str
    changes: dict[str, Any]  # new values by field name: name, target_url, filter, payload_mode, ...


class SubscriptionCommand(Command):
    subscription_id: str


class DisableWebhookSubscription(SubscriptionCommand):
    reason: str = "owner"
    detail: str | None = None


class EnableWebhookSubscription(SubscriptionCommand): ...


class RotateWebhookSecret(SubscriptionCommand):
    overlap_hours: float = Field(default=DEFAULT_OVERLAP_HOURS, ge=0)


class SecretIssued(BaseModel):
    """Result of a create or rotate. ``secret`` is shown here once and cannot be read back."""

    subscription_id: str
    secret_id: str
    secret: str
    version: int
    events: list[Event]

    def __repr__(self) -> str:
        return (
            f"SecretIssued(subscription_id={self.subscription_id!r}, secret_id={self.secret_id!r}, "
            "secret=<hidden>)"
        )

    __str__ = __repr__


class SubscriptionResult(BaseModel):
    subscription_id: str
    version: int
    events: list[Event]


def validate_target_url(url: str) -> str:
    """Syntax only: http(s), a host, no credentials.

    The egress policy judges the address at send time.
    """
    try:
        parts = urlsplit(url)
        _ = parts.port
    except ValueError as exc:
        raise InvalidSubscriptionError("target_url is not a valid URL") from exc
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise InvalidSubscriptionError("target_url must be an http(s) URL with a host")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise InvalidSubscriptionError("target_url must not contain credentials or a fragment")
    return url


def validate_filter(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        return WebhookFilter.from_dict(raw).to_dict()
    except ValueError as exc:
        raise InvalidSubscriptionError(f"invalid filter: {exc}") from exc


def _check_mode(mode: str) -> str:
    if mode not in PAYLOAD_MODES:
        raise InvalidSubscriptionError(f"payload_mode must be one of {', '.join(PAYLOAD_MODES)}")
    return mode


def _check_version(version: str) -> str:
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise InvalidSubscriptionError(
            f"event_schema_version must be one of {', '.join(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    return version


def _load(uow: UnitOfWork, scope: str, subscription_id: str) -> dict[str, Any]:
    row = (
        uow.conn()
        .execute(
            text("SELECT * FROM cur_webhook_subscription WHERE subscription_id = :s"),
            {"s": subscription_id},
        )
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise SubscriptionNotFoundError(f"no webhook subscription {subscription_id} in {scope}")
    return dict(row)


def _insert_secret(uow: UnitOfWork, subscription_id: str, now: datetime) -> tuple[str, str]:
    secret_id, secret = new_ulid(), generate_secret()
    uow.conn().execute(
        text(
            "INSERT INTO wh_secret (secret_id, subscription_id, secret, state, created_at) "
            "VALUES (:id, :s, :secret, 'active', :now)"
        ),
        {"id": secret_id, "s": subscription_id, "secret": secret, "now": iso_z(now)},
    )
    return secret_id, secret


def _append(
    uow: UnitOfWork, cmd: Command, stream_id: str, expected: int, event: NewEvent
) -> tuple[int, list[Event]]:
    result = uow.append(
        stream_id=stream_id,
        stream_type=SUBSCRIPTION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[event],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return result.new_version, result.events


def create_subscription(
    uow: UnitOfWork, cmd: CreateWebhookSubscription, *, clock: Clock = utc_now
) -> SecretIssued:
    """Create a subscription and its first signing secret."""
    target = validate_target_url(cmd.target_url)
    flt = validate_filter(cmd.filter)
    mode = _check_mode(cmd.payload_mode)
    version = _check_version(cmd.event_schema_version)
    now = clock()
    subscription_id = new_ulid()
    secret_id, secret = _insert_secret(uow, subscription_id, now)
    new_version, events = _append(
        uow,
        cmd,
        subscription_id,
        0,
        NewEvent(
            event_type=CREATED,
            payload={
                "subscription_id": subscription_id,
                "name": cmd.name,
                "owner": cmd.owner or cmd.actor,
                "integration_app": cmd.integration_app,
                "target_url": target,
                "filter": flt,
                "payload_mode": mode,
                "event_schema_version": version,
                "expires_at": None if cmd.expires_at is None else iso_z(cmd.expires_at),
                "secret_id": secret_id,
            },
        ),
    )
    return SecretIssued(
        subscription_id=subscription_id,
        secret_id=secret_id,
        secret=secret,
        version=new_version,
        events=events,
    )


def update_subscription(uow: UnitOfWork, cmd: UpdateWebhookSubscription) -> SubscriptionResult:
    """Change name, target, filter, payload mode, integration app, schema pin or expiry."""
    row = _load(uow, cmd.scope, cmd.subscription_id)
    unknown = sorted(set(cmd.changes) - UPDATABLE_FIELDS)
    if unknown:
        allowed = ", ".join(sorted(UPDATABLE_FIELDS))
        raise InvalidSubscriptionError(
            f"cannot update {', '.join(unknown)}; only {allowed} can change"
        )
    current: dict[str, Any] = {
        "name": row["name"],
        "integration_app": row["integration_app"],
        "target_url": row["target_url"],
        "filter": load_json(row["filter_json"]),
        "payload_mode": row["payload_mode"],
        "event_schema_version": row["event_schema_version"],
        "expires_at": row["expires_at"],
    }
    changes: dict[str, list[Any]] = {}
    for name, value in cmd.changes.items():
        if name == "target_url":
            value = validate_target_url(str(value))
        elif name == "filter":
            value = validate_filter(dict(value))
        elif name == "payload_mode":
            value = _check_mode(str(value))
        elif name == "event_schema_version":
            value = _check_version(str(value))
        elif name == "name" and not str(value).strip():
            raise InvalidSubscriptionError("name must not be blank")
        elif name == "expires_at" and isinstance(value, datetime):
            value = iso_z(value)
        if value != current[name]:
            changes[name] = [current[name], value]
    if not changes:
        raise NoChangesError(f"no field of subscription {cmd.subscription_id} differs")
    version, events = _append(
        uow,
        cmd,
        cmd.subscription_id,
        uow.ledger.stream_version(cmd.subscription_id),
        NewEvent(event_type=UPDATED, payload={"changes": changes}),
    )
    return SubscriptionResult(subscription_id=cmd.subscription_id, version=version, events=events)


def disable_subscription(uow: UnitOfWork, cmd: DisableWebhookSubscription) -> SubscriptionResult:
    row = _load(uow, cmd.scope, cmd.subscription_id)
    if row["status"] == "disabled":
        raise AlreadyInStateError(f"subscription {cmd.subscription_id} is already disabled")
    if cmd.reason not in ("owner", "sustained_failure"):
        raise InvalidSubscriptionError("reason must be owner or sustained_failure")
    version, events = _append(
        uow,
        cmd,
        cmd.subscription_id,
        uow.ledger.stream_version(cmd.subscription_id),
        NewEvent(event_type=DISABLED, payload={"reason": cmd.reason, "detail": cmd.detail}),
    )
    return SubscriptionResult(subscription_id=cmd.subscription_id, version=version, events=events)


def enable_subscription(uow: UnitOfWork, cmd: EnableWebhookSubscription) -> SubscriptionResult:
    """Enable again. Events committed while it was disabled are not delivered; replay them."""
    row = _load(uow, cmd.scope, cmd.subscription_id)
    if row["status"] == "active":
        raise AlreadyInStateError(f"subscription {cmd.subscription_id} is already active")
    version, events = _append(
        uow,
        cmd,
        cmd.subscription_id,
        uow.ledger.stream_version(cmd.subscription_id),
        NewEvent(event_type=ENABLED, payload={}),
    )
    return SubscriptionResult(subscription_id=cmd.subscription_id, version=version, events=events)


def rotate_secret(
    uow: UnitOfWork, cmd: RotateWebhookSecret, *, clock: Clock = utc_now
) -> SecretIssued:
    """Issue a new secret; the previous one keeps signing for ``overlap_hours``."""
    row = _load(uow, cmd.scope, cmd.subscription_id)
    now = clock()
    conn = uow.conn()
    expiry = iso_z(now + timedelta(hours=cmd.overlap_hours))
    # A secret that already had an expiry was rotated out before: retire it now (two secrets at
    # most).
    conn.execute(
        text(
            "UPDATE wh_secret SET state = 'retired' WHERE subscription_id = :s "
            "AND state = 'active' AND expires_at IS NOT NULL"
        ),
        {"s": cmd.subscription_id},
    )
    conn.execute(
        text(
            "UPDATE wh_secret SET expires_at = :expiry WHERE subscription_id = :s "
            "AND state = 'active' AND expires_at IS NULL"
        ),
        {"s": cmd.subscription_id, "expiry": expiry},
    )
    secret_id, secret = _insert_secret(uow, cmd.subscription_id, now)
    previous = row["current_secret_id"]
    version, events = _append(
        uow,
        cmd,
        cmd.subscription_id,
        uow.ledger.stream_version(cmd.subscription_id),
        NewEvent(
            event_type=SECRET_ROTATED,
            payload={
                "secret_id": secret_id,
                "previous_secret_id": previous,
                "previous_expires_at": expiry if previous else None,
            },
        ),
    )
    return SecretIssued(
        subscription_id=cmd.subscription_id,
        secret_id=secret_id,
        secret=secret,
        version=version,
        events=events,
    )
