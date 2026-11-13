"""The weekly-plan MCP reads (P2-I5-T11c): five tools over a ledger of plans, IWPs and commitments.

The world is the awp ``WeekWorld`` helper (loaded by path, as ``test_awp_tools`` loads
``awp_world``): one closed plan with two IWPs committed. The reader is the agent, which reads as
the lowest clearance, so a hidden plan or IWP gets the same answer as a missing one.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_api.auth import Forbidden
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mcp.awp_week_tools import WEEK_MCP_ACTIONS
from tl_mcp.identity import MCP_ACTIONS
from tl_mod_awp.names import IWP

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
WEEK_TOOLS = {
    "list_weekly_plans",
    "get_weekly_plan",
    "get_iwp_progress",
    "get_progress_rollup",
    "list_kpis",
}


def _load(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_worlds() -> tuple[ModuleType, ModuleType]:
    """``awp_world`` first (``progress_world`` imports it by that name), then ``progress_world``."""
    tests = ROOT / "packages" / "tl-modules" / "awp" / "tests"
    awp = _load("awp_world", tests / "awp_world.py")
    progress = _load("progress_world", tests / "progress_world.py")
    return awp, progress


class Hook:
    """The test authorizer: allows the actions in ``allowed``, refuses the rest, records them."""

    def __init__(self, allowed: frozenset[str] = WEEK_MCP_ACTIONS) -> None:
        self.allowed = allowed
        self.seen: list[str] = []

    def __call__(self, actor: str, action: str, resource: str) -> None:
        self.seen.append(action)
        if action not in self.allowed:
            raise Forbidden(f"{action} is not allowed for {actor}")


@pytest.fixture
def env(tmp_path: Path, db: DbTarget) -> Iterator[McpHarness]:
    built = McpHarness.build(tmp_path, target=db)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def world(env: McpHarness) -> Any:
    """A ``WeekWorld`` over the harness's ledger: people, editions and the standards loaded."""
    awp, progress = load_worlds()
    w = awp.World(env.db)
    w.people()
    w.editions()
    return progress.build_week_world(w)


def call(env: McpHarness, tool: str, **arguments: Any) -> Any:
    """The structured result; a list result sits under ``result`` as the SDK wraps it."""
    out = env.structured(tool, **arguments)
    return out["result"] if set(out) == {"result"} else out


def refused(env: McpHarness, tool: str, **arguments: Any) -> str:
    try:
        asyncio.run(env.server.call_tool(tool, arguments))
    except ToolError as exc:
        return str(exc).removeprefix(f"Error executing tool {tool}: ")
    raise AssertionError(f"{tool} should have been refused")


