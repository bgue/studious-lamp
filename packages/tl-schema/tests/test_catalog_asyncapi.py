"""The AsyncAPI 3 document of the event catalog (P0-I5-T20)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from tl_schema.catalog_asyncapi import asyncapi_document
from tl_schema.catalog_types import EventTypeInfo


def make(event_type: str, title: str = "Something happened.") -> EventTypeInfo:
    ce_type = f"tl.core.{event_type}.v1"
    return EventTypeInfo(
        event_type=event_type,
        version=1,
        ce_type=ce_type,
        title=title,
        description=f"{title} More detail follows.",
        payload_class=event_type.replace(".", "") + "Payload",
        payload_schema={"type": "object", "properties": {"reason": {"type": "string"}}},
        envelope_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.org/catalog/{event_type}.json",
            "type": "object",
            "required": ["type"],
            "properties": {"type": {"const": ce_type}},
        },
        sample_payload={"reason": "because"},
        sample_envelope={"specversion": "1.0", "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", "type": ce_type},
    )


EVENTS = [
    make("Workflow.Transitioned", "A record moved to another state."),
    make("Record.Created", "A record was created."),
]


def resolve(document: dict[str, Any], ref: str) -> Any:
    assert ref.startswith("#/"), ref
    node: Any = document
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def walk_refs(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(walk_refs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_refs(item))
    return found


def test_the_document_declares_asyncapi_3_with_info_and_default_content_type() -> None:
    doc = asyncapi_document(EVENTS)
    assert doc["asyncapi"] == "3.0.0"
    assert doc["info"]["title"] == "Throughline events"
    assert doc["info"]["version"] == "1.0.0"
    assert "CloudEvents" in doc["info"]["description"]
    assert doc["defaultContentType"] == "application/json"
    assert set(doc) == {
        "asyncapi",
        "info",
        "defaultContentType",
        "channels",
        "operations",
        "components",
    }


def test_title_and_version_are_parameters() -> None:
    doc = asyncapi_document(EVENTS, title="My events", version="2.3.4")
    assert (doc["info"]["title"], doc["info"]["version"]) == ("My events", "2.3.4")


def test_one_channel_one_operation_one_message_per_event_type_sorted_by_name() -> None:
    doc = asyncapi_document(EVENTS)
    assert list(doc["channels"]) == ["Record.Created", "Workflow.Transitioned"]
    assert list(doc["operations"]) == ["receiveRecordCreated", "receiveWorkflowTransitioned"]
    assert list(doc["components"]["messages"]) == ["Record.Created", "Workflow.Transitioned"]
    channel = doc["channels"]["Record.Created"]
    assert channel["address"] == "Record.Created"
    assert channel["title"] == "A record was created."
    assert channel["messages"] == {
        "Record.Created": {"$ref": "#/components/messages/Record.Created"}
    }
    operation = doc["operations"]["receiveRecordCreated"]
    assert operation["action"] == "receive"
    assert operation["channel"] == {"$ref": "#/channels/Record.Created"}
    assert operation["summary"] == "A record was created."
    assert operation["messages"] == [{"$ref": "#/channels/Record.Created/messages/Record.Created"}]


def test_a_message_carries_the_cloudevents_type_schema_and_an_example() -> None:
    doc = asyncapi_document(EVENTS)
    message = doc["components"]["messages"]["Workflow.Transitioned"]
    assert message["name"] == "tl.core.Workflow.Transitioned.v1"
    assert message["title"] == "A record moved to another state."
    assert message["summary"] == "A record moved to another state."
    assert message["description"] == "A record moved to another state. More detail follows."
    assert message["contentType"] == "application/json"
    assert message["headers"] == {"$ref": "#/components/schemas/WebhookHeaders"}
    assert message["payload"]["properties"]["type"] == {"const": "tl.core.Workflow.Transitioned.v1"}
    assert message["payload"]["required"] == ["type"]
    (example,) = message["examples"]
    assert example["name"] == "sample"
    assert example["payload"] == EVENTS[0].sample_envelope
    assert example["headers"]["webhook-id"] == "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9"
    assert set(example["headers"]) == {"webhook-id", "webhook-timestamp", "webhook-signature"}
    assert example["headers"]["webhook-signature"].startswith("v1,")


def test_schema_and_id_are_removed_from_the_message_payload_only_at_the_top_level() -> None:
    nested = make("Record.Created")
    nested.envelope_schema["properties"]["data"] = {"$id": "keep-me", "type": "object"}
    doc = asyncapi_document([nested])
    payload = doc["components"]["messages"]["Record.Created"]["payload"]
    assert "$schema" not in payload and "$id" not in payload
    assert payload["properties"]["data"]["$id"] == "keep-me"


def test_the_headers_schema_describes_the_three_standard_webhooks_headers() -> None:
    doc = asyncapi_document(EVENTS)
    schema = doc["components"]["schemas"]["WebhookHeaders"]
    assert schema["type"] == "object"
    assert schema["required"] == ["webhook-id", "webhook-timestamp", "webhook-signature"]
    assert set(schema["properties"]) == {"webhook-id", "webhook-timestamp", "webhook-signature"}
    assert all(p["type"] == "string" and p["description"] for p in schema["properties"].values())


def test_every_ref_resolves_inside_the_document() -> None:
    doc = asyncapi_document(EVENTS)
    refs = walk_refs(doc)
    assert len(refs) >= 3 * len(EVENTS)
    for ref in refs:
        resolve(doc, ref)


def test_the_result_is_deterministic_json_and_independent_of_input_order() -> None:
    first = asyncapi_document(EVENTS)
    second = asyncapi_document(list(reversed(EVENTS)))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.dumps(first) == json.dumps(second)  # key order too, not only content
    json.dumps(first)


def test_the_inputs_are_not_modified_and_the_output_does_not_alias_them() -> None:
    events = [make("Record.Created")]
    before = copy.deepcopy(events[0])
    doc = asyncapi_document(events)
    assert events[0] == before
    doc["components"]["messages"]["Record.Created"]["payload"]["properties"]["type"]["const"] = "x"
    doc["components"]["messages"]["Record.Created"]["examples"][0]["payload"]["id"] = "x"
    assert events[0] == before


def test_an_empty_catalog_is_a_valid_empty_document() -> None:
    doc = asyncapi_document([])
    assert doc["channels"] == {} and doc["operations"] == {}
    assert doc["components"]["messages"] == {}
    assert "WebhookHeaders" in doc["components"]["schemas"]


def test_a_duplicate_event_type_is_refused() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        asyncapi_document([make("Record.Created"), make("Record.Created")])
