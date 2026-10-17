"""`tl xer ls|show|activities|compare|look-ahead|resolve|trend|health`: reads of schedules (T09b).

STUB (P1-I4-T09b): `register` is the one function the group calls; the commands are added by the
ticket. Nothing is registered yet.
"""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl xer` group."""
