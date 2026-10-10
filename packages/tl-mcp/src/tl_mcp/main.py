"""``uv run python -m tl_mcp --actor agent:triage``: the MCP server on stdio (ADR-0005).

    --db PATH     SQLite ledger (default TL_DB or ./dev/data/tl.db)
    --actor ID    who this server acts as: `agent:<id>` or `user:<id>` (required)
    --lake-dir D  DuckLake directory for `lake_query` (default TL_LAKE_DIR or ./dev/data/lake)

The server never writes. It opens the ledger read-only per call, so it can run beside the API or
the TUI on the same file.
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
    parser.add_argument("--lake-dir", type=Path, default=None, help="DuckLake directory")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    from tl_api.tokens import check_actor

    try:
        check_actor(args.actor)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"error: no ledger at {args.db}; run `uv run tl init` first", file=sys.stderr)
        return 2

    from tl_adapters.sqlite.factory import SqliteUowFactory

    from tl_mcp.server import build_server

    factory = SqliteUowFactory(args.db)
    try:
        build_server(factory, actor=args.actor, lake_dir=args.lake_dir).run("stdio")
    finally:
        factory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
