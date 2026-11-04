"""Acceptance for P2-I3-T07: the materials MCP tools. Exit 0, one ``PASS <check>`` line per check.

Needs the seed ledger that ``dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db`` writes. The ledger is
copied to a temporary directory; the server is built the way the harness builds it, and
``register_materials_tools`` is added to it. The authorizer is a local hook that allows the ten
``MATERIALS_MCP_ACTIONS`` for the test agent (``identity.py`` is not edited).

Run: ``uv run python dev/accept/P2-I3/T07.py``.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tl_adapters.db import as_target, make_uow_factory
from tl_api.auth import Forbidden
from tl_core.services import proposals
from tl_mcp.errors import MAX_PART
from tl_mcp.materials_tools import MATERIALS_MCP_ACTIONS
from tl_mcp.server import build_server

SEED = Path(__file__).resolve().parents[3] / ".accept" / "p2-i3.db"
SCOPE = "project:P123"
ACTOR = "agent:triage"
PROJECT = "P123"
LOT = "P123-RCPT-0001@1"
MTO_LINE = "ISO-1234@A/MTO/001"
WORK_PACKAGE = "P123-CWP-PIP-0001"


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
    """The structured result of a call; a refusal raises ``ToolError``."""
    result = asyncio.run(server.call_tool(tool, arguments))
    assert isinstance(result, CallToolResult)
    if result.is_error:
        raise ToolError(_text(result))
    assert result.structured_content is not None
    content = result.structured_content
    return content["result"] if set(content) == {"result"} else content


def _text(result: CallToolResult) -> str:
    return " ".join(getattr(block, "text", "") for block in result.content)


def refused(server: MCPServer, tool: str, **arguments: Any) -> str:
    """The message of the ``ToolError`` a call raises. Fails if the call succeeds."""
    try:
        call(server, tool, **arguments)
    except ToolError as exc:
        return str(exc)
    raise AssertionError(f"{tool} did not refuse")


def run() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        shutil.copy(SEED, db)
        target = as_target(db)
        factory = make_uow_factory(target)
        hook = Hook()
        lake = root / "lake"
        server = build_server(factory, actor=ACTOR, authorize_hook=hook, lake_dir=lake)
        # build_server registers the materials tools itself since T13; registering again is a no-op
        # check of the same names, so the ten tools are the ones whose names the actions carry.
        tools = {t.name: t for t in asyncio.run(server.list_tools())}
        new_names = {name for name in tools if f"mcp.{name}" in MATERIALS_MCP_ACTIONS}

        def check(name: str, fn: Callable[[], None]) -> None:
            nonlocal failures
            try:
                fn()
            except Exception as exc:  # report and keep going: every check is printed
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            else:
                print(f"PASS {name}")

        def actions_match() -> None:
            assert len(MATERIALS_MCP_ACTIONS) == 10, len(MATERIALS_MCP_ACTIONS)
            assert new_names == {a.removeprefix("mcp.") for a in MATERIALS_MCP_ACTIONS}, new_names
            for action in MATERIALS_MCP_ACTIONS:
                assert action.startswith("mcp.") and action[len("mcp.") :] in tools, action

        def annotations_are_right() -> None:
            for name in new_names:
                annotations = tools[name].annotations
                assert annotations is not None
                if name == "propose_reservation":
                    assert annotations.read_only_hint is False
                else:
                    assert annotations.read_only_hint is True, name

        def stock_lots() -> None:
            rows = call(server, "list_material_stock", project=PROJECT)
            assert len({r["lot"] for r in rows}) >= 2, rows

        def stock_heat_narrows() -> None:
            # The seed's two lots share heat H-7781, so a heat that is present returns both rows
            # and a heat that is absent returns none: the filter is applied in both directions.
            rows = call(server, "list_material_stock", project=PROJECT)
            heats = [r["heat_no"] for r in rows if r["heat_no"] is not None]
            assert heats, "no row has a heat number"
            heat = heats[0]
            same = call(server, "list_material_stock", project=PROJECT, heat=heat)
            assert all(r["heat_no"] == heat for r in same), same
            assert len(same) == len([r for r in rows if r["heat_no"] == heat]), same
            absent = call(server, "list_material_stock", project=PROJECT, heat="NO-SUCH-HEAT")
            assert absent == [], absent

        def lot_detail() -> None:
            lot = call(server, "get_material_lot", project=PROJECT, lot=LOT)
            assert lot["key"] == LOT, lot["key"]
            assert lot["quantities"], "no balances"

        def receipt_lines() -> None:
            receipt = call(server, "get_material_receipt", project=PROJECT, number="P123-RCPT-0001")
            assert len(receipt["line_rows"]) == 2, len(receipt["line_rows"])

        def other_reads() -> None:
            assert len(call(server, "list_material_locations", project=PROJECT)) == 9
            assert len(call(server, "list_po_lines", project=PROJECT)) == 15
            mto = call(server, "list_mto_lines", project=PROJECT, work_package=WORK_PACKAGE)
            assert len(mto) == 3, len(mto)
            assert len(call(server, "list_material_items")) == 50
            assert call(server, "list_material_movements", project=PROJECT, lot=LOT)
            assert call(server, "list_material_receipts", project=PROJECT)

        def unknown_lot_refused() -> None:
            message = refused(server, "get_material_lot", project=PROJECT, lot="NO-SUCH-LOT@9")
            assert message, "empty message"

        def long_part_refused_before_hook() -> None:
            seen = len(hook.seen)
            refused(server, "list_material_stock", project="P" * (MAX_PART + 1))
            assert len(hook.seen) == seen, "the hook ran for an oversized part"

        def denied_read_refused() -> None:
            hook.allowing = False
            try:
                message = refused(server, "list_material_stock", project=PROJECT)
            finally:
                hook.allowing = True
            assert "not allowed" in message, message

        def propose_files_one_and_changes_no_stock() -> None:
            lot = call(server, "get_material_lot", project=PROJECT, lot=LOT)
            location = lot["quantities"][0]["location"]
            stock_before = call(server, "list_material_stock", project=PROJECT)
            with factory(True) as uow:
                pending_before = len(proposals.list_proposals(uow.conn(), SCOPE))
            result = call(
                server,
                "propose_reservation",
                project=PROJECT,
                lot=LOT,
                location=location,
                mto_line=MTO_LINE,
                qty="1",
            )
            assert result["proposal"]["status"] == "pending", result["proposal"]["status"]
            with factory(True) as uow:
                pending_after = len(proposals.list_proposals(uow.conn(), SCOPE))
            assert pending_after == pending_before + 1, (pending_before, pending_after)
            assert call(server, "list_material_stock", project=PROJECT) == stock_before

        def over_reservation_refused() -> None:
            lot = call(server, "get_material_lot", project=PROJECT, lot=LOT)
            location = lot["quantities"][0]["location"]
            stock_before = call(server, "list_material_stock", project=PROJECT)
            message = refused(
                server,
                "propose_reservation",
                project=PROJECT,
                lot=LOT,
                location=location,
                mto_line=MTO_LINE,
                qty="100000",
            )
            assert "more than is available" in message, message
            assert call(server, "list_material_stock", project=PROJECT) == stock_before

        def no_viewer_argument() -> None:
            source = Path(__file__).resolve().parents[3] / (
                "packages/tl-mcp/src/tl_mcp/materials_tools.py"
            )
            assert not re.search(r"viewer", source.read_text(), re.IGNORECASE)

        check("materials actions name ten registered tools", actions_match)
        check("reads are read-only and the proposing tool is not", annotations_are_right)
        check("stock lists at least two lots", stock_lots)
        check("stock heat filter narrows", stock_heat_narrows)
        check("lot detail answers for P123-RCPT-0001@1", lot_detail)
        check("receipt P123-RCPT-0001 has two lines", receipt_lines)
        check(
            "locations 9, po lines 15, mto lines 3, items 50 and movements/receipts answer",
            other_reads,
        )
        check("unknown lot is a ToolError", unknown_lot_refused)
        check("oversized part is refused before the hook", long_part_refused_before_hook)
        check("a denying authorizer refuses a read", denied_read_refused)
        check(
            "propose_reservation files one pending proposal and changes no stock",
            propose_files_one_and_changes_no_stock,
        )
        check("over-reservation is a ToolError with the handler message", over_reservation_refused)
        check("materials_tools.py has no viewer argument", no_viewer_argument)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
