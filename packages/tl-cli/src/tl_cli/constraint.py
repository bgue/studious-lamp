"""`tl constraint`: constraints on records (core).

The reads are in `tl_cli.constraint_read`, the write verbs in `tl_cli.constraint_write`; this module
parses nothing itself.
"""

from __future__ import annotations

import typer

from tl_cli import constraint_read, constraint_write

app = typer.Typer(help="Constraints on records (core).", no_args_is_help=True)
constraint_read.register(app)
constraint_write.register(app)
