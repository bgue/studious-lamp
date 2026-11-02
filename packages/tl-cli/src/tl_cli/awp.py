"""`tl awp`: work packaging (CWPs, CWAs, the WBS, the path of construction, packages).

The read commands are in `tl_cli.awp_read`; this module parses nothing itself.
"""

from __future__ import annotations

import typer

from tl_cli import awp_read

app = typer.Typer(
    help="Work packaging: CWPs, CWAs, the WBS, the path of construction and packages.",
    no_args_is_help=True,
)
awp_read.register(app)
