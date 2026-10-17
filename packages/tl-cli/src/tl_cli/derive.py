"""The `tl derive` group: derived documents, from a file to published records (P1-I3; ADR-0014).

The commands live in four modules and are mounted here: `derive_schema` (`tl derive schema ...`),
`derive_run` (open, content, start, ls, jobs, cancel, worker), `derive_read` (show, report, rows,
diff, check, validate) and `derive_publish` (publish, compensate). `tl_cli.main` registers the
group as `tl derive`. Documents are named by number and revision; a derived document by its key
(`ISD-001@A/instrument-index`) or id.
"""

from __future__ import annotations

import typer

from tl_cli import derive_publish, derive_read, derive_run, derive_schema

app = typer.Typer(
    help="Derive validated data from document files and publish it.", no_args_is_help=True
)
app.add_typer(derive_schema.app, name="schema")
for _module in (derive_run, derive_read, derive_publish):
    for _command in _module.app.registered_commands:
        app.registered_commands.append(_command)
