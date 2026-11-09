"""`tl awp`: work packaging (CWPs, CWAs, the WBS, the path of construction, packages).

The read commands are in `tl_cli.awp_read`, the reports in `tl_cli.awp_report`; this module parses
nothing itself.
"""

from __future__ import annotations

import typer

from tl_cli import (
    awp_iwp_read,
    awp_iwp_write,
    awp_read,
    awp_readiness_read,
    awp_report,
    awp_roc,
    awp_run,
    awp_write,
    awp_write2,
)

app = typer.Typer(
    help="Work packaging: CWPs, CWAs, the WBS, the path of construction and packages.",
    no_args_is_help=True,
)
awp_read.register(app)
awp_write.register(app)  # after the reads: it joins their cwp and package groups
awp_write2.register(app)  # wbs, cwa and path verbs (T04d); joins the read groups too
awp_report.register(app)
awp_roc.register(app)  # the rules-of-credit group (P2-I5-T01)
awp_run.register(app)  # rollup and worker verbs (T04e)
iwp_app = typer.Typer(help="Interim work packages (IWPs).", no_args_is_help=True)
app.add_typer(iwp_app, name="iwp")
awp_iwp_read.register(iwp_app)  # reads first, as for the other groups
awp_iwp_write.register(iwp_app)
awp_readiness_read.register(app)  # adds the readiness group (T04d2)
