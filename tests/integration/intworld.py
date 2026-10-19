"""Helpers of the integration tests (the name is unique on purpose: L-P1-I0A-1).

``World`` owns a unit-of-work factory and the real command runner of the API table, and writes
through the real handlers, so a test sees what a person, a rule or an endpoint would see.
"""

from __future__ import annotations

import json
from typing import Any

from intfakes import MemStore
from sqlalchemy import text
from tl_adapters.db import create_schema, make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_api.commands import command_runner
from tl_core.auth import accounts
from tl_core.integration.actions.service import (
    ActionDefined,
    DefineAction,
    define_action,
    handle_invoke_action,
)
from tl_core.integration.actions.wiring import action_job_kind
from tl_core.integration.apps import (
    RegisterIntegrationApp,
    SetIntegrationAppEnabled,
    handle_register_app,
    handle_set_app_enabled,
)
from tl_core.integration.contract import InvokeAction
from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
from tl_core.integration.enrichers.service import (
    RegisterEnricher,
    SetEnricherEnabled,
    handle_register_enricher,
    handle_set_enricher_enabled,
)
from tl_core.integration.inbound.gate import accept_delivery, endpoint_view
from tl_core.integration.inbound.service import (
    CreateInboundEndpoint,
    ReviseInboundEndpoint,
    SetInboundEndpointEnabled,
    create_endpoint,
    handle_revise_endpoint,
    handle_set_endpoint_enabled,
)
from tl_core.integration.inbound.store import body_key, put_body
from tl_core.integration.inbound.worker import InboundMapJobKind
from tl_core.integration.rules.engine import RulesWorker
from tl_core.integration.rules.service import (
    CreateRule,
    DisableRule,
    EnableRule,
    ReviseRule,
    handle_create_rule,
    handle_disable_rule,
    handle_enable_rule,
    handle_revise_rule,
)
from tl_core.jobs.runner import JobRunner, RunResult
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.records import handle_create_record
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.util import new_ulid, utcnow
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.rows import as_object, load_json
from tl_core.webhooks.testing import FakeClock, ScriptedTransport

SCOPE = "project:P123"
ADMIN = "user:boss"
PERSON = "user:jsmith"


HOSTS = {"nde.example.net": ["93.184.216.34"], "dev.example.net": ["127.0.0.1"]}


def resolve(host: str, port: int) -> list[str]:
    return HOSTS.get(host, [])


