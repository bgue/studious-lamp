"""`tl punch`: the punch list from the terminal (P2-PUNCH-T02).

The group holds the write verbs (`punch_write`: raise, edit, clear, verify, reopen, void) and the
reads (`punch_read`: ls, show). Each verb parses options and makes one call into the module's
commands or views; the handlers decide.
"""

from __future__ import annotations

import typer

from tl_cli import punch_read, punch_write

app = typer.Typer(
    help="The punch list: raise, edit, clear, verify, reopen, void, ls, show.",
    no_args_is_help=True,
)


def register_all() -> None:
    """Add every verb to the ``punch`` group (called once, at import)."""
    punch_write.register(app)
    punch_read.register(app)


register_all()
