"""The CLI group of the QR module (ADR-0029).

The hook ref `tl_mod_qr.cli:qr_app` names the group `qr`. An attribute `<x>_app` gives the group
`<x>`. The group has no command yet (T07 fills it).
"""

from __future__ import annotations

import typer

qr_app = typer.Typer(no_args_is_help=True)


@qr_app.command(hidden=True)
def placeholder() -> None:
    """Hidden until T07 adds the real commands (removed there)."""
