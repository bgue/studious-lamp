"""`tl insp`: inspections from the terminal (P2-INSP-T04).

The group holds the write verbs (`insp_write`: plan, schedule, record, verify, reinspect, cancel)
and the reads (`insp_read`: ls, show, export). Each verb parses options and makes one call into the
module's commands or views; the handlers decide.
"""

from __future__ import annotations

import typer

from tl_cli import insp_read, insp_write

app = typer.Typer(
    help="Inspections: plan, schedule, record, verify, reinspect, cancel, ls, show, export.",
    no_args_is_help=True,
)


def register_all() -> None:
    """Add every verb to the ``insp`` group (called once, at import)."""
    insp_write.register(app)
    insp_read.register(app)


register_all()
