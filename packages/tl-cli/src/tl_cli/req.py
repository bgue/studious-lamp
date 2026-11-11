"""The `tl req` and `tl wo` groups (P2-I4A-T04e1). The write verbs are in ``req_write``; the reads
of T04d join the same groups later.

``register_all`` adds the write verbs to both groups. It runs when this module is imported, so
``main`` needs only the import and one ``add_typer`` per group.
"""

from __future__ import annotations

import typer

from tl_cli import req_read, req_write

app = typer.Typer(
    help="Requisitions: raise, edit, approve, reject and cancel.", no_args_is_help=True
)
wo_app = typer.Typer(
    help="Work orders: schedule, assign, start, complete and close.", no_args_is_help=True
)


def register_all() -> None:
    """Add every write verb to ``req`` and ``wo``."""
    req_write.register(app, wo_app)
    req_read.register(app, wo_app)


register_all()
