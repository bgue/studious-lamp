"""One sample row of every integration kind, the shape `list_integration` returns (P1-I7).

Provided and final; the tickets do not change it. Each function takes keyword overrides.
"""

from __future__ import annotations

from typing import Any

SCOPE = "project:P123"
WHEN = "2026-10-11T12:15:00.123456Z"


def app(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "app_id": "app-1", "name": "acme-nde", "label": "Acme NDE", "owner": "user:boss",
        "description": "Weld inspection results", "enabled": True, "retired": False,
    }  # fmt: skip
    return row | over


def endpoint(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "endpoint_id": "ep-1", "app": "acme-nde", "name": "results", "version": 2,
        "enabled": True, "retired": False, "dry_run": False, "auth": "hmac",
        "access": "user", "service_actor": "svc:inbound-acme-nde.results", "owner": "user:boss",
        "allowed_commands": ["SetPsetValues", "AddLink"], "max_body_bytes": 65536,
        "rate_per_minute": 60,
    }  # fmt: skip
    return row | over


def rule(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rule_id": "rule-1", "key": "hse-notify", "title": "Notify HSE", "version": 1,
        "enabled": False, "retired": False, "mode": "propose", "access": "user",
        "service_actor": "svc:rule-hse-notify", "owner": "user:boss",
        "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
        "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
        "condition": None,
    }  # fmt: skip
    return row | over


def action(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "action_id": "act-1", "name": "send_to_nde", "label": "Send to NDE", "version": 1,
        "enabled": True, "retired": False, "executor": "webhook", "access": "user",
        "requires_approval": True, "side_effect_class": "external", "owner": "user:boss",
        "parameters": [{"name": "weld"}, {"name": "note"}],
    }  # fmt: skip
    return row | over


def enricher(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "enricher_id": "enr-1", "name": "doc_classifier", "version": 1, "enabled": True,
        "retired": False, "access": "user", "code_version": "1.0.0", "owner": "user:boss",
        "properties": [
            {"name": "doc_type", "kind": "text", "policy": "propose", "threshold": 0.9},
            {"name": "discipline", "kind": "text", "policy": "auto", "threshold": 0.8},
        ],
    }  # fmt: skip
    return row | over


def invocation(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "invocation_id": "01JINVOCATIONAAAAAA1", "action": "send_to_nde", "action_version": 1,
        "status": "completed", "invoked_by": "user:bob", "requested_at": WHEN,
        "finished_at": WHEN, "targets": [{"id": "r1", "record_type": "weld"}],
    }  # fmt: skip
    return row | over


def delivery(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "delivery_id": "01JDELIVERYAAAAAAA1", "endpoint_id": "ep-1", "endpoint_version": 2,
        "state": "failed", "received_at": WHEN, "payload_size": 412, "attempts": 3,
        "error_code": "mapping_failed", "error_message": "no weld in the payload",
    }  # fmt: skip
    return row | over


def enrichment(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "value_id": "01JVALUEAAAAAAAAAA1", "acceptance_state": "proposed",
        "target": {"id": "rec-1", "key": "DOC-0001", "record_type": "document"},
        "target_id": "rec-1", "property_path": "enrich.doc_classifier.doc_type",
        "value": "DRW", "confidence": 0.8, "enricher": "doc_classifier", "enricher_version": 1,
        "produced_at": WHEN, "reason": None, "decided_by": None,
    }  # fmt: skip
    return row | over
