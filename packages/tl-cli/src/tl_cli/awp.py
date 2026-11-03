"""`tl awp`: work packaging (CWPs, CWAs, the WBS, the path of construction, packages).

The read commands are in `tl_cli.awp_read`, the reports in `tl_cli.awp_report`; this module parses
nothing itself.
"""

from __future__ import annotations

import typer

from tl_cli import awp_read, awp_report, awp_write, awp_write2

app = typer.Typer(
    help="Work packaging: CWPs, CWAs, the WBS, the path of construction and packages.",
    no_args_is_help=True,
)
awp_read.register(app)
awp_write.register(app)  # after the reads: it joins their cwp and package groups
awp_write2.register(app)  # wbs, cwa and path verbs (T04d); joins the read groups too
awp_report.register(app)
