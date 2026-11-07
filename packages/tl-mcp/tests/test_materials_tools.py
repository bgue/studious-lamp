"""The materials MCP tools (T07): nine reads and a proposing tool that waits for a person, and a
walk of every read as five kinds of reader over classified records (ADR-0016)."""

from __future__ import annotations

import asyncio
import dataclasses
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_api.auth import Forbidden
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.modules import ConfidentialSource, load_modules, use_modules
from tl_core.services import proposals
from tl_mcp.errors import MAX_PART
from tl_mcp.materials_tools import MATERIALS_MCP_ACTIONS
from tl_mcp.server import build_server

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

from acc_s3 import Stocked, World  # noqa: E402

READS = {
    "list_material_stock",
    "get_material_lot",
    "list_material_movements",
    "list_material_receipts",
    "get_material_receipt",
    "list_material_locations",
    "list_po_lines",
    "list_mto_lines",
    "list_material_items",
}
#: The five kinds of reader. A tool always reads as the lowest viewer (tl_mcp.errors): none of them
#: reads a restricted record, a document controller and an admin included.
READERS = ["user:bob", "user:amy", "user:ctl", "user:boss", "agent:bot"]


class Hook:
    """The test authorizer: allows the materials actions while ``allowing`` is set, and counts."""

    def __init__(self) -> None:
        self.allowing = True
        self.seen: list[str] = []

    def __call__(self, actor: str, action: str, resource: str) -> None:
        self.seen.append(action)
        if not self.allowing or action not in MATERIALS_MCP_ACTIONS:
            raise Forbidden(f"{action} is not allowed for {actor}")


def call(server: MCPServer, tool: str, **arguments: Any) -> Any:
    result = asyncio.run(server.call_tool(tool, arguments))
    assert isinstance(result, CallToolResult)
    if result.is_error:
        raise ToolError(" ".join(getattr(b, "text", "") for b in result.content))
    assert result.structured_content is not None
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def refused(server: MCPServer, tool: str, **arguments: Any) -> str:
    try:
        call(server, tool, **arguments)
    except ToolError as exc:
        return str(exc)
    raise AssertionError(f"{tool} did not refuse")


@pytest.fixture
def world(db: DbTarget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[World, Stocked]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    w = World(db, tmp_path / "objects")
    return w, Stocked(w)


def server_for(
    db: DbTarget, tmp_path: Path, actor: str = "agent:triage", hook: Hook | None = None
) -> MCPServer:
    return build_server(
        make_uow_factory(db), actor=actor, authorize_hook=hook or Hook(), lake_dir=tmp_path / "lake"
    )


def test_ten_actions_name_ten_registered_tools_and_only_one_writes(
    db: DbTarget, tmp_path: Path, world: tuple[World, Stocked]
) -> None:
    server = server_for(db, tmp_path)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert len(MATERIALS_MCP_ACTIONS) == 10
    assert {a.removeprefix("mcp.") for a in MATERIALS_MCP_ACTIONS} == READS | {
        "propose_reservation"
    }
    for name in READS:
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is True, name
    annotations = tools["propose_reservation"].annotations
    assert annotations is not None and annotations.read_only_hint is False


def test_the_reads_answer_and_refuse(
    db: DbTarget, tmp_path: Path, world: tuple[World, Stocked]
) -> None:
    w, s = world
    project = w.project.removeprefix("project:")
    hook = Hook()
    server = server_for(db, tmp_path, hook=hook)
    rows = call(server, "list_material_stock", project=project)
    assert {r["lot"] for r in rows} >= {s.key1, s.key2}
    assert call(server, "list_material_stock", project=project, heat="NO-SUCH-HEAT") == []
    assert call(server, "get_material_lot", project=project, lot=s.key1)["key"] == s.key1
    number = w.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.receipt)["key"]
    assert (
        len(call(server, "get_material_receipt", project=project, number=number)["line_rows"]) == 2
    )
    assert call(server, "list_material_locations", project=project)
    assert call(server, "list_po_lines", project=project)
    assert call(server, "list_material_movements", project=project, lot=s.key1)
    assert call(server, "list_material_receipts", project=project)
    assert call(server, "list_material_items")
    assert call(server, "list_mto_lines", project=project)
    assert refused(server, "get_material_lot", project=project, lot="NO-SUCH-LOT@9")
    seen = len(hook.seen)
    refused(server, "list_material_stock", project="P" * (MAX_PART + 1))
    assert len(hook.seen) == seen, "the hook ran for an oversized part"
    hook.allowing = False
    assert "not allowed" in refused(server, "list_material_stock", project=project)


