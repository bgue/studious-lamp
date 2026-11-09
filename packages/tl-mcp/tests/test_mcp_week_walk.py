"""P2-I5-T16: the five readers walk the five weekly-plan MCP reads (T11c) over one ledger.

The readers are the five of the walks: ``user:bob`` (a plain user), ``user:ctl`` (a document
controller), ``user:boss`` (an admin), ``user:amy`` (named on the privileged record) and
``agent:bot`` (the agent). The MCP server reads every call as the lowest clearance whatever the
actor (``tl_mcp.errors``: an agent reads as the lowest, and every tool call sets it), so the five
readers must get the same answer, and none of them may see a hidden plan, IWP or item. A hidden
record answers as a missing one (the text, but for the name the caller sent). A tool name outside
``MCP_ACTIONS`` is refused. The walk is the one of ``test_confidentiality_walk`` in this package.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import McpHarness
from sqlalchemy import bindparam, text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.server import build_server
from tl_mod_awp.names import IWP, SCOPE_ITEM, WEEKLY_PLAN

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
READERS = ["user:bob", "user:ctl", "user:boss", "user:amy", "agent:bot"]
WEEK_TOOLS = (
    "list_weekly_plans",
    "get_weekly_plan",
    "get_iwp_progress",
    "get_progress_rollup",
    "list_kpis",
)
WEEK_CLOSED = "2026-W45"  # restricted
WEEK_OPEN = "2026-W46"
NO_WEEK = "2099-W01"
MISSING_IWP = "P123-IWP-8888"
CLASS_TABLE = "t16_mcp_class"
CLEAR_TABLE = "t16_mcp_clear"


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
    return awp, _load("progress_world", tests / "progress_world.py")


def text_of(server: Any, tool: str, args: dict[str, Any]) -> str:
    try:
        result = asyncio.run(server.call_tool(tool, args))
    except ToolError as exc:
        return f"ERROR {exc}"
    return result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)


def _rows(db: DbTarget, sql: str, **params: Any) -> list[dict[str, Any]]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(text(sql), params)
        return [dict(row._mapping) for row in found]  # pyright: ignore[reportPrivateUsage]


@dataclass(frozen=True)
class Ledger:
    """The ids and numbers of each class of record the walk knows of."""

    closed_plan: str  # restricted
    hidden_iwp: str  # restricted, committed to the open week
    hidden_number: str
    privileged_iwp: str  # named to amy only
    privileged_number: str
    visible_iwp: str
    visible_number: str
    scope_item: str  # restricted

    def markers(self) -> list[str]:
        """What a reply may not hold: the ids and numbers of what no reader here may read."""
        return [
            self.closed_plan,
            self.hidden_iwp,
            self.hidden_number,
            self.scope_item,
            self.privileged_iwp,
            self.privileged_number,
            WEEK_CLOSED,
        ]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db: DbTarget) -> Iterator[McpHarness]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    built = McpHarness.build(tmp_path, target=db)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def ledger(env: McpHarness, monkeypatch: pytest.MonkeyPatch) -> Ledger:
    """A closed week (restricted), an open week with a restricted and a privileged commitment, a
    Draft IWP with a restricted scope item, and the visible records."""
    awp, progress = load_worlds()
    w = awp.World(env.db)
    w.people()
    w.editions()
    pw = progress.ProgressWorld(w)
    ww = progress.WeekWorld(pw)
    ww.standards()
    closed = ww.open("2026-11-02")
    closed_iwp = ww.issued()
    ww.commit(closed, closed_iwp, hours="40.0")
    ww.outcome(closed, closed_iwp, "done")
    ww.close(closed)
    opened = ww.open("2026-11-09")
    visible = ww.issued()
    hidden = ww.issued()
    privileged = ww.issued()
    ww.commit(opened, visible, hours="20.0")
    ww.commit(opened, hidden, hours="10.0")
    ww.commit(opened, privileged, hours="12.0")
    _draft, [item] = pw.package(["8.0"])

    def number(record: str) -> str:
        return str(
            _rows(env.db, "SELECT key FROM cur_core_record WHERE id = :i", i=record)[0]["key"]
        )

    classes = {str(closed): "restricted", str(hidden): "restricted", str(item): "restricted",
               str(privileged): "privileged"}  # fmt: skip
    with open_uow(env.db) as uow:
        conn = uow.conn()
        conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        conn.execute(
            text(f"CREATE TABLE {CLEAR_TABLE} (record_id TEXT NOT NULL, account TEXT NOT NULL)")
        )
        found = conn.execute(
            text("SELECT id FROM cur_core_record WHERE type IN :t").bindparams(
                bindparam("t", expanding=True)
            ),
            {"t": [WEEKLY_PLAN, IWP, SCOPE_ITEM]},
        ).all()
        for (record_id,) in found:
            conn.execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {"i": str(record_id), "c": classes.get(str(record_id), "internal")},
            )
        conn.execute(
            text(f"INSERT INTO {CLEAR_TABLE} (record_id, account) VALUES (:r, :a)"),
            {"r": str(privileged), "a": "user:amy"},
        )
    source = ConfidentialSource(
        record_types=frozenset({WEEKLY_PLAN, IWP, SCOPE_ITEM}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
        clearance_table=CLEAR_TABLE,
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    return Ledger(
        closed_plan=str(closed),
        hidden_iwp=str(hidden),
        hidden_number=number(hidden),
        privileged_iwp=str(privileged),
        privileged_number=number(privileged),
        visible_iwp=str(visible),
        visible_number=number(visible),
        scope_item=str(item),
    )


def calls(led: Ledger) -> list[tuple[str, dict[str, Any]]]:
    """Every call of the walk: each tool with each candidate value of its arguments."""
    out: list[tuple[str, dict[str, Any]]] = [
        ("list_weekly_plans", {"project": PROJECT}),
        ("get_progress_rollup", {"project": PROJECT}),
        ("list_kpis", {"project": PROJECT}),
    ]
    for week in (WEEK_CLOSED, WEEK_OPEN, NO_WEEK):
        out.append(("get_weekly_plan", {"project": PROJECT, "week": week}))
    numbers = (led.hidden_number, led.privileged_number, led.visible_number, MISSING_IWP)
    out += [("get_iwp_progress", {"project": PROJECT, "number": n}) for n in numbers]
    return out


def test_the_five_readers_get_the_same_answers_and_none_of_the_hidden(
    env: McpHarness, ledger: Ledger, tmp_path: Path
) -> None:
    answers: dict[str, dict[tuple[str, str], str]] = {}
    for actor in READERS:
        server = build_server(env.factory, actor=actor, lake_dir=tmp_path / "lake")
        answers[actor] = {}
        for tool, args in calls(ledger):
            reply = text_of(server, tool, args)
            assert "internal error" not in reply.lower(), (actor, tool, reply[:200])
            answers[actor][(tool, repr(sorted(args.items())))] = reply
    first = answers[READERS[0]]
    for actor in READERS[1:]:
        assert answers[actor] == first, actor
    for (tool, args), reply in first.items():
        if reply.startswith("ERROR"):  # an error repeats the id the caller sent, and no more
            continue
        for marker in ledger.markers():
            assert marker not in reply, (tool, args, marker)
    listed = first[("list_weekly_plans", repr([("project", PROJECT)]))]
    assert WEEK_OPEN in listed and WEEK_CLOSED not in listed
    assert ledger.closed_plan not in listed
    key = repr(sorted({"project": PROJECT, "number": ledger.visible_number}.items()))
    assert ledger.visible_number in first[("get_iwp_progress", key)]  # the reader reads some


def test_a_hidden_plan_and_an_unknown_week_raise_the_same_text(
    env: McpHarness, ledger: Ledger
) -> None:
    server = build_server(env.factory, actor="user:bob")
    hidden = text_of(server, "get_weekly_plan", {"project": PROJECT, "week": WEEK_CLOSED})
    missing = text_of(server, "get_weekly_plan", {"project": PROJECT, "week": NO_WEEK})
    assert hidden.startswith("ERROR")
    assert hidden.replace(WEEK_CLOSED, "X") == missing.replace(NO_WEEK, "X")


def test_a_hidden_iwp_and_a_made_up_number_raise_the_same_text(
    env: McpHarness, ledger: Ledger
) -> None:
    server = build_server(env.factory, actor="agent:bot")
    for hidden_number in (ledger.hidden_number, ledger.privileged_number):
        hidden = text_of(server, "get_iwp_progress", {"project": PROJECT, "number": hidden_number})
        missing = text_of(server, "get_iwp_progress", {"project": PROJECT, "number": MISSING_IWP})
        assert hidden.startswith("ERROR")
        assert hidden.replace(hidden_number, "X") == missing.replace(MISSING_IWP, "X")


def test_every_week_tool_is_in_the_mcp_actions_and_an_unlisted_name_is_refused(
    env: McpHarness,
) -> None:
    server = build_server(env.factory, actor="agent:bot")
    for name in WEEK_TOOLS:
        assert f"mcp.{name}" in MCP_ACTIONS, name
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("delete_every_weekly_plan", {"project": PROJECT}))
