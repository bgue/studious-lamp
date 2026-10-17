"""`tl cost snapshots|codes|show`: reads of cost codes and snapshots (T02b).

STUB (P1-I4-T02b): `register` is the one function the group calls; the commands are added by the
ticket. Nothing is registered yet.
"""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl cost` group."""