def test_propose_reservation_waits_for_a_person(
    db: DbTarget, tmp_path: Path, world: tuple[World, Stocked]
) -> None:
    w, s = world
    project = w.project.removeprefix("project:")
    server = server_for(db, tmp_path)
    line = w.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.line)["key"]
    before = call(server, "list_material_stock", project=project)
    factory = make_uow_factory(db)
    with factory(True) as uow:
        pending = len(proposals.list_proposals(uow.conn(), w.project))
    result = call(
        server,
        "propose_reservation",
        project=project,
        lot=s.key1,
        location="LA",
        mto_line=line,
        qty="1",
    )
    assert result["proposal"]["status"] == "pending"
    with factory(True) as uow:
        assert len(proposals.list_proposals(uow.conn(), w.project)) == pending + 1
    assert call(server, "list_material_stock", project=project) == before
    message = refused(
        server,
        "propose_reservation",
        project=project,
        lot=s.key1,
        location="LA",
        mto_line=line,
        qty="100000",
    )
    assert "more than is available" in message
    assert call(server, "list_material_stock", project=project) == before


def test_no_materials_tool_takes_a_viewer() -> None:
    source = Path(sys.modules["tl_mcp.materials_tools"].__file__ or "").read_text()
    assert not re.search(r"viewer", source, re.IGNORECASE)


@contextmanager
def classes(w: World, restricted: set[str]) -> Iterator[None]:
    with open_uow(w.target) as uow:
        uow.conn().execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        ids = [
            str(r["id"])
            for r in uow.conn()
            .execute(text("SELECT id FROM cur_core_record WHERE type LIKE 'materials.%'"))
            .mappings()
        ]
        for record_id in ids:
            uow.conn().execute(
                text("INSERT INTO x_class VALUES (:i, :c)"),
                {"i": record_id, "c": "restricted" if record_id in restricted else "internal"},
            )
    source = ConfidentialSource(
        record_types=frozenset(
            {"materials.StockLot", "materials.Receipt", "materials.MTOLine", "materials.POLineRef"}
        ),
        table="x_class",
        id_column="id",
        class_column="cls",
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == "materials" else m
        for m in load_modules()
    ]
    with use_modules(changed):
        yield


def make_accounts(db: DbTarget) -> None:
    with make_uow_factory(db)(False) as uow:
        for name, roles in (
            ("bob", ["user"]),
            ("amy", ["user"]),
            ("ctl", ["document_controller"]),
            ("boss", ["admin"]),
        ):
            accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=roles,
                password=prepare_password("correct horse battery"),
                by="svc:test",
            )
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="walk",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )


@pytest.mark.parametrize("actor", READERS)
def test_five_readers_walk_every_materials_read(
    db: DbTarget, tmp_path: Path, world: tuple[World, Stocked], actor: str
) -> None:
    w, s = world
    make_accounts(db)
    project = w.project.removeprefix("project:")
    number = w.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.receipt)["key"]
    line = w.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.line)["key"]
    markers = [s.key1, s.key2, number, line]
    calls: list[tuple[str, dict[str, Any]]] = [
        ("list_material_stock", {"project": project}),
        ("get_material_lot", {"project": project, "lot": s.key1}),
        ("list_material_movements", {"project": project}),
        ("list_material_receipts", {"project": project}),
        ("get_material_receipt", {"project": project, "number": number}),
        ("list_material_locations", {"project": project}),
        ("list_po_lines", {"project": project}),
        ("list_mto_lines", {"project": project}),
        ("list_material_items", {}),
    ]
    with classes(w, {s.lot1, s.lot2, s.receipt, s.line}):
        server = server_for(db, tmp_path, actor)
        replies: dict[str, str] = {}
        for tool, args in calls:
            try:
                result = asyncio.run(server.call_tool(tool, args))
                reply = (
                    result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
                )
            except ToolError as exc:
                reply = f"ERROR {exc}"
            assert "internal error" not in reply.lower(), (actor, tool)
            replies[tool] = reply
            echoed = reply
            for asked in args.values():
                echoed = echoed.replace(asked, "\0")
            for marker in markers:
                assert marker not in echoed, (actor, tool, marker)
    glove = w.lot_key(s.glove_lot)
    assert glove in replies["list_material_stock"], actor  # what the reader may read is there
    assert s.key1 not in replies["list_material_stock"], actor
    assert replies["get_material_lot"].startswith("ERROR"), actor
    assert replies["get_material_receipt"].startswith("ERROR"), actor
    assert len(replies) == len(READS)
