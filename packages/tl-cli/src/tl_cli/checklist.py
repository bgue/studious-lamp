"""`tl checklist`: the checklists from the terminal (P2-INSP-T05).

The group holds the write verbs (`checklist_write`: create, edit, publish, revise, retire) and the
reads (`checklist_read`: ls, show). Each verb parses options and makes one call into the module's
commands or views; the handlers decide, and the question rules run in the handlers.
"""

from __future__ import annotations

import typer

from tl_cli import checklist_read, checklist_write

app = typer.Typer(
    help="Checklists: create, edit, publish, revise, retire, ls, show.",
    no_args_is_help=True,
)


def register_all() -> None:
    """Add every verb to the ``checklist`` group (called once, at import)."""
    checklist_write.register(app)
    checklist_read.register(app)


register_all()
