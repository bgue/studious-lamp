"""The `tl mat` detail reads of the S5 fields: mto show, item-projects (T05d fills this in)."""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Add the detail read verbs to the `tl mat` group and its `mto` sub-group."""
