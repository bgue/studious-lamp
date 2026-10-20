"""The read tool get_settings (P0-I8-T04). Provided; do not edit."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from tl_core import settings

KEY = "feed.reactions.enabled"


def listed(env: McpHarness, **kw: Any) -> list[dict[str, Any]]:
    rows = env.structured("get_settings", **kw)["result"]  # a list result sits under `result`
    assert isinstance(rows, list)
    return rows


def put(env: McpHarness, key: str, layer: str, value: Any, **kw: Any) -> None:
    with env.factory(False) as uow:
        settings.set_setting(
            uow, key=key, layer=layer, value=value, actor="user:alice", source="test", **kw
        )


def test_the_tool_is_a_read_only_tool(env: McpHarness) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    assert tools["get_settings"].annotations is not None
    assert tools["get_settings"].annotations.read_only_hint is True


def test_without_arguments_every_setting_is_listed_with_its_definition(env: McpHarness) -> None:
    rows = listed(env)
    keys = [r["effective"]["key"] for r in rows]
    assert keys == sorted(keys) and len(keys) == 17
    first = next(r for r in rows if r["effective"]["key"] == KEY)
    assert first["definition"]["type"] == "bool" and first["definition"]["risk"] == "normal"
    assert first["effective"]["value"] is True and first["effective"]["origin"] == "default"
    egress = next(r for r in rows if r["effective"]["key"] == "webhooks.egress.allowlist")
    assert egress["definition"]["risk"] == "dangerous"


def test_a_key_gives_one_setting_as_a_project_sees_it(env: McpHarness) -> None:
    put(env, KEY, "project:P123", False)
    (row,) = listed(env, key=KEY, project="P123")
    assert row["effective"]["value"] is False
    assert row["effective"]["origin"] == "project" and row["effective"]["modified_here"] is True
    (other,) = listed(env, key=KEY, project="P999")
    assert other["effective"]["value"] is True and other["effective"]["modified_here"] is False


def test_prefix_and_modified_only_narrow_the_list(env: McpHarness) -> None:
    put(env, KEY, "project:P123", False)
    assert [r["effective"]["key"] for r in listed(env, prefix="feed.")] == [
        KEY,
        "feed.signal_tags",
    ]
    mine = listed(env, project="P123", modified_only=True)
    assert [r["effective"]["key"] for r in mine] == [KEY]
    assert listed(env, project="P999", modified_only=True) == []
    assert listed(env, prefix="nothing.") == []


def test_locks_and_schedules_are_shown(env: McpHarness) -> None:
    with env.factory(False) as uow:
        settings.lock_setting(
            uow, key=KEY, locked=True, bounds=None, actor="user:alice", source="t", reason="policy"
        )
    put(env, "feed.signal_tags", "company", ["x"], applies_at=_future())
    (locked,) = listed(env, key=KEY)
    assert locked["effective"]["locked"] is True
    (later,) = listed(env, key="feed.signal_tags")
    assert later["effective"]["scheduled"][0]["new_value"] == ["x"]


def _future() -> Any:
    from datetime import timedelta

    from tl_core.util import utcnow

    return utcnow() + timedelta(days=30)


def test_an_unknown_key_and_a_key_with_a_filter_are_tool_errors(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="no setting"):
        env.call("get_settings", key="no.such")
    with pytest.raises(ToolError, match="not both"):
        env.call("get_settings", key=KEY, prefix="feed.")
    with pytest.raises(ToolError, match="not both"):
        env.call("get_settings", key=KEY, modified_only=True)


def test_the_arguments_are_bounded(env: McpHarness) -> None:
    for name in ("key", "prefix", "project"):
        with pytest.raises(ToolError):
            env.call("get_settings", **{name: "x" * 129})