@contextmanager
def hidden_iwp(db: DbTarget, iwp: str) -> Iterator[None]:
    """The IWP is restricted: the lowest viewer cannot open it (a test source, as the kpi test
    uses), so its commitments are left out of a plan and its detail answers as missing."""
    ids = [str(r["id"]) for r in _rows(db, "SELECT id FROM cur_awp_iwp")]
    with open_uow(db) as uow:
        conn = uow.conn()
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS mcp_iwp_class (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text("DELETE FROM mcp_iwp_class"))
        for row_id in ids:
            cls = "restricted" if row_id == iwp else "internal"
            conn.execute(text("INSERT INTO mcp_iwp_class VALUES (:i, :c)"), {"i": row_id, "c": cls})
    source = ConfidentialSource(
        record_types=frozenset({IWP}),
        table="mcp_iwp_class",
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
    try:
        yield
    finally:
        cf.confidential_sources = real  # type: ignore[attr-defined]


def _rows(db: DbTarget, sql: str, **params: Any) -> list[dict[str, Any]]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(text(sql), params)
        return [dict(row._mapping) for row in found]  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def plan(env: McpHarness, world: Any) -> dict[str, Any]:
    """One closed plan with two Issued IWPs committed to it, one of them done."""
    week = world.open("2026-11-02")
    first = world.issued()
    second = world.issued()
    world.commit(week, first, hours="40.0")
    world.commit(week, second, hours="32.0")
    world.outcome(week, first, "done")
    world.outcome(week, second, "missed", "Weather")
    world.close(week)
    listed = call(env, "list_weekly_plans", project=PROJECT)
    return {"plan": week, "week": listed[0]["week"], "first": first, "second": second}


# --- the declared keys ------------------------------------------------------------------------


def test_each_tool_returns_the_declared_keys(env: McpHarness, plan: dict[str, Any]) -> None:
    rows = call(env, "list_weekly_plans", project=PROJECT)
    assert rows and set(rows[0]) == {
        "id",
        "key",
        "week",
        "week_start",
        "state",
        "ppc",
        "closed_at",
    }
    detail = call(env, "get_weekly_plan", project=PROJECT, week=plan["week"])
    assert {"version", "commitments", "notes"} <= set(detail)
    assert detail["state"] == "Closed"
    assert set(detail["commitments"][0]) == {
        "iwp_id",
        "iwp_key",
        "iwp_state",
        "foreman",
        "committed_hours",
        "outcome",
        "miss_reason",
    }
    progress = call(env, "get_iwp_progress", project=PROJECT, number=_number(env, plan["first"]))
    assert set(progress) == {"number", "pct", "edition", "items", "notes"}
    rollup = call(env, "get_progress_rollup", project=PROJECT)
    assert set(rollup) == {"scope", "as_of_seq", "cwps", "nodes", "lines", "notes"}
    tiles = call(env, "list_kpis", project=PROJECT)
    assert [t["name"] for t in tiles] == ["kpi_ppc", "kpi_constraint_free"]
    assert set(tiles[0]) == {"name", "value", "numerator", "denominator", "detail"}


def _number(env: McpHarness, iwp_id: str) -> str:
    rows = _rows(env.db, "SELECT key FROM cur_core_record WHERE id = :id", id=iwp_id)
    return str(rows[0]["key"])


# --- hidden and missing answer the same way ---------------------------------------------------


def test_a_hidden_plan_and_an_unknown_week_raise_the_same_text(
    env: McpHarness, world: Any, plan: dict[str, Any]
) -> None:
    with world.hidden_plan(plan["plan"]):
        hidden = refused(env, "get_weekly_plan", project=PROJECT, week=plan["week"])
    missing = refused(env, "get_weekly_plan", project=PROJECT, week="2099-W01")
    assert hidden == missing


def test_a_hidden_plan_is_left_out_of_the_list(
    env: McpHarness, world: Any, plan: dict[str, Any]
) -> None:
    with world.hidden_plan(plan["plan"]):
        assert call(env, "list_weekly_plans", project=PROJECT) == []


def test_a_hidden_iwp_commitment_is_absent_from_the_detail_with_the_note(
    env: McpHarness, db: DbTarget, plan: dict[str, Any]
) -> None:
    with hidden_iwp(db, plan["second"]):
        detail = call(env, "get_weekly_plan", project=PROJECT, week=plan["week"])
    iwp_ids = [c["iwp_id"] for c in detail["commitments"]]
    assert plan["second"] not in iwp_ids and plan["first"] in iwp_ids
    assert "some commitments not shown" in detail["notes"]


def test_progress_of_a_hidden_iwp_is_the_unknown_iwp_error(
    env: McpHarness, db: DbTarget, plan: dict[str, Any]
) -> None:
    number = _number(env, plan["second"])
    with hidden_iwp(db, plan["second"]):
        hidden = refused(env, "get_iwp_progress", project=PROJECT, number=number)
    missing = refused(env, "get_iwp_progress", project=PROJECT, number="P123-IWP-9999")
    assert hidden == f"no IWP {number!r} in project {PROJECT!r}"
    assert missing == "no IWP 'P123-IWP-9999' in project 'P123'"


# --- the closed list and the agent's allowance -------------------------------------------------


def test_every_week_tool_name_is_in_the_mcp_actions(env: McpHarness) -> None:
    assert WEEK_MCP_ACTIONS == {f"mcp.{name}" for name in WEEK_TOOLS}
    assert WEEK_MCP_ACTIONS <= MCP_ACTIONS
    registered = {t.name for t in asyncio.run(env.server.list_tools())}
    assert WEEK_TOOLS <= registered


def test_an_agent_is_refused_for_a_tool_outside_the_list(tmp_path: Path, db: DbTarget) -> None:
    hook = Hook(allowed=WEEK_MCP_ACTIONS)
    harness = McpHarness.build(tmp_path, target=db, authorize_hook=hook)
    try:
        assert {t["name"] for t in call(harness, "list_kpis", project=PROJECT)} == {
            "kpi_ppc",
            "kpi_constraint_free",
        }
        assert refused(harness, "list_iwps", project=PROJECT).startswith("not allowed")
        assert "mcp.list_iwps" in hook.seen
    finally:
        harness.close()
