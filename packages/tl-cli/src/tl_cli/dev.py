"""The `tl dev` group: development helpers. Today: `tl dev token add` (ADR-0005).

The API (`tl_api`) authenticates with static bearer tokens read from a local JSON file. This command
creates one for an actor. It is a development convenience, not an account system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_api.tokens import add_token

app = typer.Typer(help="Development helpers.", no_args_is_help=True)
token_app = typer.Typer(help="Dev bearer tokens for the API (ADR-0005).", no_args_is_help=True)
app.add_typer(token_app, name="token")

DEFAULT_TOKENS = "./dev/data/tokens.json"


@token_app.command("add")
def add(
    actor: Annotated[
        str, typer.Argument(help="Actor the token stands for: user:<id> or agent:<id>.")
    ],
    tokens: Annotated[
        Path,
        typer.Option("--tokens", envvar="TL_TOKENS", help="Token file (created if missing)."),
    ] = Path(DEFAULT_TOKENS),
) -> None:
    """Create a bearer token for ACTOR, store it in the token file, and print it."""
    try:
        token = add_token(tokens, actor)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(token)
    typer.echo(f"added token for {actor} to {tokens}", err=True)
