"""The delivery engine: claim, attempt, settle (brief 18.4). Signing and ordering live here.

Lifecycle of one ``wh_delivery`` row: ``pending`` until it is ``delivered`` (a 2xx answer) or
``dead``
(retries exhausted, ``410 Gone``, or a target the egress policy refuses). A dead delivery is the
dead-letter queue; an operator re-enqueues it with ``Dispatcher.redrive`` (it becomes ``redriven``).

**Ordering.** Events of one subject reach one subscription in ``seq`` order: a delivery is only
claimable while no earlier delivery of the same ``(subscription, subject)`` is still ``pending``
(being retried counts as pending). So event N+1 never goes out before N is delivered or
dead-lettered, while different subjects are claimed together and can be sent in parallel. A replay
or redrive row is ordered by its ``seq`` like any other.

**Claims.** ``claim`` takes a lease with a compare-and-set ``UPDATE`` (works on SQLite and Postgres
without ``SKIP LOCKED``): a row is leased to one worker until ``lease_until``; a crashed worker's
lease expires and the row is taken again. No transaction is open while the network call runs.

**Settling.** ``settle`` records the attempt, then the outcome: delivered, rescheduled with backoff,
or
dead-lettered. After every failure it evaluates the subscription's health and, if the policy says
so,
appends ``WebhookSubscription.Disabled`` (reason ``sustained_failure``) in the same transaction.
Delivery attempts themselves are operational rows (``wh_attempt``), not ledger events: a failing
endpoint would otherwise write events about events (brief section 5 deviation, recorded in the
increment plan).
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, text

from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_core.webhooks.base import Clock, UowFactory, iso_z, parse_iso, utc_now
from tl_core.webhooks.egress import EgressDenied, EgressPolicy, ResolutionFailed
from tl_core.webhooks.retry import DeadReason, HealthPolicy, RetryPolicy
from tl_core.webhooks.signing import SigningSecret, sign_headers
from tl_core.webhooks.subscription_projector import (
    DISABLED,
    SUBSCRIPTION_STREAM_TYPE,
)
from tl_core.webhooks.subscriptions import SubscriptionNotActiveError, current_version
from tl_core.webhooks.transport import Transport, TransportResult

log = logging.getLogger(__name__)

#: Header on test sends (``DeliveryEngine.send_test``); absent from real deliveries.
TEST_HEADER = "webhook-test"
ACTOR = "svc:webhooks"
SOURCE = "svc:webhook-worker"
DEFAULT_LEASE_S = 60.0
DEFAULT_TIMEOUT_S = 10.0

# A subscription can send only while it has a signing secret that has not expired. After a restore
# from the ledger archive it has none (secrets are never in the ledger): its deliveries then stay
# pending, untouched, until `rotate-secret` issues one. Nothing is sent unsigned and nothing is
# dead-lettered for want of a secret.
HAS_SECRET_SQL = (
    "EXISTS (SELECT 1 FROM wh_secret w WHERE w.subscription_id = d.subscription_id "
    "AND w.state = 'active' AND (w.expires_at IS NULL OR w.expires_at > :now))"
)
_CLAIMABLE_SQL = text(
    "SELECT d.delivery_id, d.subscription_id, d.seq, d.event_id, d.subject_id, d.body, "
    "d.attempts, d.created_at, s.target_url, s.scope "
    "FROM wh_delivery d JOIN cur_webhook_subscription s "
    "ON s.subscription_id = d.subscription_id "
    "WHERE d.status = 'pending' AND s.status = 'active' AND d.next_attempt_at <= :now "
    f"AND {HAS_SECRET_SQL} "
    "AND (d.lease_until IS NULL OR d.lease_until <= :now) "
    "AND NOT EXISTS (SELECT 1 FROM wh_delivery e "
    "WHERE e.subscription_id = d.subscription_id AND e.subject_id = d.subject_id "
    "AND e.status = 'pending' AND (e.seq < d.seq "
    "OR (e.seq = d.seq AND e.delivery_id < d.delivery_id))) "
    "ORDER BY d.seq, d.delivery_id LIMIT :limit"
)
_NEEDS_SECRET_SQL = text(
    "SELECT DISTINCT d.subscription_id FROM wh_delivery d JOIN cur_webhook_subscription s "
    "ON s.subscription_id = d.subscription_id "
    f"WHERE d.status = 'pending' AND s.status = 'active' AND NOT {HAS_SECRET_SQL} "
    "ORDER BY d.subscription_id"
)
_LEASE_SQL = text(
    "UPDATE wh_delivery SET lease_until = :until, lease_owner = :owner "
    "WHERE delivery_id = :id AND status = 'pending' "
    "AND (lease_until IS NULL OR lease_until <= :now)"
)
_SECRETS_SQL = text(
    "SELECT secret, expires_at FROM wh_secret WHERE subscription_id = :s AND state = 'active' "
    "ORDER BY created_at, secret_id"
)
_OWNED_SQL = text(
    "SELECT attempts, created_at FROM wh_delivery "
    "WHERE delivery_id = :id AND status = 'pending' AND lease_owner = :owner"
)
_ATTEMPT_SQL = text(
    "INSERT INTO wh_attempt (attempt_id, delivery_id, subscription_id, attempt, started_at, "
    "latency_ms, status, outcome, error, response_excerpt) VALUES (:attempt_id, :delivery_id, "
    ":subscription_id, :attempt, :started_at, :latency_ms, :status, :outcome, :error, :excerpt)"
)
_HEALTH_SQL = text("SELECT * FROM wh_health WHERE subscription_id = :s")


@dataclass(frozen=True)
class Claim:
    """A delivery leased to this worker, with what an attempt needs."""

    delivery_id: str
    subscription_id: str
    scope: str
    seq: int
    event_id: str
    subject_id: str
    body: str
    attempts: int
    created_at: datetime
    target_url: str
    secrets: tuple[SigningSecret, ...]


@dataclass(frozen=True)
class AttemptOutcome:
    """What one attempt did, before it is recorded."""

    started_at: datetime
    result: TransportResult | None
    permanent: DeadReason | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None and self.result.ok


@dataclass(frozen=True)
class Settled:
    """The recorded result of one claim."""

    delivery_id: str
    state: str  # delivered | retry | dead | lost (the lease was taken by someone else)
    attempt: int = 0
    status: int | None = None
    next_attempt_at: datetime | None = None
    dead_reason: str | None = None
    disabled_subscription: bool = False


@dataclass(frozen=True)
class TestResult:
    """Result of :meth:`DeliveryEngine.send_test`."""

    __test__ = False  # not a pytest class

    event_id: str
    status: int | None
    ok: bool
    latency_ms: int
    error: str | None = None
    excerpt: str = ""
    blocked: bool = False


@dataclass
class CycleStats:
    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    dead: int = 0
    disabled: int = 0


class DeliveryEngine:
    def __init__(
        self,
        open_uow: UowFactory,
        transport: Transport,
        *,
        egress: EgressPolicy | None = None,
        retry: RetryPolicy | None = None,
        health: HealthPolicy | None = None,
        clock: Clock = utc_now,
        rng: random.Random | None = None,
        worker_id: str | None = None,
        lease_s: float = DEFAULT_LEASE_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._open = open_uow
        self._transport = transport
        self._egress = egress if egress is not None else EgressPolicy()
        self._retry = retry if retry is not None else RetryPolicy()
        self._health = health if health is not None else HealthPolicy()
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self.worker_id = worker_id or f"worker-{uuid4().hex[:8]}"
        self._lease_s = lease_s
        self._timeout_s = timeout_s
        self.needs_secret: list[str] = []
        """Subscriptions the latest ``claim`` held back for want of a secret."""

    # --- claim -------------------------------------------------------------------------------

    def claim(self, limit: int = 10) -> list[Claim]:
        """Lease up to ``limit`` deliveries that may be sent now: the head of each subject's
        queue."""
        now = self._clock()
        until = iso_z(now + timedelta(seconds=self._lease_s))
        stamp = iso_z(now)
        claimed: list[Claim] = []
        with self._open() as uow:
            conn = uow.conn()
            heads = conn.execute(_CLAIMABLE_SQL, {"now": stamp, "limit": limit}).mappings().all()
            for head in heads:
                taken = conn.execute(
                    _LEASE_SQL,
                    {
                        "until": until,
                        "owner": self.worker_id,
                        "id": head["delivery_id"],
                        "now": stamp,
                    },
                )
                if taken.rowcount != 1:
                    continue
                claimed.append(
                    Claim(
                        delivery_id=head["delivery_id"],
                        subscription_id=head["subscription_id"],
                        scope=head["scope"],
                        seq=int(head["seq"]),
                        event_id=head["event_id"],
                        subject_id=head["subject_id"],
                        body=head["body"],
                        attempts=int(head["attempts"]),
                        created_at=parse_iso(head["created_at"]),
                        target_url=head["target_url"],
                        secrets=self._active_secrets(conn, head["subscription_id"], now),
                    )
                )
            waiting = [str(row[0]) for row in conn.execute(_NEEDS_SECRET_SQL, {"now": stamp}).all()]
        self.needs_secret = waiting
        for subscription_id in waiting:  # once per subscription per cycle; never the secret id
            log.warning(
                "webhook subscription %s has pending deliveries but no usable signing secret; "
                "they stay pending until `tl webhook rotate-secret` issues one",
                subscription_id,
            )
        return claimed

    @staticmethod
    def _active_secrets(
        conn: Connection, subscription_id: str, now: datetime
    ) -> tuple[SigningSecret, ...]:
        secrets: list[SigningSecret] = []
        for row in conn.execute(_SECRETS_SQL, {"s": subscription_id}).mappings():
            expires = row["expires_at"]
            if expires is None or parse_iso(str(expires)) > now:
                secrets.append(SigningSecret(row["secret"]))
        return tuple(secrets)

    # --- attempt (no database) -----------------------------------------------------------------

    def attempt(
        self, claim: Claim, *, extra_headers: Mapping[str, str] | None = None
    ) -> AttemptOutcome:
        """Check the target, sign the body afresh and send it. Opens no transaction.

        ``extra_headers`` are added after signing (they are not part of the signed content).
        """
        started = self._clock()
        try:
            target = self._egress.check(claim.target_url)
        except EgressDenied as exc:
            return AttemptOutcome(started, None, permanent="egress_denied", error=str(exc)[:200])
        except ResolutionFailed as exc:
            return AttemptOutcome(started, None, error=str(exc)[:200])
        if not claim.secrets:
            return AttemptOutcome(
                started, None, error="the subscription has no active signing secret"
            )
        headers = {
            **sign_headers(claim.event_id, int(started.timestamp()), claim.body, claim.secrets),
            "Content-Type": "application/json",
            **(extra_headers or {}),
        }
        result = self._transport.send(
            target, headers, claim.body.encode("utf-8"), timeout_s=self._timeout_s
        )
        return AttemptOutcome(started, result)

    # --- settle ------------------------------------------------------------------------------

    def settle(self, claim: Claim, outcome: AttemptOutcome) -> Settled:
        """Record the attempt and move the delivery to its next state."""
        now = self._clock()
        with self._open() as uow:
            conn = uow.conn()
            owned = conn.execute(
                _OWNED_SQL, {"id": claim.delivery_id, "owner": self.worker_id}
            ).first()
            if owned is None:
                return Settled(claim.delivery_id, "lost")
            attempt = int(owned.attempts) + 1
            created = parse_iso(owned.created_at)
            result = outcome.result
            status = None if result is None else result.status
            error = outcome.error if result is None else result.error
            if outcome.ok:
                state, decision_delay, dead_reason = "delivered", 0.0, None
            else:
                decision = self._retry.decide(
                    attempt=attempt,
                    now=now,
                    created_at=created,
                    rng=self._rng,
                    status=status,
                    permanent=outcome.permanent,
                    retry_after_s=None if result is None else result.retry_after_s,
                )
                state = decision.kind
                decision_delay, dead_reason = decision.delay_s, decision.reason
                if error is None:
                    error = f"HTTP {status}" if status is not None else "no response"
            conn.execute(
                _ATTEMPT_SQL,
                {
                    "attempt_id": new_ulid(),
                    "delivery_id": claim.delivery_id,
                    "subscription_id": claim.subscription_id,
                    "attempt": attempt,
                    "started_at": iso_z(outcome.started_at),
                    "latency_ms": 0 if result is None else result.latency_ms,
                    "status": status,
                    "outcome": {"delivered": "delivered", "retry": "retry", "dead": "dead"}[state],
                    "error": None if state == "delivered" else error,
                    "excerpt": None if result is None else result.excerpt,
                },
            )
            next_at: datetime | None = None
            if state == "delivered":
                self._finish(conn, claim, "delivered", attempt, status, None, None, now)
            elif state == "retry":
                next_at = now + timedelta(seconds=decision_delay)
                conn.execute(
                    text(
                        "UPDATE wh_delivery SET attempts = :a, next_attempt_at = :next, "
                        "lease_until = NULL, lease_owner = NULL, last_status = :st, "
                        "last_error = :err WHERE delivery_id = :id"
                    ),
                    {
                        "a": attempt,
                        "next": iso_z(next_at),
                        "st": status,
                        "err": error,
                        "id": claim.delivery_id,
                    },
                )
            else:
                self._finish(conn, claim, "dead", attempt, status, error, dead_reason, now)
            disabled = self._update_health(uow, claim, state, now)
            return Settled(
                claim.delivery_id,
                state,
                attempt=attempt,
                status=status,
                next_attempt_at=next_at,
                dead_reason=dead_reason,
                disabled_subscription=disabled,
            )

    @staticmethod
    def _finish(
        conn: Connection,
        claim: Claim,
        state: str,
        attempt: int,
        status: int | None,
        error: str | None,
        dead_reason: str | None,
        now: datetime,
    ) -> None:
        stamp = iso_z(now)
        conn.execute(
            text(
                "UPDATE wh_delivery SET status = :state, attempts = :a, lease_until = NULL, "
                "lease_owner = NULL, last_status = :st, last_error = :err, "
                "delivered_at = :delivered, dead_at = :dead, dead_reason = :reason "
                "WHERE delivery_id = :id"
            ),
            {
                "state": state,
                "a": attempt,
                "st": status,
                "err": error,
                "delivered": stamp if state == "delivered" else None,
                "dead": stamp if state == "dead" else None,
                "reason": dead_reason,
                "id": claim.delivery_id,
            },
        )

    def _update_health(self, uow: Any, claim: Claim, state: str, now: datetime) -> bool:
        """Bookkeeping per subscription; returns True when it auto-disabled the subscription."""
        conn: Connection = uow.conn()
        sid = claim.subscription_id
        conn.execute(
            text("INSERT INTO wh_health (subscription_id) VALUES (:s) ON CONFLICT DO NOTHING"),
            {"s": sid},
        )
        stamp = iso_z(now)
        if state == "delivered":
            conn.execute(
                text(
                    "UPDATE wh_health SET consecutive_dead = 0, failing_since = NULL, "
                    "last_success_at = :t, delivered_total = delivered_total + 1 "
                    "WHERE subscription_id = :s"
                ),
                {"t": stamp, "s": sid},
            )
            return False
        conn.execute(
            text(
                "UPDATE wh_health SET failing_since = COALESCE(failing_since, :t), "
                "last_failure_at = :t, failed_total = failed_total + 1, "
                "consecutive_dead = consecutive_dead + :dead WHERE subscription_id = :s"
            ),
            {"t": stamp, "s": sid, "dead": 1 if state == "dead" else 0},
        )
        row = conn.execute(_HEALTH_SQL, {"s": sid}).mappings().one()
        detail = self._health.should_disable(
            consecutive_dead=int(row["consecutive_dead"]),
            failing_since=None if row["failing_since"] is None else parse_iso(row["failing_since"]),
            now=now,
        )
        if detail is None:
            return False
        active = conn.execute(
            text("SELECT status FROM cur_webhook_subscription WHERE subscription_id = :s"),
            {"s": sid},
        ).first()
        if active is None or active.status != "active":
            return False
        uow.append(
            stream_id=sid,
            stream_type=SUBSCRIPTION_STREAM_TYPE,
            scope=claim.scope,
            expected_version=current_version(uow, sid),
            events=[
                NewEvent(
                    event_type=DISABLED,
                    payload={"reason": "sustained_failure", "detail": detail},
                )
            ],
            actor=ACTOR,
            source=SOURCE,
            correlation_id=new_ulid(),
        )
        log.warning("webhook subscription %s auto-disabled: %s", sid, detail)
        return True

    # --- test event ---------------------------------------------------------------------------

    def send_test(self, subscription_id: str, event_type: str = "Record.Created") -> TestResult:
        """Send a catalog sample of ``event_type`` to the subscription's target, signed as usual.

        A fresh event id and the current time replace the sample's. Nothing is queued, retried or
        recorded: it is a one-shot check of reachability, signature handling and egress policy,
        and the receiver sees ``data.detail`` of the sample. The request carries the header
        ``webhook-test: 1`` so a receiver can tell it from a real delivery. A disabled or expired
        subscription is refused with :class:`SubscriptionNotActiveError`. The result says what
        happened.
        """
        from tl_schema.catalog import sample

        now = self._clock()
        with self._open(readonly=True) as uow:
            row = (
                uow.conn()
                .execute(
                    text(
                        "SELECT target_url, status, expires_at FROM cur_webhook_subscription "
                        "WHERE subscription_id = :s"
                    ),
                    {"s": subscription_id},
                )
                .first()
            )
            if row is None:
                raise LookupError(f"no webhook subscription {subscription_id}")
            if row.status != "active":
                raise SubscriptionNotActiveError(f"subscription {subscription_id} is disabled")
            if row.expires_at is not None and parse_iso(str(row.expires_at)) <= now:
                raise SubscriptionNotActiveError(f"subscription {subscription_id} has expired")
            secrets = self._active_secrets(uow.conn(), subscription_id, now)
        envelope = dict(sample(event_type)["envelope"])
        envelope["id"] = new_ulid()
        envelope["time"] = iso_z(now)
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        claim = Claim(
            delivery_id="test",
            subscription_id=subscription_id,
            scope="",
            seq=0,
            event_id=str(envelope["id"]),
            subject_id="",
            body=body,
            attempts=0,
            created_at=now,
            target_url=str(row.target_url),
            secrets=secrets,
        )
        outcome = self.attempt(claim, extra_headers={TEST_HEADER: "1"})
        result = outcome.result
        return TestResult(
            event_id=claim.event_id,
            status=None if result is None else result.status,
            ok=outcome.ok,
            latency_ms=0 if result is None else result.latency_ms,
            error=outcome.error if result is None else result.error,
            excerpt="" if result is None else result.excerpt,
            blocked=outcome.permanent == "egress_denied",
        )

    # --- convenience -------------------------------------------------------------------------

    def deliver(self, claim: Claim) -> Settled:
        """Attempt and settle one claim."""
        return self.settle(claim, self.attempt(claim))

    def run_cycle(self, limit: int = 10) -> CycleStats:
        """Claim up to ``limit`` heads and deliver them one after another (the worker loop adds
        threads). Returns what happened."""
        stats = CycleStats()
        for claim in self.claim(limit):
            stats.claimed += 1
            settled = self.deliver(claim)
            stats.delivered += settled.state == "delivered"
            stats.retried += settled.state == "retry"
            stats.dead += settled.state == "dead"
            stats.disabled += settled.disabled_subscription
        return stats
