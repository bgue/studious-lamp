"""`tl mat`: materials, items, locations, stock, receipts and take-offs (P2-I3-T05b).

This group holds the read verbs (`tl_cli.mat_read`) and the report (`tl_cli.mat_report`). The
write verbs (`tl_cli.mat_write`) and the detail reads (`tl_cli.mat_detail`) join the same group; the
`receipt` and `mto` sub-groups are made here so each half can add to them. `ls` is an alias of
`list` on both sub-groups, as in the other `tl` groups.
"""

from __future__ import annotations

import typer

from tl_cli import mat_detail, mat_read, mat_report, mat_write

app = typer.Typer(
    help="Materials: items, locations, stock, receipts, take-offs.", no_args_is_help=True
)
receipt = typer.Typer(help="Receipts of materials.", no_args_is_help=True)
mto = typer.Typer(help="Take-off (MTO) lines.", no_args_is_help=True)
app.add_typer(receipt, name="receipt")
app.add_typer(mto, name="mto")

mat_read.register(app)
mat_report.register(app)
mat_write.register(app)
mat_detail.register(app)
receipt.command("ls", help="Alias of `receipt list`.")(mat_read.receipt_list)
mto.command("ls", help="Alias of `mto list`.")(mat_read.mto_list)
