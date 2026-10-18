"""Projectors of the integration layer: one ``cur_*`` table per record stream (P1-I7, ADR-0017).

Like ``WebhookSubscriptionProjector``, each projector is deterministic: every value comes from the
event, no secret is in any event, and a rebuild reproduces the rows. A revision event carries the
whole new definition, so a row is replaced by what the event says, never merged from hidden state.

``IntegrationStateTables`` creates the operational tables (``int_secret``, ``int_replay``,
``int_delivery``, ``int_counter``, ``rule_cursor``, ``rule_firing``, ``enrich_cursor``). They are
not projections: a rebuild must never clear them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.integration.streams import (
    ACTION_COMPLETED,
    ACTION_DEFINED,
    ACTION_DEFINITION_EVENT_TYPES,
    ACTION_FAILED,
    ACTION_INVOCATION_EVENT_TYPES,
    ACTION_REQUESTED,
    ACTION_RETIRED,
    ACTION_REVISED,
    ACTION_RUNNING,
    ACTION_SECRET_ROTATED,
    APP_DISABLED,
    APP_ENABLED,
    APP_EVENT_TYPES,
    APP_REGISTERED,
    APP_REVISED,
    ENDPOINT_CREATED,
    ENDPOINT_DISABLED,
    ENDPOINT_ENABLED,
    ENDPOINT_EVENT_TYPES,
    ENDPOINT_REVISED,
    ENDPOINT_SECRET_ROTATED,
    ENRICHER_DISABLED,
    ENRICHER_ENABLED,
    ENRICHER_EVENT_TYPES,
    ENRICHER_REGISTERED,
    ENRICHER_REVISED,
    ENRICHMENT_ACCEPTED,
    ENRICHMENT_EVENT_TYPES,
    ENRICHMENT_PROPOSED,
    ENRICHMENT_REJECTED,
    RULE_BLOCKED,
    RULE_CREATED,
    RULE_DISABLED,
    RULE_ENABLED,
    RULE_EVENT_TYPES,
    RULE_REVISED,
)
from tl_core.ledger import Event, iso_utc
from tl_core.webhooks.rows import as_list, as_object, dumps, load_json

#: Operational tables created next to the projections and never rebuilt (FANOUT D13).
OPERATIONAL_TABLES = (
    "int_secret",
    "int_replay",
    "int_delivery",
    "int_counter",
    "rule_cursor",
    "rule_firing",
    "enrich_cursor",
)

#: payload key -> (column, stored as JSON). Column names never come from event data.
_Fields = Mapping[str, tuple[str, bool]]


def _insert(conn: Connection, table: str, values: Mapping[str, Any]) -> None:
    columns = ", ".join(values)
    marks = ", ".join(f":{name}" for name in values)
    conn.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({marks})"), dict(values))


def _update(
    conn: Connection, table: str, id_column: str, id_value: str, values: Mapping[str, Any]
) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in values)
    done = conn.execute(
        text(f"UPDATE {table} SET {assignments} WHERE {id_column} = :_id"),
        {**values, "_id": id_value},
    )
    if done.rowcount == 0:
        raise LookupError(f"no row of {table} for {id_column} {id_value}")


def _take(payload: Mapping[str, Any], fields: _Fields) -> dict[str, Any]:
    """The columns the payload names, JSON ones as canonical text."""
    found: dict[str, Any] = {}
    for key, (column, is_json) in fields.items():
        if key in payload:
            value = payload[key]
            found[column] = dumps(value) if is_json and value is not None else value
    return found


def _stamp(event: Event) -> dict[str, Any]:
    return {
        "updated_at": iso_utc(event.recorded_at),
        "stream_version": event.stream_version,
        "last_seq": event.seq,
    }


class _Base:
    """Shared plumbing: the table, its DDL and its reset."""

    name = ""
    table = ""
    id_column = ""
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            found: list[str] = []
            for table in self.tables():
                found.extend(statements(table, dialect))
            return found
        raise ValueError(f"unsupported dialect: {dialect}")

    def tables(self) -> tuple[str, ...]:
        return (self.table,)

    def reset(self, conn: Connection) -> None:
        for table in self.tables():
            conn.execute(text(f"DELETE FROM {table}"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type not in self.handles:
            raise ValueError(f"{type(self).__name__} cannot apply: {event.event_type}")
        self.handle(conn, event)

    def handle(self, conn: Connection, event: Event) -> None:
        raise NotImplementedError


# --- integration apps -----------------------------------------------------------------------------


class IntegrationAppProjector(_Base):
    name = "integration_apps"
    table = "cur_integration_app"
    id_column = "app_id"
    handles = APP_EVENT_TYPES

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == APP_REGISTERED:
            _insert(
                conn,
                self.table,
                {
                    "app_id": event.stream_id,
                    "scope": event.scope,
                    "name": payload["name"],
                    "label": payload["label"],
                    "description": payload.get("description"),
                    "owner": payload["owner"],
                    "enabled": bool(payload.get("enabled", True)),
                    "created_by": event.actor,
                    "created_at": stamp,
                    "updated_at": stamp,
                    "version": event.stream_version,
                    "last_seq": event.seq,
                },
            )
            return
        changes: dict[str, Any] = {
            "updated_at": stamp,
            "version": event.stream_version,
            "last_seq": event.seq,
        }
        if event.event_type == APP_REVISED:
            for field, pair in as_object(payload.get("changes")).items():
                if field not in ("label", "description", "owner"):
                    raise ValueError(f"cannot revise integration app field {field!r}")
                changes[field] = as_list(pair)[1]
        elif event.event_type == APP_ENABLED:
            changes["enabled"] = True
        elif event.event_type == APP_DISABLED:
            changes["enabled"] = False
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- action definitions ---------------------------------------------------------------------------

_DEFINITION_FIELDS: _Fields = {
    "label": ("label", False),
    "description": ("description", False),
    "version": ("version", False),
    "applies_to": ("applies_to_json", True),
    "parameters": ("parameters_json", True),
    "executor": ("executor", False),
    "executor_config": ("executor_config_json", True),
    "side_effect_class": ("side_effect_class", False),
    "requires_approval": ("requires_approval", False),
    "access": ("access", False),
    "result_handling": ("result_handling_json", True),
    "owner": ("owner", False),
    "enabled": ("enabled", False),
    "integration_app": ("integration_app", False),
}


class ActionDefinitionProjector(_Base):
    name = "action_definitions"
    table = "cur_action_definition"
    id_column = "definition_id"
    handles = ACTION_DEFINITION_EVENT_TYPES

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == ACTION_DEFINED:
            values = _take(payload, _DEFINITION_FIELDS)
            values.setdefault("enabled", True)
            values.setdefault("requires_approval", False)
            _insert(
                conn,
                self.table,
                {
                    "definition_id": event.stream_id,
                    "name": payload["name"],
                    "scope": event.scope,
                    "retired": False,
                    "secret_id": payload.get("secret_id"),
                    "created_by": event.actor,
                    "created_at": stamp,
                    **values,
                    **_stamp(event),
                },
            )
            return
        changes = _stamp(event)
        if event.event_type == ACTION_REVISED:
            changes.update(_take(as_object(payload.get("definition")), _DEFINITION_FIELDS))
            changes["version"] = payload["version"]
        elif event.event_type == ACTION_RETIRED:
            changes.update(retired=True, enabled=False)
        elif event.event_type == ACTION_SECRET_ROTATED:
            changes["secret_id"] = payload["secret_id"]
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- action invocations ---------------------------------------------------------------------------


class ActionInvocationProjector(_Base):
    name = "action_invocations"
    table = "cur_action_invocation"
    id_column = "invocation_id"
    handles = ACTION_INVOCATION_EVENT_TYPES

    def tables(self) -> tuple[str, ...]:
        return ("cur_action_invocation", "cur_action_invocation_target")

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == ACTION_REQUESTED:
            targets = as_list(payload.get("targets"))
            _insert(
                conn,
                self.table,
                {
                    "invocation_id": event.stream_id,
                    "scope": event.scope,
                    "action": payload["action"],
                    "action_version": payload["action_version"],
                    "definition_id": payload["definition_id"],
                    "status": "requested",
                    "targets_json": dumps(targets),
                    "parameters_json": dumps(payload.get("parameters") or {}),
                    "invoked_by": payload["invoked_by"],
                    "attempt": 0,
                    "requested_at": stamp,
                    "proposal_id": payload.get("proposal_id"),
                    "seq": event.seq,
                    "version": event.stream_version,
                    "last_seq": event.seq,
                },
            )
            for index, target in enumerate(targets):
                ref = as_object(target)
                _insert(
                    conn,
                    "cur_action_invocation_target",
                    {
                        "target_id": f"{event.event_id}:{index}",
                        "invocation_id": event.stream_id,
                        "record_id": ref.get("id"),
                        "record_key": ref.get("key"),
                        "record_type": ref.get("record_type"),
                        "record_version": ref.get("version"),
                    },
                )
            return
        changes: dict[str, Any] = {"version": event.stream_version, "last_seq": event.seq}
        if event.event_type == ACTION_RUNNING:
            changes.update(status="running", attempt=payload["attempt"], started_at=stamp)
        elif event.event_type == ACTION_COMPLETED:
            changes.update(
                status="completed",
                attempt=payload["attempt"],
                finished_at=stamp,
                http_status=payload.get("http_status"),
                result_json=None if payload.get("result") is None else dumps(payload["result"]),
            )
        elif event.event_type == ACTION_FAILED:
            changes.update(
                status="failed",
                attempt=payload["attempt"],
                finished_at=stamp,
                http_status=payload.get("http_status"),
                problems_json=dumps(payload.get("problems") or []),
            )
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- rules ----------------------------------------------------------------------------------------

_RULE_FIELDS: _Fields = {
    "title": ("title", False),
    "version": ("version", False),
    "when": ("when_json", True),
    "condition": ("condition", False),
    "then": ("then_json", True),
    "mode": ("mode", False),
    "service_actor": ("service_actor", False),
    "access": ("access", False),
    "owner": ("owner", False),
    "enabled": ("enabled", False),
    "integration_app": ("integration_app", False),
}


class RuleProjector(_Base):
    name = "rules"
    table = "cur_rule"
    id_column = "rule_id"
    handles = RULE_EVENT_TYPES

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == RULE_CREATED:
            values = _take(payload, _RULE_FIELDS)
            values.setdefault("enabled", False)
            values.setdefault("mode", "propose")
            _insert(
                conn,
                self.table,
                {
                    "rule_id": event.stream_id,
                    "key": payload["key"],
                    "scope": event.scope,
                    "created_by": event.actor,
                    "created_at": stamp,
                    "enabled_from_seq": event.seq if values["enabled"] else 0,
                    **values,
                    **_stamp(event),
                },
            )
            return
        changes = _stamp(event)
        if event.event_type == RULE_REVISED:
            changes.update(_take(as_object(payload.get("rule")), _RULE_FIELDS))
            changes["version"] = payload["version"]
        elif event.event_type == RULE_ENABLED:
            changes.update(enabled=True, enabled_from_seq=event.seq)
        elif event.event_type == RULE_DISABLED:
            changes["enabled"] = False
        elif event.event_type != RULE_BLOCKED:
            raise ValueError(f"RuleProjector cannot apply: {event.event_type}")
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- inbound endpoints ----------------------------------------------------------------------------

_ENDPOINT_FIELDS: _Fields = {
    "version": ("version", False),
    "auth": ("auth", False),
    "mapping": ("mapping", False),
    "mapping_language": ("mapping_language", False),
    "external_schema": ("external_schema", False),
    "allowed_commands": ("allowed_commands_json", True),
    "service_actor": ("service_actor", False),
    "access": ("access", False),
    "max_body_bytes": ("max_body_bytes", False),
    "rate_per_minute": ("rate_per_minute", False),
    "dry_run": ("dry_run", False),
    "enabled": ("enabled", False),
    "owner": ("owner", False),
}
#: What a version snapshot holds: the endpoint model, never an id, a secret or a timestamp.
_SNAPSHOT_KEYS = (
    "app",
    "name",
    "version",
    "auth",
    "mapping",
    "mapping_language",
    "external_schema",
    "allowed_commands",
    "service_actor",
    "access",
    "max_body_bytes",
    "rate_per_minute",
    "dry_run",
    "enabled",
    "owner",
)


class InboundEndpointProjector(_Base):
    name = "inbound_endpoints"
    table = "cur_inbound_endpoint"
    id_column = "endpoint_id"
    handles = ENDPOINT_EVENT_TYPES

    def tables(self) -> tuple[str, ...]:
        return ("cur_inbound_endpoint", "cur_inbound_endpoint_version")

    @staticmethod
    def _snapshot(conn: Connection, event: Event, version: int) -> None:
        row = (
            conn.execute(
                text("SELECT * FROM cur_inbound_endpoint WHERE endpoint_id = :i"),
                {"i": event.stream_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise LookupError(f"no endpoint row for stream {event.stream_id}")
        definition: dict[str, Any] = {}
        for key in _SNAPSHOT_KEYS:
            column = "allowed_commands_json" if key == "allowed_commands" else key
            value = row[column]
            if key == "allowed_commands":
                value = as_list(load_json(value))
            elif key in ("dry_run", "enabled"):
                value = bool(value)
            definition[key] = value
        _insert(
            conn,
            "cur_inbound_endpoint_version",
            {
                "version_id": event.event_id,
                "endpoint_id": event.stream_id,
                "version": version,
                "definition_json": dumps(definition),
                "seq": event.seq,
            },
        )

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == ENDPOINT_CREATED:
            values = _take(payload, _ENDPOINT_FIELDS)
            values.setdefault("dry_run", True)
            values.setdefault("enabled", False)
            _insert(
                conn,
                self.table,
                {
                    "endpoint_id": event.stream_id,
                    "app": payload["app"],
                    "name": payload["name"],
                    "scope": event.scope,
                    "current_secret_id": payload.get("secret_id"),
                    "created_by": event.actor,
                    "created_at": stamp,
                    **values,
                    **_stamp(event),
                },
            )
            self._snapshot(conn, event, int(payload["version"]))
            return
        changes = _stamp(event)
        if event.event_type == ENDPOINT_REVISED:
            changes.update(_take(as_object(payload.get("endpoint")), _ENDPOINT_FIELDS))
            changes["version"] = payload["version"]
        elif event.event_type == ENDPOINT_ENABLED:
            changes["enabled"] = True
        elif event.event_type == ENDPOINT_DISABLED:
            changes["enabled"] = False
        elif event.event_type == ENDPOINT_SECRET_ROTATED:
            changes["current_secret_id"] = payload["secret_id"]
        _update(conn, self.table, self.id_column, event.stream_id, changes)
        if event.event_type == ENDPOINT_REVISED:
            self._snapshot(conn, event, int(payload["version"]))


# --- enrichers ------------------------------------------------------------------------------------

_ENRICHER_FIELDS: _Fields = {
    "version": ("version", False),
    "code_version": ("code_version", False),
    "model_ref": ("model_ref", False),
    "when": ("when_json", True),
    "properties": ("properties_json", True),
    "service_actor": ("service_actor", False),
    "access": ("access", False),
    "owner": ("owner", False),
    "enabled": ("enabled", False),
    "integration_app": ("integration_app", False),
}


class EnricherProjector(_Base):
    name = "enrichers"
    table = "cur_enricher"
    id_column = "enricher_id"
    handles = ENRICHER_EVENT_TYPES

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        if event.event_type == ENRICHER_REGISTERED:
            values = _take(payload, _ENRICHER_FIELDS)
            values.setdefault("enabled", False)
            _insert(
                conn,
                self.table,
                {
                    "enricher_id": event.stream_id,
                    "name": payload["name"],
                    "scope": event.scope,
                    "created_by": event.actor,
                    "created_at": stamp,
                    "enabled_from_seq": event.seq if values["enabled"] else 0,
                    **values,
                    **_stamp(event),
                },
            )
            return
        changes = _stamp(event)
        if event.event_type == ENRICHER_REVISED:
            changes.update(_take(as_object(payload.get("enricher")), _ENRICHER_FIELDS))
            changes["version"] = payload["version"]
        elif event.event_type == ENRICHER_ENABLED:
            changes.update(enabled=True, enabled_from_seq=event.seq)
        elif event.event_type == ENRICHER_DISABLED:
            changes["enabled"] = False
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- enrichment values ----------------------------------------------------------------------------


class EnrichmentValueProjector(_Base):
    name = "enrichment_values"
    table = "cur_enrichment_value"
    id_column = "value_id"
    handles = ENRICHMENT_EVENT_TYPES

    def handle(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        if event.event_type == ENRICHMENT_PROPOSED:
            target = as_object(payload["target"])
            _insert(
                conn,
                self.table,
                {
                    "value_id": event.stream_id,
                    "scope": event.scope,
                    "target_json": dumps(target),
                    "target_id": target["id"],
                    "property_path": payload["property_path"],
                    "value_json": None if payload.get("value") is None else dumps(payload["value"]),
                    "enricher": payload["enricher"],
                    "enricher_version": payload["enricher_version"],
                    "confidence": payload["confidence"],
                    "inputs_json": dumps(payload.get("inputs") or []),
                    "model_ref": payload.get("model_ref"),
                    "produced_at": payload["produced_at"],
                    "acceptance_state": payload["acceptance_state"],
                    "seq": event.seq,
                    "version": event.stream_version,
                    "last_seq": event.seq,
                },
            )
            return
        changes: dict[str, Any] = {
            "version": event.stream_version,
            "last_seq": event.seq,
            "decided_by": payload["by"],
            "decided_at": iso_utc(event.recorded_at),
        }
        if event.event_type == ENRICHMENT_ACCEPTED:
            changes["acceptance_state"] = "auto_accepted" if payload["automatic"] else "accepted"
        elif event.event_type == ENRICHMENT_REJECTED:
            changes.update(acceptance_state="rejected", reason=payload["reason"])
        _update(conn, self.table, self.id_column, event.stream_id, changes)


# --- operational tables ---------------------------------------------------------------------------


class IntegrationStateTables:
    """The operational tables, created with the rest of the schema and never reset by a rebuild."""

    name = "integration_state"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        found: list[str] = []
        for table in OPERATIONAL_TABLES:
            found.extend(statements(table, dialect))
        return found

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: operational state is not rebuilt from the ledger."""


def integration_projectors() -> list[_Base]:
    """The record projectors, in registration order."""
    return [
        IntegrationAppProjector(),
        ActionDefinitionProjector(),
        ActionInvocationProjector(),
        RuleProjector(),
        InboundEndpointProjector(),
        EnricherProjector(),
        EnrichmentValueProjector(),
    ]
