"""Acceptance for P2-I1-T06: the awp MCP read tools and ``propose_cwp``.

Run: ``uv run python dev/accept/P2-I1/T06.py --db PATH`` (PATH is the seed from ``S4.py --keep``).
The server runs on a copy of the seed in a temporary directory, so the seed is not changed.
Prints one ``PASS <check>`` line per check, then ``T06 ok``. Nothing is sent over a network.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text
from tl_adapters.db import as_target, make_uow_factory, open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, require_command_access
from tl_core.services import proposals
from tl_mcp.server import build_server
from tl_mod_awp.commands import CreateCwp

SCOPE = "project:P123"
PROJECT = "P123"
AGENT = "agent:triage"  # the actor the server runs as (its viewer is the lowest clearance)


class Failed(Exception):
    pass


def passed(check: str) -> None:
    print(f"PASS {check}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    try:
        call()
    except error as exc:
        return exc
    raise Failed(f"expected {error.__name__}")


def cwp_count(db: Any) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(
            uow.conn()
            .execute(text("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'"))
            .scalar_one()
        )


def main(db_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        copy = work / "seed.db"
        shutil.copy(db_path, copy)
        db = as_target(str(copy))
        server = build_server(make_uow_factory(db), actor=AGENT, lake_dir=work / "lake")

        def call(tool: str, **arguments: Any) -> Any:
            """The structured content of a successful call (a list sits under ``result``)."""
            result = asyncio.run(server.call_tool(tool, arguments))
            assert result.structured_content is not None
            return result.structured_content

        def refused(tool: str, **arguments: Any) -> str:
            try:
                asyncio.run(server.call_tool(tool, arguments))
            except ToolError as exc:
                return str(exc)
            raise Failed(f"{tool} should have been refused")

        # --- the reads ---------------------------------------------------------------------
        cwps = call("list_cwps", project=PROJECT)["result"]
        need(len(cwps) == 6, f"list_cwps: {len(cwps)} rows")
        passed(f"list_cwps {len(cwps)} rows")

        number = cwps[0]["number"]
        detail = call("get_cwp", project=PROJECT, number=number)
        need(detail["number"] == number and "allocations" in detail, "get_cwp shape")
        need("counts" not in detail and "timeline" not in detail, "get_cwp has no counts")
        passed(f"get_cwp {number}")

        made_up = "P123-CWP-NOPE-9999"
        message = refused("get_cwp", project=PROJECT, number=made_up)
        need(f"no CWP {made_up!r} in project {PROJECT!r}" in message, message)
        passed("get_cwp missing (error text identical for a made-up number)")

        tree = call("wbs_tree", project=PROJECT)["result"]
        top = call("wbs_tree", project=PROJECT, depth=1)["result"]
        need(len(top) == 1 and len(top) < len(tree), f"tree {len(tree)} top {len(top)}")
        passed(f"wbs_tree {len(tree)} nodes, depth 1 gives {len(top)}")

        path = call("path_of_construction", project=PROJECT)["result"]  # an optional: wrapped
        need(path is not None and path["version"] == 1 and len(path["steps"]) > 0, "path v1")
        passed(f"path_of_construction v{path['version']} {len(path['steps'])} steps")

        # --- the proposal ------------------------------------------------------------------
        before = cwp_count(db)
        need(before == 6, f"seed has {before} CWPs")
        made = call(
            "propose_cwp",
            project=PROJECT,
            discipline="PIP",
            title="Proposed piping",
            cwa_code="A2",
        )
        proposal = made["proposal"]
        need(proposal["status"] == "pending", f"status {proposal['status']}")
        need(
            proposal["summary"] == 'Create a PIP CWP "Proposed piping" in A2',
            f"summary {proposal['summary']!r}",
        )
        need(cwp_count(db) == before, "a proposal created a CWP")
        need(len(call("list_cwps", project=PROJECT)["result"]) == 6, "list_cwps still 6")
        passed("propose_cwp waits (pending, no CWP created: list_cwps 6)")

        with open_uow(db) as uow:
            done = proposals.accept_proposal(
                uow,
                proposal_id=proposal["proposal_id"],
                by="user:uma",
                holds=lambda level: level == "user",
                holder=holder_for_actor(uow.conn(), "user:uma"),
            )
        need(done.status == "accepted", f"accepted status {done.status}")
        after = len(call("list_cwps", project=PROJECT)["result"])
        need(after == 7, f"list_cwps after accept: {after}")
        passed("accepted by a person (user:uma; list_cwps 7)")

        # --- the agent cannot make a CWP itself -------------------------------------------
        command = CreateCwp(
            actor=AGENT,
            source="mcp:triage",
            scope=SCOPE,
            discipline="PIP",
            title="Agent piping",
            cwa_code="A2",
        )
        with open_uow(db) as uow:
            refuses(ForbiddenError, lambda: require_command_access(uow.conn(), command))
        need(len(call("list_cwps", project=PROJECT)["result"]) == 7, "agent created a CWP")
        passed("agent cannot create a CWP directly (ForbiddenError; list_cwps still 7)")


def parse() -> Path:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger from S4.py --keep")
    return parser.parse_args().db


if __name__ == "__main__":
    try:
        main(parse())
        print("T06 ok")
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
