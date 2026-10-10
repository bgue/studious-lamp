"""The `lake_query` tool and the `tl://lake/schema` resource (P0-I7 B; brief 11.3, 28.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_adapters.db import make_engine
from tl_lake import read_snapshot, sync_lake
from tl_lake.config import LakeConfig


def sync(env: McpHarness, lake_dir: Path) -> None:
    engine = make_engine(env.db)
    try:
        with read_snapshot(engine) as conn:
            sync_lake(LakeConfig.at(lake_dir), conn)
    finally:
        engine.dispose()


@pytest.fixture
def synced(env: McpHarness, tmp_path: Path) -> McpHarness:
    a = env.create_record("A-1", "Gate valve").stream_id
    b = env.create_record("B-1", "Data sheet").stream_id
    env.link(a, b)
    sync(env, tmp_path / "lake")
    return env


def audit(tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "lake" / "lake_query.log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_lake_query_returns_rows_and_the_as_of_seq(synced: McpHarness) -> None:
    out = synced.structured("lake_query", sql="SELECT key, title FROM cur_core_record ORDER BY key")
    assert out["columns"] == ["key", "title"]
    assert out["rows"] == [["A-1", "Gate valve"], ["B-1", "Data sheet"]]
    assert (out["row_count"], out["truncated"], out["truncated_by"]) == (2, False, None)
    assert out["limit"] == 100 and out["as_of_seq"] == 3
    assert out["as_of"] == f"as of seq 3 (snapshot {out['snapshot_id']})"


def test_the_row_limit_applies_and_is_reported(synced: McpHarness) -> None:
    out = synced.structured("lake_query", sql="SELECT seq FROM events ORDER BY seq", limit=2)
    assert out["rows"] == [[1], [2]] and out["truncated"] and out["truncated_by"] == "limit"


def test_it_sees_the_state_the_agent_could_also_read_with_the_record_tools(
    synced: McpHarness,
) -> None:
    via_lake = synced.structured("lake_query", sql="SELECT key FROM cur_core_record ORDER BY key")
    via_search = synced.structured("search_records", scope=SCOPE, order_by="key")
    assert [r[0] for r in via_lake["rows"]] == [r["key"] for r in via_search["records"]]


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE events",
        "SELECT 1; SELECT 2",
        "INSERT INTO events SELECT * FROM events",
        "ATTACH ':memory:' AS x",
        "COPY events TO '/tmp/mcp-leak.csv'",
        "PRAGMA database_list",
        "SET enable_external_access = true",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_text('/etc/hostname')",
        "SELECT * FROM '/etc/passwd.csv'",
        "INSTALL httpfs",
        "LOAD httpfs",
    ],
)
def test_a_refused_statement_is_a_tool_error_that_says_refused(
    synced: McpHarness, tmp_path: Path, sql: str
) -> None:
    with pytest.raises(ToolError, match="refused: "):
        synced.call("lake_query", sql=sql)
    assert not Path("/tmp/mcp-leak.csv").exists()
    assert audit(tmp_path)[-1]["outcome"] == "refused"
    out = synced.structured("lake_query", sql="SELECT count(*) FROM events")
    assert out["rows"] == [[3]]  # nothing changed


def test_every_call_is_logged_with_the_acting_agent(synced: McpHarness, tmp_path: Path) -> None:
    synced.structured("lake_query", sql="SELECT 1")
    with pytest.raises(ToolError):
        synced.call("lake_query", sql="DROP TABLE events")
    ok, refused = audit(tmp_path)[-2:]
    assert ok["caller"] == ACTOR and ok["outcome"] == "ok" and ok["rows"] == 1
    assert refused["caller"] == ACTOR and refused["outcome"] == "refused"


def test_a_lake_that_was_never_synced_says_what_to_do(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="tl lake sync"):
        env.call("lake_query", sql="SELECT 1")
    with pytest.raises(ResourceError, match="tl lake sync"):
        env.read("tl://lake/schema")


def test_a_failing_statement_is_a_short_tool_error_without_paths(
    synced: McpHarness, tmp_path: Path
) -> None:
    with pytest.raises(ToolError) as caught:
        synced.call("lake_query", sql="SELECT CAST('x' AS INTEGER)")
    assert "ConversionException" in str(caught.value) and str(tmp_path) not in str(caught.value)


def test_arguments_are_bounded_by_the_schema(synced: McpHarness) -> None:
    for args in (
        {"sql": ""},
        {"sql": "x" * 20_001},
        {"sql": "SELECT 1", "limit": 0},
        {"sql": "SELECT 1", "limit": 1001},
        {"sql": "SELECT 1", "limit": 2.5},
    ):
        with pytest.raises(ToolError):
            synced.call("lake_query", **args)


def test_the_tool_is_annotated_read_only_and_describes_its_limits(env: McpHarness) -> None:
    import asyncio

    [tool] = [t for t in asyncio.run(env.server.list_tools()) if t.name == "lake_query"]
    assert tool.annotations is not None and tool.annotations.read_only_hint is True
    text = tool.description or ""
    for needle in ("cur_core_record", "as_of_seq", "AT (VERSION", "SELECT", "logged"):
        assert needle in text


def test_the_schema_resource_lists_tables_and_columns(synced: McpHarness) -> None:
    tables = json.loads(synced.read("tl://lake/schema"))
    assert {"events", "cur_core_record", "links", "pset_values", "_tl_sync"} <= set(tables)
    assert {"column": "seq", "type": "BIGINT"} in tables["events"]