class World:
    def __init__(self, db: Any) -> None:
        self.db = db
        create_schema(db)
        self.factory = make_uow_factory(db)
        self.runner = command_runner()
        self.clock = FakeClock()
        self.transport = ScriptedTransport()
        self.policy = EgressPolicy((), resolve)
        self.store = MemStore()

    def dispose(self) -> None:
        self.factory.dispose()

    # --- writing -----------------------------------------------------------------------------

    def post(self, body: str, *, scope: str = SCOPE, actor: str = PERSON) -> CommandResult:
        with self.factory() as uow:
            return handle_post(uow, PostToFeed(actor=actor, source="test", scope=scope, body=body))

    def record(self, key: str, *, title: str | None = None, scope: str = SCOPE) -> str:
        with self.factory() as uow:
            made = handle_create_record(
                uow,
                CreateRecord(
                    actor=PERSON, source="test", scope=scope, record_type="core.Record",
                    title=title or key, key=key,
                ),
            )  # fmt: skip
        return made.stream_id

    def setting(self, key: str, value: Any, *, layer: str = "company") -> None:
        with self.factory() as uow:
            handle_change_setting(
                uow,
                ChangeSetting(
                    actor=ADMIN,
                    source="test",
                    scope="company",
                    key=key,
                    layer=layer,
                    value=value,
                    reason="test",
                    accept_risk=True,
                ),
            )

    def account(
        self, username: str, *roles: str, kind: str = "person", disabled: bool = False
    ) -> str:
        """An account (the runner resolves a person's access from it); its actor name."""
        with self.factory() as uow:
            made = accounts.create_account(
                uow,
                username=username,
                display_name=username,
                kind=kind,  # type: ignore[arg-type]
                roles=list(roles) or ["user"],
                password=None,
                by=ADMIN,
            )
            if disabled:
                accounts.disable(uow, account_id=made.account_id, by=ADMIN, reason="test")
        return f"agent:{username}" if kind == "agent" else f"user:{username}"

    # --- rules -------------------------------------------------------------------------------

    def create_rule(self, **fields: Any) -> str:
        values: dict[str, Any] = {
            "actor": ADMIN,
            "source": "test",
            "scope": SCOPE,
            "key": "hse-notify",
            "title": "Notify HSE",
            "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
            "then": [{"command": "PostToFeed", "args": {"body": "HSE notified of ${event_id}"}}],
        }
        values.update(fields)
        with self.factory() as uow:
            return handle_create_rule(uow, CreateRule(**values)).stream_id

    def revise_rule(
        self, rule_id: str, changes: dict[str, Any], reason: str = "test", scope: str = SCOPE
    ) -> None:
        with self.factory() as uow:
            handle_revise_rule(
                uow,
                ReviseRule(
                    actor=ADMIN, source="test", scope=scope, rule_id=rule_id,
                    changes=changes, reason=reason,
                ),
            )  # fmt: skip

    def switch_rule(self, rule_id: str, *, on: bool, scope: str = SCOPE) -> None:
        command = (EnableRule if on else DisableRule)(
            actor=ADMIN, source="test", scope=scope, rule_id=rule_id
        )
        with self.factory() as uow:
            (handle_enable_rule if on else handle_disable_rule)(uow, command)  # type: ignore[arg-type]

    def worker(self) -> RulesWorker:
        return RulesWorker(self.factory, self.runner, clock=self.clock)

    # --- reading -----------------------------------------------------------------------------

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with self.factory(readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def events(self, event_type: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT event_id, seq, scope, actor, source, correlation_id, causation_id, stream_id, "
            "payload FROM events WHERE event_type = :t ORDER BY seq",
            t=event_type,
        )

    def posts(self) -> list[dict[str, Any]]:
        """Every ``Feed.Posted`` event with its payload parsed (``body``, ``hashtags``...)."""
        out: list[dict[str, Any]] = []
        for row in self.events("Feed.Posted"):
            out.append({**as_object(load_json(row["payload"])), **row})
        return out

    def firings(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM rule_firing ORDER BY seq, rule_id")

    def cursor(self) -> int:
        found = self.rows("SELECT last_seq FROM rule_cursor WHERE name = 'rules'")
        return int(found[0]["last_seq"]) if found else 0

    # --- inbound -----------------------------------------------------------------------------

    def endpoint(
        self, name: str = "orders", *, on: bool = True, live: bool = True, **over: Any
    ) -> Any:
        """An enabled, live (not dry-run) endpoint of the app ``erp``; returns what create gave."""
        app = over.get("app", "erp")
        with self.factory() as uow:
            known = uow.conn().execute(
                text("SELECT 1 FROM cur_integration_app WHERE name = :n"), {"n": app}
            )
            if known.first() is None:
                handle_register_app(
                    uow,
                    RegisterIntegrationApp(
                        actor=ADMIN, source="test", scope=SCOPE, name=app, label=app
                    ),
                )
        values: dict[str, Any] = {
            "actor": ADMIN,
            "source": "test",
            "scope": SCOPE,
            "app": "erp",
            "name": name,
            "mapping": '{"command": "PostToFeed", "args": {"body": $.text}}',
            "allowed_commands": ["PostToFeed"],
        }
        values.update(over)
        with self.factory() as uow:
            made = create_endpoint(uow, CreateInboundEndpoint(**values))
        if live:
            with self.factory() as uow:
                handle_revise_endpoint(
                    uow,
                    ReviseInboundEndpoint(
                        actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id,
                        changes={"dry_run": False}, reason="go live",
                    ),
                )  # fmt: skip
        if on:
            with self.factory() as uow:
                handle_set_endpoint_enabled(
                    uow,
                    SetInboundEndpointEnabled(
                        actor=ADMIN,
                        source="test",
                        scope=SCOPE,
                        endpoint_id=made.endpoint_id,
                        enabled=True,
                    ),
                )
        return made

    def switch_endpoint(self, endpoint_id: str, on: bool) -> None:
        with self.factory() as uow:
            handle_set_endpoint_enabled(
                uow,
                SetInboundEndpointEnabled(
                    actor=ADMIN, source="test", scope=SCOPE, endpoint_id=endpoint_id, enabled=on
                ),
            )

    def deliver(self, endpoint_id: str, payload: Any, *, message_id: str | None = None) -> str:
        """Store a body and accept it as the route does (no signature); returns the delivery id."""
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        delivery_id = new_ulid()
        key = body_key(endpoint_id, delivery_id)
        digest = put_body(self.store, key, body)
        with self.factory() as uow:
            row = endpoint_view(uow.conn(), endpoint_id)
            assert row is not None
            accept_delivery(
                uow, row, message_id=message_id or new_ulid(), delivery_id=delivery_id,
                object_key=key, payload_sha256=digest, payload_size=len(body), now=utcnow(),
            )  # fmt: skip
        return delivery_id

    def inbound_runner(self, **kw: Any) -> JobRunner:
        with self.factory(readonly=True) as uow:
            queue = job_queue_for(uow.conn())
        kind = InboundMapJobKind(self.runner, self.store, **kw)
        return JobRunner(self.factory, queue, [kind], worker_id="test", retry_base_s=0.0)

    def deliveries(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM int_delivery ORDER BY received_at, delivery_id")

    # --- enrichers ---------------------------------------------------------------------------

    def register_enricher(self, **fields: Any) -> str:
        values: dict[str, Any] = {
            "actor": ADMIN,
            "source": "test",
            "scope": SCOPE,
            "name": "fake",
            "when": {"event_types": ["Record.Created"]},
            "properties": [{"name": "label", "kind": "string"}],
        }
        values.update(fields)
        with self.factory() as uow:
            return handle_register_enricher(uow, RegisterEnricher(**values)).stream_id

    def dispatcher(self, **kw: Any) -> EnrichmentDispatcher:
        return EnrichmentDispatcher(self.factory, clock=self.clock, **kw)

    def values(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM cur_enrichment_value ORDER BY seq")

    def layer(self, record_id: str, enricher: str = "fake") -> dict[str, Any]:
        row = self.rows("SELECT psets_json FROM cur_core_record WHERE id = :i", i=record_id)[0]
        psets = as_object(load_json(row["psets_json"]))
        return as_object(as_object(psets.get("enrich", {})).get(enricher, {}))

    def app(self, name: str) -> str:
        """Register the integration app ``name`` (switched on); its id."""
        with self.factory() as uow:
            return handle_register_app(
                uow,
                RegisterIntegrationApp(
                    actor=ADMIN, source="test", scope=SCOPE, name=name, label=name
                ),
            ).stream_id

    def switch_app(self, name: str, *, on: bool) -> None:
        app_id = self.rows("SELECT app_id FROM cur_integration_app WHERE name = :n", n=name)[0][
            "app_id"
        ]
        with self.factory() as uow:
            handle_set_app_enabled(
                uow,
                SetIntegrationAppEnabled(
                    actor=ADMIN, source="test", scope=SCOPE, app_id=app_id, enabled=on
                ),
            )

    def switch_enricher(self, enricher_id: str, *, on: bool, scope: str = SCOPE) -> None:
        with self.factory() as uow:
            handle_set_enricher_enabled(
                uow,
                SetEnricherEnabled(
                    actor=ADMIN, source="test", scope=scope, enricher_id=enricher_id, enabled=on
                ),
            )

    # --- actions -----------------------------------------------------------------------------

    def define_action(self, **fields: Any) -> ActionDefined:
        values: dict[str, Any] = {
            "actor": ADMIN,
            "source": "test",
            "scope": SCOPE,
            "name": "send_to_nde",
            "label": "Send to NDE",
            "executor": "webhook",
            "executor_config": {"url": "https://nde.example.net/hooks/request"},
            "side_effect_class": "external",
        }
        values.update(fields)
        with self.factory() as uow:
            return define_action(uow, DefineAction(**values), policy=self.policy)

    def invoke(
        self,
        action: str = "send_to_nde",
        *,
        targets: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        holds: Any = None,
        actor: str = PERSON,
        scope: str = SCOPE,
    ) -> CommandResult:
        command = InvokeAction(
            actor=actor, source="test", scope=scope, action=action,
            targets=targets or [], parameters=parameters or {},
        )  # fmt: skip
        with self.factory() as uow:
            return handle_invoke_action(uow, command, holds=holds)

    def job_runner(self) -> JobRunner:
        with self.factory(readonly=True) as uow:
            queue = job_queue_for(uow.conn())
        kind = action_job_kind(self.factory, policy=self.policy, transport=self.transport)
        return JobRunner(self.factory, queue, [kind], worker_id="test", retry_base_s=0.0)

    def run_jobs(self) -> list[RunResult]:
        return self.job_runner().run_until_idle()

    def invocations(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM cur_action_invocation ORDER BY seq")
