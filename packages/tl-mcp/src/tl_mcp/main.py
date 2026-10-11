"""``TL_AGENT_TOKEN=... uv run python -m tl_mcp``: the MCP server on stdio (ADR-0005, ADR-0009).

    TL_AGENT_TOKEN       the agent's token (`tl admin token issue <agent> --label <what for>`);
                         it names who the server acts as and is checked again on every call
    --db TARGET          SQLite ledger file or postgresql:// URL (default TL_DB or
                         ./dev/data/tl.db; prefer TL_DB for a URL, it carries the password)
    --lake-dir D         DuckLake directory for `lake_query` (default TL_LAKE_DIR)
    --tool-mode T=MODE   set a record-changing tool's mode; the only mode is `propose`, and
                         `write` is refused (permission model, human gate)

The record-changing tools only propose; `post_feed` is the one direct write, labelled with the
agent. Each call opens its own short transaction, so the server can run beside the API or the TUI
on the same ledger.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from tl_adapters.db import DbTarget, as_target, display_target
from tl_core.files.types import ObjectStore

from tl_mcp.identity import (
    HOW_TO_GET_ONE,
    TOKEN_ENV,
    AgentTokenError,
    resolve_agent,
    token_authorizer,
    token_from_env,
)

DEFAULT_DB = "./dev/data/tl.db"


def _database(text: str) -> DbTarget:
    """``--db`` as a target; a bad value is reported without repeating it (a URL has a password)."""
    try:
        return as_target(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tl-mcp", description="Throughline MCP read server.")
    parser.add_argument(
        "--db", type=_database, default=None, help="SQLite file or postgresql:// URL (TL_DB)"
    )
    parser.add_argument("--actor", default=None, help=argparse.SUPPRESS)  # removed: see main()
    parser.add_argument(
        "--tool-mode",
        action="append",
        default=[],
        metavar="TOOL=MODE",
        help="mode of a record-changing tool; only 'propose' exists (write is a human gate)",
    )
    parser.add_argument("--lake-dir", type=Path, default=None, help="DuckLake directory")
    return parser.parse_args(argv)


def object_store_from_env() -> ObjectStore | None:
    """The object store the environment names, or ``None`` (extension record bodies unavailable)."""
    from tl_adapters.objectstore import make_object_store

    try:
        return make_object_store()
    except ValueError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        db = args.db if args.db is not None else as_target(os.environ.get("TL_DB", DEFAULT_DB))
    except ValueError as exc:  # TL_DB holds something that is not a database target
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.actor is not None:
        print(
            f"error: --actor was removed: an agent is identified by its token. Set "
            f"{TOKEN_ENV}; {HOW_TO_GET_ONE}",
            file=sys.stderr,
        )
        return 2
    from tl_mcp.modes import ToolModeError, resolve_tool_modes

    requested = dict(item.partition("=")[::2] for item in args.tool_mode)
    try:
        resolve_tool_modes(requested)
    except ToolModeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        token = token_from_env()
    except AgentTokenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from tl_adapters.backend import BackendUnavailableError, ledger_exists, open_backend

    try:
        found = ledger_exists(db)
        factory = open_backend(db) if found else None
    except (BackendUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if factory is None:
        print(
            f"error: no ledger at {display_target(db)}; run `uv run tl init` first", file=sys.stderr
        )
        return 2

    from tl_mcp.server import build_server

    try:
        try:
            principal = resolve_agent(factory, token)
        except AgentTokenError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        build_server(
            factory,
            actor=principal.actor,
            authorize_hook=token_authorizer(factory, token),
            tool_modes=requested,
            lake_dir=args.lake_dir,
            object_store=object_store_from_env(),
        ).run("stdio")
    finally:
        factory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
