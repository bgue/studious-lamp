"""Demo clause 8 for dev/demos/P2-INT.sh: the CLI flags, the MCP ``intent`` parameter and the TUI
text function, each used once. Prints one ``PASS clause 8: <what>`` line per surface; a miss
prints ``FAIL <what>`` and exits 1.

Usage: ``uv run python dev/accept/P2-INT/demo_cli_mcp.py DB TARGET_KEY``

* DB: the demo ledger (a SQLite path or a postgresql:// URL, read with ``as_target``). The
  signed-in session is in TL_SESSION_FILE, as the driver set it up.
* TARGET_KEY: an existing record key in project P1 that the intent points at.

The CLI runs ``tl record create --why --next --toward`` once; the MCP tool ``create_record`` is
called once in process with its ``intent`` parameter (the authorizer allows that one tool); the
TUI text function ``intent_lines`` is called once on the stored CLI intent. The database is read
through ``tl_adapters.db`` only; the URL is never printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp.types import CallToolResult
from sqlalchemy import text
from tl_adapters.db import as_target, display_target, make_engine, make_uow_factory, read_tx
from tl_api.auth import Forbidden
from tl_core.intent import Intent
from tl_mcp.server import build_server
from tl_tui.intent_text import intent_lines

PROJECT = "P1"
SCOPE = f"project:{PROJECT}"
CLI_WHY = "pour on Monday"
CLI_NEXT = "text:call the super"
MCP_WHY = "agent saw a defect"
MCP_ACTOR = "agent:demo-clause8"
ALLOWED_TOOL = "mcp.create_record"


def passed(label: str, ok: bool) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {label}")
    if not ok:
        raise SystemExit(1)


def _query_one(db: str, sql: str, params: dict[str, str]) -> object:
    engine = make_engine(as_target(db))
    try:
        with read_tx(engine) as conn:
            return conn.execute(text(sql), params).scalar_one()
    finally:
        engine.dispose()


def stored_intent(db: str, stream_id: str) -> str | None:
    """The intent column of the first event of a stream (its Created event)."""
    engine = make_engine(as_target(db))
    try:
        with read_tx(engine) as conn:
            row = conn.execute(
                text("SELECT intent FROM events WHERE stream_id = :s ORDER BY stream_version"),
                {"s": stream_id},
            ).first()
    finally:
        engine.dispose()
    if row is None:
        raise SystemExit(f"FAIL no event for stream {stream_id}")
    return row[0]


def cli_clause(db: str, target_key: str) -> str:
    """``tl record create`` with --why, --next and --toward; returns the stored intent JSON."""
    cmd = [
        "uv", "run", "tl", "record", "create", "--project", PROJECT,
        "--title", "Clause 8 CLI", "--why", CLI_WHY, "--next", CLI_NEXT,
        "--toward", f"{target_key}:~cured",
    ]  # fmt: skip
    env = dict(os.environ, TL_DB=db)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise SystemExit(f"FAIL tl record create exited {proc.returncode}: {proc.stderr.strip()}")
    match = re.search(r"^created (\S+)$", proc.stdout, re.MULTILINE)
    if match is None:
        raise SystemExit(f"FAIL no 'created' line in: {proc.stdout}")
    stored = stored_intent(db, match.group(1))
    passed(
        "clause 8: CLI --why, --next and --toward store the intent",
        stored is not None and json.loads(stored)["why"] == CLI_WHY,
    )
    assert stored is not None
    return stored


def mcp_clause(db: str, workdir: Path) -> None:
    """``create_record`` through the MCP server with the intent parameter; a proposal is pending."""
    factory = make_uow_factory(as_target(db))
    actions: list[str] = []

    def hook(actor: str, action: str, resource: str) -> None:
        actions.append(action)
        if action != ALLOWED_TOOL:
            raise Forbidden(f"{action} is not allowed in this demo")

    server = build_server(factory, actor=MCP_ACTOR, authorize_hook=hook, lake_dir=workdir / "lake")
    result = asyncio.run(
        server.call_tool(
            "create_record",
            {"scope": SCOPE, "title": "Clause 8 MCP", "intent": {"why": MCP_WHY}},
        )
    )
    assert isinstance(result, CallToolResult)
    if result.is_error:
        raise SystemExit(f"FAIL create_record refused: {result.content}")
    content = result.structured_content or {}
    proposal_id = (content.get("result", content))["proposal"]["proposal_id"]
    stored = stored_intent(db, proposal_id)
    command_payload = _query_one(
        db,
        "SELECT payload FROM events WHERE stream_id = :s ORDER BY stream_version",
        {"s": proposal_id},
    )
    no_intent_key = "intent" not in json.loads(str(command_payload))["command"]
    passed(
        "clause 8: MCP create_record intent parameter is stored on the proposal",
        actions == [ALLOWED_TOOL]
        and stored is not None
        and json.loads(stored)["why"] == MCP_WHY
        and no_intent_key,
    )


def tui_clause(stored: str) -> None:
    """``intent_lines`` on the stored CLI intent: the plain-mode lines the History panel shows."""
    lines = intent_lines(Intent.model_validate(json.loads(stored)), technical=False)
    print("  " + " | ".join(lines))
    passed(
        "clause 8: TUI History text shows Why, Next and Toward",
        lines[:1] == [f"Why: {CLI_WHY}"]
        and any(line.startswith("Next: call the super") for line in lines)
        and any(line.startswith("Toward: ") for line in lines),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: demo_cli_mcp.py DB TARGET_KEY", file=sys.stderr)
        return 2
    db, target_key = argv[1], argv[2]
    print(f"ledger {display_target(as_target(db))}")
    stored = cli_clause(db, target_key)
    with tempfile.TemporaryDirectory() as tmp:
        mcp_clause(db, Path(tmp))
    tui_clause(stored)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
