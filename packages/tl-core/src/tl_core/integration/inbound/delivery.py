"""The error queue and the dry run of a mapping (FANOUT D4; admin only, D12).

``RetryInboundDelivery`` re-runs a delivery that failed (or was stopped by the kill switch) through
the same worker path **with the endpoint's current version**, optionally with a corrected payload
that is stored as a new object beside the received one (which is never changed). The event
``Inbound.Retried`` names the admin and both hashes. A delivery that is queued, applied or a dry
run is not retried: it has not failed.

``dry_run_mapping`` evaluates the endpoint's *current* mapping over a sample or a stored delivery
and reports every command as a ``PlannedCommand``; nothing is written, no command runs, and the
kill switch and the endpoint's switches are ignored (a dry run asks what would happen).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from tl_core.integration.contract import (
    INBOUND_HARD_MAX_BODY_BYTES,
    CommandRunner,
    MappingRuntime,
    PlannedCommand,
    Problem,
)
from tl_core.integration.errors import (
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.inbound import store as body_store
from tl_core.integration.inbound.gate import (
    JOB_KIND,
    MAX_ATTEMPTS,
    InvalidPayload,
    endpoint_view,
    parse_payload,
)
from tl_core.integration.inbound.mapping import JsonataRestricted
from tl_core.integration.inbound.service import endpoint_of_row
from tl_core.integration.inbound.worker import plan_mapped
from tl_core.integration.streams import DELIVERY_STREAM_TYPE, INBOUND_RETRIED
from tl_core.jobs.queue import JobQueue
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

RETRYABLE_STATES = ("failed", "killed")


class RetryInboundDelivery(Command):
    """Queue a failed delivery again. ``corrected_payload`` replaces the body for the run."""

    delivery_id: str
    corrected_payload: Any | None = None


class MappingDryRun(BaseModel):
    """What the current mapping of an endpoint would do with one payload."""

    endpoint: str
    endpoint_version: int
    status: str
    problems: list[Problem] = Field(default_factory=list[Problem])
    commands: list[PlannedCommand] = Field(default_factory=list[PlannedCommand])
    payload_sha256: str | None = None


def _delivery(uow: UnitOfWork, delivery_id: str, scope: str) -> Any:
    row = (
        uow.conn()
        .execute(text("SELECT * FROM int_delivery WHERE delivery_id = :i"), {"i": delivery_id})
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise IntegrationNotFoundError(f"no delivery {delivery_id} in {scope}")
    return row


def handle_retry_delivery(uow: UnitOfWork, cmd: RetryInboundDelivery) -> CommandResult:
    delivery = _delivery(uow, cmd.delivery_id, cmd.scope)
    if delivery["state"] not in RETRYABLE_STATES:
        raise IntegrationStateError(
            f"the delivery is {delivery['state']}; only a failed one retries"
        )
    view = endpoint_view(uow.conn(), delivery["endpoint_id"])
    if view is None:
        raise IntegrationNotFoundError("the endpoint of the delivery is gone")
    corrected_sha: str | None = None
    corrected_key: str | None = None
    if cmd.corrected_payload is not None:
        body = json.dumps(cmd.corrected_payload, ensure_ascii=False, allow_nan=False).encode()
        if len(body) > min(view.max_body_bytes, INBOUND_HARD_MAX_BODY_BYTES):
            raise InvalidIntegrationError("the corrected payload is over the endpoint's body cap")
        try:
            parse_payload(body)
        except InvalidPayload:
            raise InvalidIntegrationError("the corrected payload is not acceptable JSON") from None
        store = body_store.configured()
        corrected_sha = hashlib.sha256(body).hexdigest()
        corrected_key = body_store.body_key(
            view.endpoint_id, cmd.delivery_id, correction=corrected_sha[:8]
        )
        body_store.put_body(store, corrected_key, body)
    conn = uow.conn()
    conn.execute(
        text(
            "UPDATE int_delivery SET state = 'queued', finished_at = NULL, error_code = NULL, "
            "error_message = NULL, command_count = NULL, endpoint_version = :v, "
            "corrected_object_key = COALESCE(:key, corrected_object_key) WHERE delivery_id = :i"
        ),
        {"v": view.version, "key": corrected_key, "i": cmd.delivery_id},
    )
    version = int(
        conn.execute(
            text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s"),
            {"s": cmd.delivery_id},
        ).scalar_one()
    )
    result = uow.append(
        stream_id=cmd.delivery_id,
        stream_type=DELIVERY_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=version,
        events=[
            NewEvent(
                event_type=INBOUND_RETRIED,
                payload={
                    "delivery_id": cmd.delivery_id,
                    "by": cmd.actor,
                    "original_sha256": delivery["payload_sha256"],
                    "corrected_sha256": corrected_sha,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    JobQueue().enqueue(
        conn,
        job_id=f"{cmd.delivery_id}:{new_ulid()}",
        kind=JOB_KIND,
        scope=cmd.scope,
        now=utcnow(),
        max_attempts=MAX_ATTEMPTS,
    )
    return CommandResult(
        stream_id=cmd.delivery_id, key=None, version=result.new_version, events=result.events
    )


def dry_run_mapping(
    uow: UnitOfWork,
    runner: CommandRunner,
    *,
    endpoint_id: str,
    scope: str,
    sample: Any | None = None,
    delivery_id: str | None = None,
    runtime: MappingRuntime | None = None,
) -> MappingDryRun:
    """Plan the endpoint's current mapping over ``sample`` or the body of a stored delivery."""
    if (sample is None) == (delivery_id is None):
        raise InvalidIntegrationError("give a sample payload or a delivery id, not both")
    row = (
        uow.conn()
        .execute(
            text("SELECT * FROM cur_inbound_endpoint WHERE endpoint_id = :i"), {"i": endpoint_id}
        )
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise IntegrationNotFoundError(f"no inbound endpoint {endpoint_id} in {scope}")
    endpoint = endpoint_of_row(row)
    payload_sha: str | None = None
    if delivery_id is not None:
        delivery = _delivery(uow, delivery_id, scope)
        if delivery["endpoint_id"] != endpoint_id:
            raise IntegrationNotFoundError("that delivery belongs to another endpoint")
        try:
            body = body_store.read_body(
                body_store.configured(),
                delivery["corrected_object_key"] or delivery["object_key"],
                INBOUND_HARD_MAX_BODY_BYTES,
            )
            payload = parse_payload(body)
        except (InvalidPayload, ValueError, KeyError, OSError):
            unreadable = Problem(code="invalid_payload", message="The payload is unreadable.")
            return MappingDryRun(
                endpoint=endpoint.name,
                endpoint_version=endpoint.version,
                status="invalid_payload",
                problems=[unreadable],
            )
        payload_sha = delivery["payload_sha256"]
    else:
        payload = sample
    runtime = runtime or JsonataRestricted()
    outcome = runtime.evaluate(endpoint.mapping, payload)
    report = MappingDryRun(
        endpoint=endpoint.name,
        endpoint_version=endpoint.version,
        status=outcome.status,
        problems=list(outcome.problems),
        payload_sha256=payload_sha,
    )
    if outcome.status == "ok":
        definition = {
            "access": endpoint.access,
            "service_actor": endpoint.service_actor,
            "app": endpoint.app,
            "name": endpoint.name,
            "allowed_commands": endpoint.allowed_commands,
        }
        planned = plan_mapped(
            uow.conn(), runner, outcome, definition=definition, scope=scope, delivery_id="dry-run"
        )
        report.commands = [item.planned for item in planned]
    return report


__all__ = [
    "RETRYABLE_STATES",
    "MappingDryRun",
    "RetryInboundDelivery",
    "dry_run_mapping",
    "handle_retry_delivery",
]
