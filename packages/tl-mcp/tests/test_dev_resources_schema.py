"""The dev resources: the event catalog (page, index, samples) and the core schema graph."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ResourceError
from tl_mcp.dev.guard import find_repo_root
from tl_schema import catalog

REPO = find_repo_root()
CATALOG_PAGE = REPO / "packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md"
PAGE_URI = "tl://dev/event-catalog"
INDEX_URI = "tl://dev/event-catalog/index"
GRAPH_URI = "tl://dev/schema-graph"


def sample_uri(event_type: str) -> str:
    return f"tl://dev/event-sample/{event_type}"


def graph(env: DevHarness) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(env.read(GRAPH_URI))
    return parsed


def test_the_four_resources_are_listed(dev_env: DevHarness) -> None:
    uris = dev_env.resource_uris()
    for uri in (PAGE_URI, INDEX_URI, GRAPH_URI, "tl://dev/event-sample/{event_type}"):
        assert uri in uris


def test_the_catalog_page_is_the_committed_file(dev_env: DevHarness) -> None:
    assert dev_env.read(PAGE_URI) == CATALOG_PAGE.read_text(encoding="utf-8")


def test_the_index_lists_the_catalog_event_types_in_order(dev_env: DevHarness) -> None:
    index = json.loads(dev_env.read(INDEX_URI))
    assert [entry["event_type"] for entry in index] == catalog.event_types()
    assert index == catalog.index()


def test_a_sample_has_payload_and_envelope(dev_env: DevHarness) -> None:
    sample = json.loads(dev_env.read(sample_uri("Record.Created")))
    assert set(sample) == {"payload", "envelope"}
    assert sample == catalog.sample("Record.Created")


@pytest.mark.parametrize("event_type", ["Nope.Created", "", "x" * 200])
def test_an_unknown_or_bad_event_type_is_refused(dev_env: DevHarness, event_type: str) -> None:
    with pytest.raises(ResourceError) as refused:
        dev_env.read(sample_uri(event_type))
    message = str(refused.value)
    assert "first valid ones are" in message
    assert catalog.event_types()[0] in message
    assert "x" * 200 not in message


def test_the_graph_has_the_record_class(dev_env: DevHarness) -> None:
    classes = {entry["name"]: entry for entry in graph(dev_env)["classes"]}
    record = classes["Record"]
    assert record["is_a"] == "RecordEnvelope"
    assert record["current_state"] is True
    id_slot = next(slot for slot in record["slots"] if slot["name"] == "id")
    assert id_slot["required"] is True
    assert len(record["description"]) <= 200


def test_the_graph_has_the_enum_with_sorted_values(dev_env: DevHarness) -> None:
    enums = {entry["name"]: entry for entry in graph(dev_env)["enums"]}
    values = enums["ConformanceStatus"]["values"]
    assert values == sorted(values)
    assert values == ["nonconformant", "ok", "waived", "warning"]


def test_the_graph_has_the_is_a_edge(dev_env: DevHarness) -> None:
    edges = graph(dev_env)["edges"]
    assert {"from": "Record", "to": "RecordEnvelope", "kind": "is_a", "slot": None} in edges


def test_the_graph_has_the_range_edge_from_the_declaring_class(dev_env: DevHarness) -> None:
    edges = graph(dev_env)["edges"]
    assert {
        "from": "RecordEnvelope",
        "to": "ConformanceStatus",
        "kind": "range",
        "slot": "conformance",
    } in edges


def test_every_edge_endpoint_is_named_in_the_document(dev_env: DevHarness) -> None:
    document = graph(dev_env)
    names = {entry["name"] for entry in document["classes"]} | {
        entry["name"] for entry in document["enums"]
    }
    for edge in document["edges"]:
        assert edge["from"] in names
        assert edge["to"] in names


def test_two_reads_of_the_graph_are_byte_identical(dev_env: DevHarness) -> None:
    assert dev_env.read(GRAPH_URI) == dev_env.read(GRAPH_URI)


def test_no_resource_text_contains_the_repository_path(dev_env: DevHarness) -> None:
    repo = str(find_repo_root())
    texts = [
        dev_env.read(PAGE_URI),
        dev_env.read(INDEX_URI),
        dev_env.read(GRAPH_URI),
        dev_env.read(sample_uri("Record.Created")),
    ]
    for text in texts:
        assert repo not in text


def test_reading_the_graph_does_not_change_the_working_directory(dev_env: DevHarness) -> None:
    before = os.getcwd()
    dev_env.read(GRAPH_URI)
    assert os.getcwd() == before


def test_the_reads_are_audited(dev_env: DevHarness) -> None:
    dev_env.read(GRAPH_URI)
    dev_env.read(sample_uri("Record.Created"))
    tools = [line["tool"] for line in dev_env.audit_lines()]
    assert "resource.schema_graph" in tools
    assert "resource.event_sample" in tools


def test_the_graph_names_the_core_schema(dev_env: DevHarness) -> None:
    assert graph(dev_env)["schema"] == "tl_core"
