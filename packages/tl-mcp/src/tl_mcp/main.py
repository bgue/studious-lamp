"""``uv run python -m tl_mcp --actor agent:triage``: the MCP server on stdio (ADR-0005).

    --db PATH            SQLite ledger (default TL_DB or ./dev/data/tl.db)
    --actor ID           who this server acts as: `agent:<id>` or `user:<id>` (required)
    --tool-mode T=MODE   set a record-changing tool's mode; the only mode is `propose`, and
                         `write` is refused (permission model, human gate)

The record-changing tools only propose; `post_feed` is the one direct write, labelled with the
agent. Each call opens its own short transaction, so the server can run beside the API or the TUI
on the same file.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_DB = "./dev/data/tl.db"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tl-mcp", description="Throughline MCP read server.")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("TL_DB", DEFAULT_DB)))
    parser.add_argument("--actor", required=True, help="agent:<id> or user:<id>")
    parser.add_argument(
        "--tool-mode",
        action="append",
        default=[],
        metavar="TOOL=MODE",
        help="mode of a record-changing tool; only 'propose' exists (write is a human gate)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    from tl_api.tokens import check_actor

    try:
        check_actor(args.actor)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from tl_mcp.modes import ToolModeError, resolve_tool_modes

    requested = dict(item.partition("=")[::2] for item in args.tool_mode)
    try:
        resolve_tool_modes(requested)
    except ToolModeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"error: no ledger at {args.db}; run `uv run tl init` first", file=sys.stderr)
        return 2

    from tl_adapters.sqlite.factory import SqliteUowFactory

    from tl_mcp.server import build_server

    factory = SqliteUowFactory(args.db)
    try:
        build_server(factory, actor=args.actor, tool_modes=requested).run("stdio")
    finally:
        factory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
