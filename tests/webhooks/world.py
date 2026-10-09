"""A small world for the webhook tests: a SQLite ledger, a clock, a scripted network."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.records import handle_create_record, handle_update_record
from tl_core.util import new_ulid
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import HealthPolicy, RetryPolicy
from tl_core.webhooks.subscriptions import (
    CreateWebhookSubscription,
    SecretIssued,
    create_subscription,
)
from tl_core.webhooks.testing import FakeClock, ScriptedTransport

SCOPE = "project:P1"


@dataclass
class World:
    """One ledger, one clock, and helpers that write through the real command handlers."""

    path: Path
    factory: SqliteUowFactory
    clock: FakeClock
    transport: ScriptedTransport
    resolver_calls: list[str] = field(default_factory=list[str])

    # --- writing -----------------------------------------------------------------------------

    def record(self, key: str, *, scope: str = SCOPE, title: str | None = None) -> str:
        with self.factory() as uow:
            result = handle_create_record(
                uow,
                CreateRecord(
                    actor="user:alice",
                    source="test",
                    scope=scope,
                    record_type="core.Record",
                    title=title or key,
                    key=key,
                ),
            )
        return result.stream_id

    def retitle(self, record_id: str, title: str, *, version: int, scope: str = SCOPE) -> int:
        with self.factory() as uow:
            result = handle_update_record(
                uow,
                UpdateRecord(
                    actor="user:alice",
                    source="test",
                    scope=scope,
                    stream_id=record_id,
                    expected_version=version,
                    changes={"title": title},
                ),
            )
        return result.version

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        stream_id: str | None = None,
        stream_type: str = "core.Record",
        scope: str = SCOPE,
        version: int | None = None,
    ) -> Event:
        """Append one raw event (for event types that have no command handler in this branch)."""
        sid = stream_id or new_ulid()
        with self.factory() as uow:
            expected = uow.ledger.stream_version(sid) if version is None else version
            result = uow.append(
                stream_id=sid,
                stream_type=stream_type,
                scope=scope,
                expected_version=expected,
                events=[NewEvent(event_type=event_type, payload=payload)],
                actor="user:alice",
                source="test",
                correlation_id=new_ulid(),
            )
        return result.events[0]

    def subscribe(
        self,
        *,
        filter: dict[str, Any] | None = None,
        mode: str = "thin",
        scope: str = SCOPE,
        url: str = "https://hook.test/in",
        name: str = "test hook",
    ) -> SecretIssued:
        with self.factory() as uow:
            return create_subscription(
                uow,
                CreateWebhookSubscription(
                    actor="user:alice",
                    source="test",
                    scope=scope,
                    name=name,
                    target_url=url,
                    filter=filter or {},
                    payload_mode=mode,
                ),
                clock=self.clock,
            )

    # --- machinery ---------------------------------------------------------------------------

    def resolver(self, host: str, port: int) -> list[str]:
        self.resolver_calls.append(host)
        return ["93.184.216.34"]

    def dispatcher(self, **kw: Any) -> Dispatcher:
        return Dispatcher(self.factory, clock=self.clock, **kw)

    def engine(
        self,
        *,
        worker_id: str = "w1",
        retry: RetryPolicy | None = None,
        health: HealthPolicy | None = None,
        egress: EgressPolicy | None = None,
        lease_s: float = 60.0,
    ) -> DeliveryEngine:
        return DeliveryEngine(
            self.factory,
            self.transport,
            egress=egress or EgressPolicy((), self.resolver),
            retry=retry or RetryPolicy(base_s=10, jitter=0),
            health=health,
            clock=self.clock,
            rng=random.Random(1),
            worker_id=worker_id,
            lease_s=lease_s,
        )

    def query(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self.factory(readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]
