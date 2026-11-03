"""The `tl mat` write verbs: receipt receive, move, reserve, mto assign (T05c fills this in)."""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Add the write verbs to the `tl mat` group and its `receipt` and `mto` sub-groups."""
