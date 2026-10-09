"""The `tl dev` group: development helpers. Today: `tl dev token add` (ADR-0005).

STUB (P0-I4-T45): the command body below raises ``NotImplementedError``. Keep every name and option;
implement the body, then delete this paragraph.

The API (`tl_api`) authenticates with static bearer tokens read from a local JSON file. This command
creates one for an actor. It is a development convenience, not an account system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

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
    raise NotImplementedError("STUB (P0-I4-T45)")
