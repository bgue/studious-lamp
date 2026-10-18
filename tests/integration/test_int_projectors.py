"""The record projectors of the integration layer fold their events into the right rows (ADR-0017).

Events are appended with the real unit of work on each adapter, so the rows are read back from
the tables the generated DDL made, not from a fake.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.integration import streams as s
from tl_core.integration.projectors import OPERATIONAL_TABLES
from tl_core.ledger import NewEvent
from tl_core.projection.defaults import default_registry
from tl_core.util import new_ulid
from tl_core.webhooks.rows import as_list, load_json

SCOPE = "project:P123"
ACTOR = "user:jsmith"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def append(
    db: DbTarget, stream_id: str, stream_type: str, version: int, kind: str, payload: dict[str, Any]
) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=stream_id,
            stream_type=stream_type,
            scope=SCOPE,
            expected_version=version,
            events=[NewEvent(event_type=kind, payload=payload)],
            actor=ACTOR,
            source="test",
            correlation_id=new_ulid(),
        )


def row(db: DbTarget, table: str, column: str, value: str) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = (
            uow.conn()
            .execute(text(f"SELECT * FROM {table} WHERE {column} = :v"), {"v": value})  # noqa: S608
            .mappings()
            .first()
        )
    assert found is not None, f"no row in {table}"
    return dict(found)


def rows(db: DbTarget, table: str) -> list[dict[str, Any]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(f"SELECT * FROM {table}")).mappings()]  # noqa: S608


def test_every_event_type_of_the_layer_has_a_projector_or_is_bookkeeping() -> None:
    handled: set[str] = set()
    for projector in default_registry().all():
        handled |= set(projector.handles)
    # the inbound delivery events are bookkeeping on the operational ``int_delivery`` row
    expected = s.INTEGRATION_EVENT_TYPES - s.DELIVERY_EVENT_TYPES
    assert expected <= handled
    assert not (s.DELIVERY_EVENT_TYPES & handled)


def test_the_operational_tables_are_created_and_a_rebuild_leaves_them_alone(db: DbTarget) -> None:
    with open_uow(db) as uow:
        for table in OPERATIONAL_TABLES:
            assert uow.conn().execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0  # noqa: S608
        uow.conn().execute(text("INSERT INTO rule_cursor (name, last_seq) VALUES ('rules', 7)"))
    registry = default_registry()
    with open_uow(db) as uow:
        for projector in registry.all():
            projector.reset(uow.conn())
    assert rows(db, "rule_cursor") == [{"name": "rules", "last_seq": 7}]


def test_an_app_is_registered_revised_and_switched(db: DbTarget) -> None:
    app = new_ulid()
    append(
        db,
        app,
        s.APP_STREAM_TYPE,
        0,
        s.APP_REGISTERED,
        {"app_id": app, "name": "acme-nde", "label": "Acme NDE", "owner": ACTOR},
    )
    append(
        db, app, s.APP_STREAM_TYPE, 1, s.APP_REVISED, {"changes": {"label": ["Acme NDE", "NDE"]}}
    )
    append(db, app, s.APP_STREAM_TYPE, 2, s.APP_DISABLED, {"reason": "test"})
    found = row(db, "cur_integration_app", "app_id", app)
    assert (found["label"], bool(found["enabled"]), found["version"]) == ("NDE", False, 3)
    append(db, app, s.APP_STREAM_TYPE, 3, s.APP_ENABLED, {})
    assert bool(row(db, "cur_integration_app", "app_id", app)["enabled"]) is True


def test_an_app_name_is_unique(db: DbTarget) -> None:
    first, second = new_ulid(), new_ulid()
    append(
        db,
        first,
        s.APP_STREAM_TYPE,
        0,
        s.APP_REGISTERED,
        {"app_id": first, "name": "dup", "label": "x", "owner": ACTOR},
    )
    with pytest.raises(Exception):  # noqa: B017 - the driver's integrity error
        append(
            db,
            second,
            s.APP_STREAM_TYPE,
            0,
            s.APP_REGISTERED,
            {"app_id": second, "name": "dup", "label": "y", "owner": ACTOR},
        )
    assert len(rows(db, "cur_integration_app")) == 1


DEFINITION: dict[str, Any] = {
    "name": "send_to_nde",
    "label": "Send to NDE",
    "version": 1,
    "applies_to": {"record_types": ["core.Record"], "condition": None},
    "parameters": [],
    "executor": "webhook",
    "executor_config": {"kind": "webhook", "url": "https://nde.example.net/h", "timeout_s": 10.0},
    "side_effect_class": "external",
    "requires_approval": False,
    "access": "user",
    "result_handling": ["store"],
    "owner": ACTOR,
    "enabled": True,
}


def test_an_action_definition_is_defined_revised_and_retired(db: DbTarget) -> None:
    definition = new_ulid()
    append(
        db,
        definition,
        s.ACTION_DEFINITION_STREAM_TYPE,
        0,
        s.ACTION_DEFINED,
        {"definition_id": definition, **DEFINITION, "secret_id": new_ulid()},
    )
    found = row(db, "cur_action_definition", "definition_id", definition)
    assert found["name"] == "send_to_nde" and found["version"] == 1
    assert load_json(found["executor_config_json"])["url"] == "https://nde.example.net/h"
    revised = {**DEFINITION, "version": 2, "label": "Send to NDE contractor"}
    append(
        db,
        definition,
        s.ACTION_DEFINITION_STREAM_TYPE,
        1,
        s.ACTION_REVISED,
        {"definition_id": definition, "version": 2, "definition": revised, "reason": "label"},
    )
    found = row(db, "cur_action_definition", "definition_id", definition)
    assert (found["version"], found["label"], found["stream_version"]) == (
        2,
        "Send to NDE contractor",
        2,
    )
    new_secret = new_ulid()
    append(
        db,
        definition,
        s.ACTION_DEFINITION_STREAM_TYPE,
        2,
        s.ACTION_SECRET_ROTATED,
        {"definition_id": definition, "secret_id": new_secret},
    )
    append(
        db,
        definition,
        s.ACTION_DEFINITION_STREAM_TYPE,
        3,
        s.ACTION_RETIRED,
        {"definition_id": definition, "reason": "gone"},
    )
    found = row(db, "cur_action_definition", "definition_id", definition)
    assert found["secret_id"] == new_secret
    assert bool(found["retired"]) is True and bool(found["enabled"]) is False


def test_an_invocation_runs_through_its_lifecycle_and_keeps_its_targets(db: DbTarget) -> None:
    invocation = new_ulid()
    target = {"id": new_ulid(), "key": "47-1234-W012", "record_type": "core.Record", "version": 3}
    append(
        db,
        invocation,
        s.ACTION_INVOCATION_STREAM_TYPE,
        0,
        s.ACTION_REQUESTED,
        {
            "invocation_id": invocation,
            "action": "send_to_nde",
            "action_version": 1,
            "definition_id": new_ulid(),
            "targets": [target],
            "parameters": {"method": "RT"},
            "invoked_by": ACTOR,
        },
    )
    found = row(db, "cur_action_invocation", "invocation_id", invocation)
    assert found["status"] == "requested" and found["attempt"] == 0
    assert row(db, "cur_action_invocation_target", "invocation_id", invocation)["record_key"] == (
        "47-1234-W012"
    )
    append(
        db,
        invocation,
        s.ACTION_INVOCATION_STREAM_TYPE,
        1,
        s.ACTION_RUNNING,
        {"invocation_id": invocation, "attempt": 1},
    )
    assert row(db, "cur_action_invocation", "invocation_id", invocation)["status"] == "running"
    append(
        db,
        invocation,
        s.ACTION_INVOCATION_STREAM_TYPE,
        2,
        s.ACTION_COMPLETED,
        {"invocation_id": invocation, "attempt": 1, "result": {"ok": True}, "http_status": 200},
    )
    found = row(db, "cur_action_invocation", "invocation_id", invocation)
    assert found["status"] == "completed" and found["http_status"] == 200
    assert load_json(found["result_json"]) == {"ok": True}


def test_a_failed_invocation_keeps_its_problems(db: DbTarget) -> None:
    invocation = new_ulid()
    append(
        db,
        invocation,
        s.ACTION_INVOCATION_STREAM_TYPE,
        0,
        s.ACTION_REQUESTED,
        {
            "invocation_id": invocation,
            "action": "a",
            "action_version": 1,
            "definition_id": new_ulid(),
            "targets": [],
            "parameters": {},
            "invoked_by": ACTOR,
        },
    )
    append(
        db,
        invocation,
        s.ACTION_INVOCATION_STREAM_TYPE,
        1,
        s.ACTION_FAILED,
        {
            "invocation_id": invocation,
            "attempt": 3,
            "problems": [{"code": "http_error", "message": "503"}],
        },
    )
    found = row(db, "cur_action_invocation", "invocation_id", invocation)
    assert found["status"] == "failed"
    assert as_list(load_json(found["problems_json"]))[0]["code"] == "http_error"


RULE: dict[str, Any] = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "version": 1,
    "when": {"hashtags": ["safety"]},
    "condition": None,
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
    "mode": "propose",
    "service_actor": "svc:rule-hse-notify",
    "access": "user",
    "owner": ACTOR,
    "enabled": False,
}


def test_a_rule_starts_disabled_and_every_revision_replaces_the_row(db: DbTarget) -> None:
    rule = new_ulid()
    append(db, rule, s.RULE_STREAM_TYPE, 0, s.RULE_CREATED, {"rule_id": rule, **RULE})
    found = row(db, "cur_rule", "rule_id", rule)
    assert bool(found["enabled"]) is False and found["mode"] == "propose"
    append(db, rule, s.RULE_STREAM_TYPE, 1, s.RULE_ENABLED, {"rule_id": rule})
    assert bool(row(db, "cur_rule", "rule_id", rule)["enabled"]) is True
    append(
        db,
        rule,
        s.RULE_STREAM_TYPE,
        2,
        s.RULE_REVISED,
        {
            "rule_id": rule,
            "version": 2,
            "rule": {**RULE, "mode": "act", "enabled": True},
            "reason": "ready",
        },
    )
    found = row(db, "cur_rule", "rule_id", rule)
    assert (found["version"], found["mode"], found["stream_version"]) == (2, "act", 3)
    append(
        db,
        rule,
        s.RULE_STREAM_TYPE,
        3,
        s.RULE_BLOCKED,
        {
            "rule_id": rule,
            "rule_version": 2,
            "trigger_event_id": new_ulid(),
            "trigger_seq": 5,
            "depth": 3,
            "outcome": "depth_limit",
            "problems": [],
        },
    )
    found = row(db, "cur_rule", "rule_id", rule)
    assert found["version"] == 2 and found["stream_version"] == 4


ENDPOINT: dict[str, Any] = {
    "app": "acme-nde",
    "name": "results",
    "version": 1,
    "auth": "hmac_sha256",
    "mapping": '{"command": "PostToFeed", "args": {"body": "x"}}',
    "mapping_language": "jsonata-restricted@1",
    "external_schema": None,
    "allowed_commands": ["PostToFeed"],
    "service_actor": "svc:inbound-acme-nde-results",
    "access": "user",
    "max_body_bytes": 262144,
    "rate_per_minute": 60,
    "dry_run": True,
    "enabled": False,
    "owner": ACTOR,
}


def test_an_endpoint_keeps_every_version_it_had(db: DbTarget) -> None:
    endpoint, secret = new_ulid(), new_ulid()
    append(
        db,
        endpoint,
        s.ENDPOINT_STREAM_TYPE,
        0,
        s.ENDPOINT_CREATED,
        {"endpoint_id": endpoint, **ENDPOINT, "secret_id": secret},
    )
    found = row(db, "cur_inbound_endpoint", "endpoint_id", endpoint)
    assert found["current_secret_id"] == secret and bool(found["dry_run"]) is True
    revised = {
        **ENDPOINT,
        "version": 2,
        "mapping": '{"command": "PostToFeed", "args": {"body": "y"}}',
        "dry_run": False,
    }
    append(
        db,
        endpoint,
        s.ENDPOINT_STREAM_TYPE,
        1,
        s.ENDPOINT_REVISED,
        {"endpoint_id": endpoint, "version": 2, "endpoint": revised, "reason": "go live"},
    )
    versions = {
        r["version"]: load_json(r["definition_json"])
        for r in rows(db, "cur_inbound_endpoint_version")
    }
    assert set(versions) == {1, 2}
    assert versions[1]["mapping"].endswith('"x"}}') and versions[1]["dry_run"] is True
    assert versions[2]["mapping"].endswith('"y"}}') and versions[2]["dry_run"] is False
    assert "secret_id" not in versions[1] and "current_secret_id" not in versions[1]
    new_secret = new_ulid()
    append(
        db,
        endpoint,
        s.ENDPOINT_STREAM_TYPE,
        2,
        s.ENDPOINT_SECRET_ROTATED,
        {"endpoint_id": endpoint, "secret_id": new_secret},
    )
    append(db, endpoint, s.ENDPOINT_STREAM_TYPE, 3, s.ENDPOINT_ENABLED, {"endpoint_id": endpoint})
    found = row(db, "cur_inbound_endpoint", "endpoint_id", endpoint)
    assert found["current_secret_id"] == new_secret and bool(found["enabled"]) is True
    assert found["version"] == 2


def test_an_enricher_is_registered_and_revised(db: DbTarget) -> None:
    enricher = new_ulid()
    base = {
        "name": "doc_classifier",
        "version": 1,
        "code_version": "1.0.0",
        "model_ref": None,
        "when": {"event_types": ["File.Processed"]},
        "properties": [{"name": "doc_type", "kind": "string", "policy": "propose"}],
        "service_actor": "svc:enricher-doc-classifier",
        "access": "user",
        "owner": ACTOR,
        "enabled": False,
    }
    append(
        db,
        enricher,
        s.ENRICHER_STREAM_TYPE,
        0,
        s.ENRICHER_REGISTERED,
        {"enricher_id": enricher, **base},
    )
    append(db, enricher, s.ENRICHER_STREAM_TYPE, 1, s.ENRICHER_ENABLED, {"enricher_id": enricher})
    found = row(db, "cur_enricher", "enricher_id", enricher)
    assert bool(found["enabled"]) is True and found["model_ref"] is None
    append(
        db,
        enricher,
        s.ENRICHER_STREAM_TYPE,
        2,
        s.ENRICHER_REVISED,
        {
            "enricher_id": enricher,
            "version": 2,
            "reason": "policy",
            "enricher": {**base, "version": 2, "code_version": "1.1.0"},
        },
    )
    found = row(db, "cur_enricher", "enricher_id", enricher)
    assert (found["version"], found["code_version"]) == (2, "1.1.0")


def test_a_proposed_value_is_accepted_or_rejected(db: DbTarget) -> None:
    target = {"id": new_ulid(), "key": "ISD-001", "record_type": "documents.Document", "version": 4}
    kept, dropped = new_ulid(), new_ulid()
    for value_id, version in ((kept, "ISO"), (dropped, "PID")):
        append(
            db,
            value_id,
            s.ENRICHMENT_STREAM_TYPE,
            0,
            s.ENRICHMENT_PROPOSED,
            {
                "value_id": value_id,
                "target": target,
                "property_path": "enrich.doc_classifier.doc_type",
                "value": version,
                "enricher": "doc_classifier",
                "enricher_version": "1.0.0",
                "confidence": 0.9,
                "inputs": [{"record": target, "file_sha256": "0" * 64}],
                "model_ref": None,
                "produced_at": "2026-10-17T00:00:00.000000Z",
                "acceptance_state": "proposed",
            },
        )
    append(
        db,
        kept,
        s.ENRICHMENT_STREAM_TYPE,
        1,
        s.ENRICHMENT_ACCEPTED,
        {"value_id": kept, "by": "user:mlee", "automatic": False},
    )
    append(
        db,
        dropped,
        s.ENRICHMENT_STREAM_TYPE,
        1,
        s.ENRICHMENT_REJECTED,
        {"value_id": dropped, "by": "user:mlee", "reason": "wrong"},
    )
    first = row(db, "cur_enrichment_value", "value_id", kept)
    second = row(db, "cur_enrichment_value", "value_id", dropped)
    assert (first["acceptance_state"], first["decided_by"]) == ("accepted", "user:mlee")
    assert (second["acceptance_state"], second["reason"]) == ("rejected", "wrong")
    assert load_json(first["value_json"]) == "ISO"
    assert load_json(first["target_json"])["key"] == "ISD-001"


def test_an_automatic_acceptance_is_told_apart(db: DbTarget) -> None:
    target = {"id": new_ulid(), "key": "ISD-002", "record_type": "documents.Document", "version": 1}
    value = new_ulid()
    append(
        db,
        value,
        s.ENRICHMENT_STREAM_TYPE,
        0,
        s.ENRICHMENT_PROPOSED,
        {
            "value_id": value,
            "target": target,
            "property_path": "enrich.e.p",
            "value": ["a"],
            "enricher": "e",
            "enricher_version": "1",
            "confidence": 0.99,
            "inputs": [{"record": target}],
            "produced_at": "t",
            "acceptance_state": "proposed",
        },
    )
    append(
        db,
        value,
        s.ENRICHMENT_STREAM_TYPE,
        1,
        s.ENRICHMENT_ACCEPTED,
        {"value_id": value, "by": "svc:enricher-e", "automatic": True},
    )
    assert row(db, "cur_enrichment_value", "value_id", value)["acceptance_state"] == "auto_accepted"


def test_the_layer_event_sets_are_disjoint_and_complete() -> None:
    parts = [
        s.APP_EVENT_TYPES,
        s.ACTION_DEFINITION_EVENT_TYPES,
        s.ACTION_INVOCATION_EVENT_TYPES,
        s.RULE_EVENT_TYPES,
        s.ENDPOINT_EVENT_TYPES,
        s.DELIVERY_EVENT_TYPES,
        s.ENRICHER_EVENT_TYPES,
        s.ENRICHMENT_EVENT_TYPES,
    ]
    assert sum(len(p) for p in parts) == len(s.INTEGRATION_EVENT_TYPES) == 33
    assert s.INTEGRATION_WEBHOOK_EVENT_TYPES <= s.INTEGRATION_EVENT_TYPES
    assert s.INTEGRATION_INTERNAL_EVENT_TYPES.isdisjoint(s.INTEGRATION_WEBHOOK_EVENT_TYPES)
