"""`tl mat`: materials, items, locations, stock, receipts and take-offs (P2-I3-T05b).

This group holds the read verbs (`tl_cli.mat_read`) and the report (`tl_cli.mat_report`). The
write verbs (`receipt receive`, `mto assign`) join the same group later; the `receipt` and `mto`
sub-groups are made here so both halves can add to them. The group is not yet added to
`tl_cli.main`; the registry glue does that.
"""

from __future__ import annotations

import typer

from tl_cli import mat_read, mat_report

app = typer.Typer(
    help="Materials: items, locations, stock, receipts, take-offs.", no_args_is_help=True
)
receipt = typer.Typer(help="Receipts of materials.", no_args_is_help=True)
mto = typer.Typer(help="Take-off (MTO) lines.", no_args_is_help=True)
app.add_typer(receipt, name="receipt")
app.add_typer(mto, name="mto")

mat_read.register(app)
mat_report.register(app)
