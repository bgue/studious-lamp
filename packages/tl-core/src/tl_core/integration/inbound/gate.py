"""The steps of the inbound route that touch the ledger's state (FANOUT D4; ADR-0017).

The route (``tl_api.inbound``) owns the HTTP: the order of its answers, the body cap and the
status codes. This module owns what each step *decides*, so it is tested without a server:

1. :func:`find_open_endpoint`: the endpoint exists, is switched on, its app is on and the kill
   switch is off. Anything else is ``None``, and the route answers one fixed 404 for every reason.
2. :func:`verify_request`: HMAC or JWT against the endpoint's live secrets, constant time, a fixed
   code on failure (:class:`VerifyError`).
3. :func:`parse_payload`: UTF-8 JSON, nesting at most ``INBOUND_MAX_JSON_DEPTH``, no NaN or
   Infinity, no oversized number; every failure is :class:`InvalidPayload`.
4. :func:`accept_delivery`: in one write transaction the replay row, the operational delivery row,
   the job ``inbound.map`` and the event ``Inbound.Received`` (delivery id, endpoint, SHA-256 and
   size; never the payload or the headers). A message id seen within ``INBOUND_REPLAY_RETENTION_S``
   is :class:`ReplayError`. The body is stored before this call (``store.put_body``).

A failure is counted per endpoint and fixed code in ``int_counter`` (:func:`count_failure`); the
reason never leaves the server except as that code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import Connection, text

from tl_core.integration.contract import (
    INBOUND_MAX_JSON_DEPTH,
    INBOUND_MAX_PENDING_PER_ENDPOINT,
    INBOUND_REPLAY_RETENTION_S,
    AutomationAccess,
)
from tl_core.integration.errors import IntegrationStateError
from tl_core.integration.inbound.verify import VerifyError, verify_hmac, verify_jwt
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.secrets import live_secrets
from tl_core.integration.streams import DELIVERY_STREAM_TYPE, INBOUND_RECEIVED
from tl_core.jobs.queue import JobQueue
from tl_core.jobs.types import iso_z
from tl_core.ledger import Event, NewEvent
from tl_core.uow import UnitOfWork

JOB_KIND = "inbound.map"
MAX_ATTEMPTS = 3
#: A JSON number with more digits than this is hostile (Python would parse a huge integer).
MAX_NUMBER_CHARS = 40
#: A message id longer than this is refused by the verifiers already; the cap is repeated here.
MAX_MESSAGE_ID = 128


class InvalidPayload(Exception):
    """The body is not acceptable JSON. The route answers a fixed 422 ``invalid_payload``."""


class ReplayError(Exception):
    """The message id was seen within the retention window. The route answers the fixed 401."""


class PendingFull(Exception):
    """Too many deliveries wait for this endpoint. The route answers 429."""


@dataclass(frozen=True)
class EndpointView:
    """What the route needs to know about an endpoint that is open for business."""

    endpoint_id: str
    app: str
    name: str
    scope: str
    version: int
    auth: str
    max_body_bytes: int
    rate_per_minute: int
    service_actor: str
    access: AutomationAccess
    dry_run: bool

    @property
    def path(self) -> str:
        return f"/in/{self.app}/{self.name}"

    @property
    def source(self) -> str:
        return f"inbound:{self.app}/{self.name}"


_OPEN_SQL = text(
    "SELECT e.endpoint_id, e.app, e.name, e.scope, e.version, e.auth, e.max_body_bytes, "
    "e.rate_per_minute, e.service_actor, e.access, e.dry_run FROM cur_inbound_endpoint e "
    "WHERE e.app = :app AND e.name = :name AND e.enabled = :on "
    "AND EXISTS (SELECT 1 FROM cur_integration_app a WHERE a.name = e.app AND a.enabled = :on)"
)


def find_open_endpoint(conn: Connection, app: str, name: str) -> EndpointView | None:
    """The endpoint at ``/in/{app}/{name}`` when it may take a delivery now, else ``None``."""
    if len(app) > 200 or len(name) > 200:
        return None
    if kill_switch_on(conn):
        return None
    row = conn.execute(_OPEN_SQL, {"app": app, "name": name, "on": True}).mappings().first()
    return None if row is None else _view(row)


def endpoint_view(conn: Connection, endpoint_id: str) -> EndpointView | None:
    """The endpoint with this id whatever its switches say (for admin paths and tests)."""
    row = (
        conn.execute(
            text(
                "SELECT endpoint_id, app, name, scope, version, auth, max_body_bytes, "
                "rate_per_minute, service_actor, access, dry_run FROM cur_inbound_endpoint "
                "WHERE endpoint_id = :i"
            ),
            {"i": endpoint_id},
        )
        .mappings()
        .first()
    )
    return None if row is None else _view(row)


def _view(row: Any) -> EndpointView:
    return EndpointView(
        endpoint_id=row["endpoint_id"],
        app=row["app"],
        name=row["name"],
        scope=row["scope"],
        version=int(row["version"]),
        auth=row["auth"],
        max_body_bytes=int(row["max_body_bytes"]),
        rate_per_minute=int(row["rate_per_minute"]),
        service_actor=row["service_actor"],
        access=row["access"],
        dry_run=bool(row["dry_run"]),
    )


def pending_deliveries(conn: Connection, endpoint_id: str) -> int:
    return int(
        conn.execute(
            text("SELECT COUNT(*) FROM int_delivery WHERE endpoint_id = :e AND state = 'queued'"),
            {"e": endpoint_id},
        ).scalar_one()
    )


def check_pending(conn: Connection, endpoint_id: str) -> None:
    if pending_deliveries(conn, endpoint_id) >= INBOUND_MAX_PENDING_PER_ENDPOINT:
        raise PendingFull(endpoint_id)


def verify_request(
    conn: Connection,
    endpoint: EndpointView,
    headers: Mapping[str, str],
    body: bytes,
    *,
    now: datetime,
) -> str:
    """The message id (``webhook-id`` or ``jti``) of a request signed for ``endpoint``."""
    secrets = live_secrets(conn, "inbound", endpoint.endpoint_id, now=now)
    if endpoint.auth == "jwt_hs256":
        return verify_jwt(headers, body, secrets, audience=endpoint.path, now=now.timestamp())
    if endpoint.auth == "hmac_sha256":
        return verify_hmac(headers, body, secrets, now=now.timestamp())
    raise VerifyError("no_secret")  # an auth kind this code does not know: fail closed


def _refuse_constant(_name: str) -> Any:
    raise InvalidPayload("not a JSON number")  # NaN, Infinity, -Infinity


def _refuse_number(text_: str) -> Any:
    if len(text_) > MAX_NUMBER_CHARS:
        raise InvalidPayload("a number is too long")
    return int(text_)


def _depth_ok(value: Any) -> bool:
    """Whether ``value`` nests at most ``INBOUND_MAX_JSON_DEPTH`` levels (iterative)."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        children: list[Any]
        if isinstance(item, dict):
            children = list(cast("dict[str, Any]", item).values())
        elif isinstance(item, list):
            children = list(cast("list[Any]", item))
        else:
            continue
        if children and depth >= INBOUND_MAX_JSON_DEPTH:
            return False
        stack.extend((child, depth + 1) for child in children)
    return True


