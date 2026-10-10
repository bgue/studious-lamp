"""AsyncAPI 3.0 document of the event catalog (brief 18.3).

``asyncapi_document`` turns the event-type descriptions the catalog generator produces into one
AsyncAPI 3.0 document: a channel, an operation and a message per event type, a shared
``WebhookHeaders`` schema (Standard Webhooks headers, brief 18.4) and a sample per message. It is a
pure function of its inputs.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from tl_schema.catalog_types import EventTypeInfo

ASYNCAPI_VERSION = "3.0.0"

_CONTENT_TYPE = "application/json"
_INFO_DESCRIPTION = (
    "Events delivered by Throughline webhooks as CloudEvents 1.0 JSON, signed with Standard "
    "Webhooks headers. Generated from the LinkML event classes."
)
_HEADERS_SCHEMA = "WebhookHeaders"
_HEADERS_DESCRIPTION = "Standard Webhooks headers that accompany every delivered event."
_SAMPLE_TIMESTAMP = "1760000047"
_SAMPLE_SIGNATURE = "v1,ZXhhbXBsZS1zaWduYXR1cmU="


def asyncapi_document(
    events: Sequence[EventTypeInfo],
    *,
    title: str = "Throughline events",
    version: str = "1.0.0",
) -> dict[str, Any]:
    """The AsyncAPI 3.0 document for ``events``. Pure and deterministic. See the ticket."""
    ordered = sorted(events, key=lambda e: e.event_type)
    if len({event.event_type for event in ordered}) != len(ordered):
        raise ValueError("duplicate event type in the catalog")

    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    messages: dict[str, Any] = {}
    for event in ordered:
        name = event.event_type
        channels[name] = {
            "address": name,
            "title": event.title,
            "messages": {name: {"$ref": f"#/components/messages/{name}"}},
        }
        operation = "receive" + name.replace(".", "")
        if operation in operations:
            raise ValueError(f"event types collide on the operation key {operation!r}")
        operations[operation] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/{name}"},
            "summary": event.title,
            "messages": [{"$ref": f"#/channels/{name}/messages/{name}"}],
        }
        messages[name] = _message(event)

    return {
        "asyncapi": ASYNCAPI_VERSION,
        "info": {"title": title, "version": version, "description": _INFO_DESCRIPTION},
        "defaultContentType": _CONTENT_TYPE,
        "channels": channels,
        "operations": operations,
        "components": {
            "messages": messages,
            "schemas": {_HEADERS_SCHEMA: _headers_schema()},
        },
    }


def _message(event: EventTypeInfo) -> dict[str, Any]:
    """One AsyncAPI message: the CloudEvent envelope schema and one sample delivery."""
    payload_schema = copy.deepcopy(event.envelope_schema)
    payload_schema.pop("$schema", None)
    payload_schema.pop("$id", None)
    webhook_id: str = event.sample_envelope.get("id", "")
    return {
        "name": event.ce_type,
        "title": event.title,
        "summary": event.title,
        "description": event.description,
        "contentType": _CONTENT_TYPE,
        "headers": {"$ref": f"#/components/schemas/{_HEADERS_SCHEMA}"},
        "payload": payload_schema,
        "examples": [
            {
                "name": "sample",
                "headers": {
                    "webhook-id": webhook_id,
                    "webhook-timestamp": _SAMPLE_TIMESTAMP,
                    "webhook-signature": _SAMPLE_SIGNATURE,
                },
                "payload": copy.deepcopy(event.sample_envelope),
            }
        ],
    }


def _headers_schema() -> dict[str, Any]:
    """The object schema of the three Standard Webhooks headers."""
    return {
        "type": "object",
        "description": _HEADERS_DESCRIPTION,
        "required": ["webhook-id", "webhook-timestamp", "webhook-signature"],
        "properties": {
            "webhook-id": {
                "type": "string",
                "description": "Unique identifier of the delivery, the same across retries.",
            },
            "webhook-timestamp": {
                "type": "string",
                "description": "Unix time in seconds at which the delivery was signed.",
            },
            "webhook-signature": {
                "type": "string",
                "description": (
                    "HMAC-SHA256 signature of the id, timestamp and payload, as 'v1,<base64>'."
                ),
            },
        },
    }
