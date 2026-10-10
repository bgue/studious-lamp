"""``uv run python -m tl_mcp.dev``: the dev MCP server on stdio (brief 25.3; FANOUT D12).

    --db TARGET   the dev database: a SQLite file under the repository's dev/ directory or a
                  temporary directory (default TL_DB or dev/data/tl.db), or a local Postgres URL
                  whose database name starts with tl_test or tl_dev

stdio is the only transport. The server refuses to start for a database the guard rejects, and
when TL_ENV names a real environment. It never serves the product tools: use ``python -m tl_mcp``
for those.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import DEFAULT_DB, check_environment, find_repo_root, resolve_target
from tl_mcp.dev.runtime import DevContext


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tl-mcp-dev", description="Throughline dev MCP server.")
    parser.add_argument("--db", default=os.environ.get("TL_DB", DEFAULT_DB), metavar="TARGET")
    return parser.parse_args(argv)


def build_context(db: str) -> DevContext:
    """The context for ``db``, or :class:`DevGuardError`."""
    check_environment()
    root = find_repo_root()
    target = resolve_target(db, repo_root=root)
    return DevContext(
        repo_root=root, target=target, audit_path=root / "dev" / "data" / "dev-mcp.log.jsonl"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        ctx = build_context(args.db)
    except DevGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from tl_mcp.dev.server import build_dev_server

    build_dev_server(ctx).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