def parse_payload(body: bytes) -> Any:
    """The JSON value of ``body``. Raises :class:`InvalidPayload` for anything else."""
    try:
        decoded = body.decode("utf-8")
        value = json.loads(
            decoded,
            parse_constant=_refuse_constant,
            parse_int=_refuse_number,
            parse_float=lambda t: _float(t),
        )
    except InvalidPayload:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError, OverflowError):
        raise InvalidPayload("not JSON") from None
    if not _depth_ok(value):
        raise InvalidPayload("nested too deeply")
    return value


def _float(text_: str) -> float:
    if len(text_) > MAX_NUMBER_CHARS:
        raise InvalidPayload("a number is too long")
    number = float(text_)
    if number in (float("inf"), float("-inf")) or number != number:
        raise InvalidPayload("not a finite number")
    return number


_REPLAY_INSERT = text(
    "INSERT INTO int_replay (replay_id, endpoint_id, seen_at) VALUES (:id, :e, :t) "
    "ON CONFLICT DO NOTHING"
)
_REPLAY_PRUNE = text("DELETE FROM int_replay WHERE endpoint_id = :e AND seen_at < :cutoff")
_DELIVERY_INSERT = text(
    "INSERT INTO int_delivery (delivery_id, endpoint_id, endpoint_version, scope, state, "
    "object_key, payload_sha256, payload_size, received_at, attempts) VALUES (:id, :e, :v, :s, "
    "'queued', :key, :sha, :size, :t, 0)"
)


