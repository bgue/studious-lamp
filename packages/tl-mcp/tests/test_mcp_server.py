"""The MCP server skeleton: tool surface, identity, authorisation hook and error mapping."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp_harness import ACTOR, McpHarness
from tl_api.auth import Forbidden
from tl_mcp.context import McpContext
from tl_mcp.errors import guarded, resource_name
from tl_mcp.main import main, parse_args
from tl_mcp.server import build_server

TOOLS = {"search_records", "get_record", "get_links", "trace"}


def test_the_phase_0_surface_is_four_read_tools_and_no_write_tool(env: McpHarness) -> None:
    tools = asyncio.run(env.server.list_tools())
    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert tool.annotations is not None
        assert (
            tool.annotations.read_only_hint is True and tool.annotations.destructive_hint is False
        )
        assert tool.description
    by_name = {t.name: t for t in tools}
    search = by_name["search_records"].input_schema
    assert search["required"] == ["scope"]
    assert set(search["properties"]) == {"scope", "q", "limit", "offset", "order_by"}
    assert search["properties"]["limit"]["maximum"] == 500
    assert "linked:NCR" in (by_name["search_records"].description or "")
    assert by_name["trace"].input_schema["properties"]["direction"]["enum"] == ["out", "in", "both"]


def test_the_resources_are_registered(env: McpHarness) -> None:
    templates = {t.uri_template for t in asyncio.run(env.server.list_resource_templates())}
    assert templates == {"tl://record/{scope}/{key}", "tl://schema/{scope}/{record_type}"}
    assert {str(r.uri) for r in asyncio.run(env.server.list_resources())} == {"tl://relations"}


def test_the_actor_must_be_a_user_or_an_agent(env: McpHarness) -> None:
    for bad in ("triage", "svc:scanner", "agent:", "admin:root"):
        with pytest.raises(ValueError):
            build_server(env.factory, actor=bad)


def test_every_tool_and_resource_calls_the_hook_before_doing_anything(tmp_path: Path) -> None:
    seen: list[tuple[str, str, str]] = []

    def deny(actor: str, action: str, resource: str) -> None:
        seen.append((actor, action, resource))
        raise Forbidden("nobody may")

    env = McpHarness.build(tmp_path, authorize_hook=deny)
    try:
        calls = {
            "search_records": {"scope": "project:P123"},
            "get_record": {"record": "K-1", "scope": "project:P123"},
            "get_links": {"record": "K-1", "scope": "project:P123"},
            "trace": {"record": "K-1", "scope": "project:P123"},
        }
        for tool, args in calls.items():
            with pytest.raises(ToolError, match="not allowed: nobody may"):
                env.call(tool, **args)
        for uri in (
            "tl://record/project:P123/K-1",
            "tl://schema/project:P123/core.Record",
            "tl://relations",
        ):
            with pytest.raises(ResourceError, match="not allowed"):
                env.read(uri)
    finally:
        env.close()
    assert {action for _, action, _ in seen} == {
        "mcp.search_records",
        "mcp.get_record",
        "mcp.get_links",
        "mcp.trace",
        "mcp.resource.record",
        "mcp.resource.schema",
        "mcp.resource.relations",
    }
    assert {actor for actor, _, _ in seen} == {ACTOR}


def test_argument_validation_comes_from_the_schema(env: McpHarness) -> None:
    for args in ({"scope": "project:P123", "limit": 0}, {"scope": "project:P123", "limit": 501}):
        with pytest.raises(ToolError):
            env.call("search_records", **args)
    with pytest.raises(ToolError):
        env.call("trace", record="x", direction="sideways")


def test_the_entry_point_checks_its_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert parse_args(["--actor", "agent:a", "--db", "/x/y.db"]).db == Path("/x/y.db")
    assert main(["--actor", "nobody", "--db", str(tmp_path / "x.db")]) == 2
    assert "agent:<id>" in capsys.readouterr().err
    assert main(["--actor", "agent:a", "--db", str(tmp_path / "missing.db")]) == 2
    assert "tl init" in capsys.readouterr().err


def recording_env(tmp_path: Path) -> tuple[McpHarness, list[tuple[str, str, str]]]:
    """A server whose hook records each call and then refuses, so nothing after it ever runs."""
    seen: list[tuple[str, str, str]] = []

    def record_and_deny(actor: str, action: str, resource: str) -> None:
        seen.append((actor, action, resource))
        raise Forbidden("stop here")

    return McpHarness.build(tmp_path, authorize_hook=record_and_deny), seen


def test_oversized_input_is_rejected_before_the_hook_runs(tmp_path: Path) -> None:
    env, seen = recording_env(tmp_path)
    try:
        too_big = {
            "search_records": [
                {"scope": "project:P123", "q": "x" * 2001},
                {"scope": "s" * 129},
                {"scope": "project:P123", "order_by": "o" * 257},
                {"scope": ""},
            ],
            "get_record": [
                {"record": "r" * 129},
                {"record": ""},
                {"record": "K", "scope": "s" * 129},
            ],
            "get_links": [{"record": "r" * 129}],
            "trace": [{"record": "r" * 129}],
        }
        for tool, variants in too_big.items():
            for args in variants:
                with pytest.raises(ToolError):
                    env.call(tool, **args)
        assert seen == []  # the schema stopped every one of them first
        # the same arguments at the limit get as far as the hook (which then refuses)
        for tool, args in {
            "search_records": {"scope": "s" * 128, "q": "x" * 2000, "order_by": "o" * 256},
            "get_record": {"record": "r" * 128, "scope": "s" * 128},
        }.items():
            with pytest.raises(ToolError, match="not allowed"):
                env.call(tool, **args)
        assert len(seen) == 2
    finally:
        env.close()


def test_resource_parts_are_checked_before_the_hook_and_quoted_for_it(tmp_path: Path) -> None:
    env, seen = recording_env(tmp_path)
    try:
        ctx = McpContext(env.factory, ACTOR, lambda *a: seen.append(a))
        for parts in (
            [("scope", ""), ("key", "K")],
            [("scope", "s"), ("key", " ")],
            [("key", "k" * 129)],
        ):
            with (
                pytest.raises(ResourceError),
                guarded(ctx, "t", "r", error=ResourceError, parts=parts),
            ):
                pytest.fail("the body must not run")
        assert seen == []
        with guarded(ctx, "t", "r", parts=[("scope", "project:P1"), ("key", "K-1")]):
            pass
        assert seen == [(ACTOR, "mcp.t", "r")]
    finally:
        env.close()
    assert resource_name("record", "project:P1", "K-1") == "record:project%3AP1/K-1"
    assert resource_name("record", "project:P1", "a/b") == "record:project%3AP1/a%2Fb"
    assert resource_name("schema", "company", "core.Record") == "schema:company/core.Record"
    # a key that contains the separator cannot be confused with a different scope and key
    assert resource_name("record", "a", "b/c") != resource_name("record", "a/b", "c")
