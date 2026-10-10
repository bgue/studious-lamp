"""`tl serve`: the REST API and event stream on the dev ledger (P0-I4; ADR-0005).

A thin wrapper over ``tl_api.main.main`` (what ``just serve`` runs): it passes the ledger chosen by
the root ``--db`` option and the options below, and exits with the server's exit code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

DEFAULT_TOKENS = "./dev/data/tokens.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def serve(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = DEFAULT_PORT,
    tokens: Annotated[
        Path, typer.Option("--tokens", envvar="TL_TOKENS", help="Dev token file.")
    ] = Path(DEFAULT_TOKENS),
    insecure_dev: Annotated[
        bool, typer.Option("--insecure-dev", help="Allow a non-loopback bind (dev only).")
    ] = False,
) -> None:
    """Serve the API and the event stream on the dev ledger (loopback unless --insecure-dev)."""
    from tl_api import main as api_main

    argv = ["--db", str(ctx.obj), "--tokens", str(tokens), "--host", host, "--port", str(port)]
    if insecure_dev:
        argv.append("--insecure-dev")
    raise typer.Exit(code=api_main.main(argv))