def accept_delivery(
    uow: UnitOfWork,
    endpoint: EndpointView,
    *,
    message_id: str,
    delivery_id: str,
    object_key: str,
    payload_sha256: str,
    payload_size: int,
    now: datetime,
) -> list[Event]:
    """The replay row, the delivery row, the job and ``Inbound.Received``: one transaction."""
    if not message_id or len(message_id) > MAX_MESSAGE_ID:
        raise ReplayError("bad message id")
    conn = uow.conn()
    stamp = iso_z(now)
    cutoff = iso_z(now - timedelta(seconds=INBOUND_REPLAY_RETENTION_S))
    conn.execute(_REPLAY_PRUNE, {"e": endpoint.endpoint_id, "cutoff": cutoff})
    inserted = conn.execute(
        _REPLAY_INSERT,
        {"id": f"{endpoint.endpoint_id}:{message_id}", "e": endpoint.endpoint_id, "t": stamp},
    )
    if inserted.rowcount == 0:
        raise ReplayError("seen")
    conn.execute(
        _DELIVERY_INSERT,
        {
            "id": delivery_id,
            "e": endpoint.endpoint_id,
            "v": endpoint.version,
            "s": endpoint.scope,
            "key": object_key,
            "sha": payload_sha256,
            "size": payload_size,
            "t": stamp,
        },
    )
    result = uow.append(
        stream_id=delivery_id,
        stream_type=DELIVERY_STREAM_TYPE,
        scope=endpoint.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=INBOUND_RECEIVED,
                payload={
                    "delivery_id": delivery_id,
                    "endpoint_id": endpoint.endpoint_id,
                    "endpoint_version": endpoint.version,
                    "payload_sha256": payload_sha256,
                    "payload_size": payload_size,
                },
            )
        ],
        actor=endpoint.service_actor,
        source=endpoint.source,
        correlation_id=f"inbound:{delivery_id}",
        causation_id=None,
    )
    JobQueue().enqueue(
        conn,
        job_id=delivery_id,
        kind=JOB_KIND,
        scope=endpoint.scope,
        now=now,
        max_attempts=MAX_ATTEMPTS,
    )
    return result.events


_COUNTER_UPSERT = text(
    "INSERT INTO int_counter (counter_id, endpoint_id, code, count, last_at) "
    "VALUES (:id, :e, :c, 1, :t) ON CONFLICT (counter_id) DO UPDATE SET "
    "count = int_counter.count + 1, last_at = :t"
)


def count_failure(conn: Connection, endpoint_id: str, code: str, now: datetime) -> None:
    """Count one refused request under a fixed ``code`` (never a value from the request)."""
    conn.execute(
        _COUNTER_UPSERT,
        {"id": f"{endpoint_id}:{code}", "e": endpoint_id, "c": code, "t": iso_z(now)},
    )


def require_idle(conn: Connection, endpoint_id: str) -> None:
    """For callers that must not run while deliveries are in flight (kept for the retry command)."""
    if pending_deliveries(conn, endpoint_id) >= INBOUND_MAX_PENDING_PER_ENDPOINT:
        raise IntegrationStateError("too many deliveries are waiting for this endpoint")


__all__ = [
    "JOB_KIND",
    "EndpointView",
    "InvalidPayload",
    "PendingFull",
    "ReplayError",
    "VerifyError",
    "accept_delivery",
    "check_pending",
    "endpoint_view",
    "count_failure",
    "find_open_endpoint",
    "parse_payload",
    "pending_deliveries",
    "require_idle",
    "verify_request",
]
