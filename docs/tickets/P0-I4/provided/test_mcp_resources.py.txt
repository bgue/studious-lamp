"""MCP resources (P0-I4-T43): a record with its links, a form schema, the relations."""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver.exceptions import ResourceError
from mcp_harness import SCOPE, McpHarness
from tl_core.links.provider import get_vocabulary
from tl_core.services import link_queries, psets, queries


def test_the_record_resource_holds_the_record_and_its_links(env: McpHarness) -> None:
    a = env.create_record("P123-REC-0001", "First").stream_id
    b = env.create_record("P123-REC-0002", "Second").stream_id
    env.link(a, b)
    body = json.loads(env.read(f"tl://record/{SCOPE}/P123-REC-0001"))
    with env.factory(True) as uow:
        assert body["record"] == queries.get_record(uow, SCOPE, "P123-REC-0001")
        expected = [r.model_dump(mode="json") for r in link_queries.links_of(uow, a)]
    assert body["links"] == expected and body["links"][0]["other_key"] == "P123-REC-0002"
    assert set(body) == {"record", "links"}


def test_an_unknown_record_is_a_resource_error(env: McpHarness) -> None:
    with pytest.raises(ResourceError, match="no record with key 'NOPE'"):
        env.read(f"tl://record/{SCOPE}/NOPE")
    env.create_record("K-1")
    with pytest.raises(ResourceError, match="no record"):
        env.read("tl://record/project:P999/K-1")


def test_the_schema_resource_is_the_form_metadata(env: McpHarness) -> None:
    body = json.loads(env.read(f"tl://schema/{SCOPE}/core.Record"))
    with env.factory(True) as uow:
        expected = psets.form_metadata(uow, SCOPE, "core.Record").model_dump(mode="json")
    assert body == expected
    assert body["record_type"] == "core.Record" and body["effective_schema_hash"]


def test_the_relations_resource_lists_the_vocabulary_in_order(env: McpHarness) -> None:
    rows = json.loads(env.read("tl://relations"))
    vocabulary = get_vocabulary()
    assert [r["code"] for r in rows] == list(vocabulary.codes())
    assert all(set(r) == {"code", "label", "inverse_code", "inverse_label"} for r in rows)
    requires = next(r for r in rows if r["code"] == "requires")
    assert requires["label"] and requires["inverse_label"] != requires["label"]
