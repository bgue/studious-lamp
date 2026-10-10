"""MCP read tools (P0-I4-T43): search_records, get_record, get_links, trace."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_core.query import QuerySpec, parse, run_query
from tl_core.services import link_queries, link_trace, queries


def seed(env: McpHarness) -> dict[str, str]:
    """A requires B requires C in P123, a lone D, and X in another project."""
    ids = {k: env.create_record(k, f"Record {k}").stream_id for k in "ABCD"}
    env.link(ids["A"], ids["B"])
    env.link(ids["B"], ids["C"])
    ids["X"] = env.create_record("X", "Other project", scope="project:P999").stream_id
    return ids


def test_search_records_returns_a_page_and_the_total(env: McpHarness) -> None:
    seed(env)
    found = env.structured("search_records", scope=SCOPE)
    assert [r["key"] for r in found["records"]] == ["A", "B", "C", "D"]
    assert (found["total"], found["limit"], found["offset"]) == (4, 50, 0)
    page = env.structured("search_records", scope=SCOPE, limit=2, offset=1, order_by="key:desc")
    assert [r["key"] for r in page["records"]] == ["C", "B"] and page["total"] == 4
    assert env.structured("search_records", scope="project:P999")["total"] == 1


def test_search_records_takes_the_same_query_text_as_the_api(env: McpHarness) -> None:
    seed(env)
    for text in ("record b", "title~record -key=A", "key=A or key=D", "linked:core.Record"):
        with env.factory(True) as uow:
            expected = run_query(uow, QuerySpec(scope=SCOPE, where=parse(text)))
        found = env.structured("search_records", scope=SCOPE, q=text)
        assert found["records"] == expected, text
        assert found["total"] == len(expected), text


def test_a_syntax_error_is_a_tool_error_with_its_position(env: McpHarness) -> None:
    with pytest.raises(ToolError, match=r"query syntax error at position \d+"):
        env.call("search_records", scope=SCOPE, q="title~gate (")
    with pytest.raises(ToolError, match="query syntax error"):
        env.call("search_records", scope=SCOPE, q="nonesuch:1")
    with pytest.raises(ToolError, match="order_by"):
        env.call("search_records", scope=SCOPE, order_by="title:sideways")
    with pytest.raises(ToolError, match="order"):
        env.call("search_records", scope=SCOPE, order_by="nonesuch")


def test_get_record_by_id_or_by_key_and_scope(env: McpHarness) -> None:
    ids = seed(env)
    with env.factory(True) as uow:
        expected = queries.get_record_by_id(uow, ids["B"])
    assert env.structured("get_record", record=ids["B"]) == expected
    assert env.structured("get_record", record="B", scope=SCOPE) == expected
    assert env.structured("get_record", record=ids["B"], scope="project:P999") == expected


def test_get_record_refuses_what_it_cannot_find(env: McpHarness) -> None:
    seed(env)
    with pytest.raises(ToolError, match="no record 'NOPE'"):
        env.call("get_record", record="NOPE", scope=SCOPE)
    with pytest.raises(ToolError, match="give `scope`"):
        env.call("get_record", record="B")
    with pytest.raises(ToolError, match="no record"):
        env.call("get_record", record="B", scope="project:P999")


def test_get_links_lists_both_directions_like_the_service(env: McpHarness) -> None:
    ids = seed(env)
    with env.factory(True) as uow:
        expected = [row.model_dump(mode="json") for row in link_queries.links_of(uow, ids["B"])]
    got = env.structured("get_links", record="B", scope=SCOPE)["result"]
    assert got == expected and [r["direction"] for r in got] == ["out", "in"]
    assert got[0]["other_key"] == "C" and got[1]["other_key"] == "A"
    assert env.structured("get_links", record=ids["D"])["result"] == []
    with pytest.raises(ToolError, match="no record"):
        env.call("get_links", record="NOPE", scope=SCOPE)


def test_get_links_can_include_retracted_links(env: McpHarness) -> None:
    ids = seed(env)
    link_id = env.structured("get_links", record=ids["A"])["result"][0]["link_id"]
    from tl_core.services.links import RetractLink, handle_retract_link

    with env.factory(False) as uow:
        handle_retract_link(
            uow,
            RetractLink(actor="user:seed", source="test", scope=SCOPE, link_id=link_id, reason="x"),
        )
    assert env.structured("get_links", record=ids["A"])["result"] == []
    shown = env.structured("get_links", record=ids["A"], include_retracted=True)["result"]
    assert [r["status"] for r in shown] == ["retracted"]


def test_trace_is_the_link_tree(env: McpHarness) -> None:
    ids = seed(env)
    with env.factory(True) as uow:
        expected = link_trace.trace(uow, ids["A"]).model_dump(mode="json")
        shallow = link_trace.trace(uow, ids["C"], depth=1, direction="in").model_dump(mode="json")
    assert env.structured("trace", record=ids["A"]) == expected
    assert env.structured("trace", record="A", scope=SCOPE) == expected
    assert env.structured("trace", record="C", scope=SCOPE, depth=1, direction="in") == shallow
    assert expected["key"] == "A" and expected["children"][0]["key"] == "B"
    with pytest.raises(ToolError, match="no record"):
        env.call("trace", record="NOPE", scope=SCOPE)


def test_the_same_calls_work_through_a_client(env: McpHarness) -> None:
    ids = seed(env)
    result = env.wire_call("get_record", record=ids["A"])
    assert result.is_error is False and result.structured_content is not None
    assert result.structured_content["key"] == "A"
    missing = env.wire_call("get_record", record="NOPE", scope=SCOPE)
    assert missing.is_error is True
    assert "no record 'NOPE'" in missing.content[0].text  # type: ignore[union-attr]


def test_a_tool_error_reaches_a_client_as_an_error_result(env: McpHarness) -> None:
    result = env.wire_call("search_records", scope="project:P123", q="title~gate (")
    assert result.is_error is True
    assert "query syntax error at position" in result.content[0].text  # type: ignore[union-attr]
