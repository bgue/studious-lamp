"""The CLI groups of the permits module: ``tl permit``, ``tl isolation``, ``tl gastest``.

This file holds the three Typer objects and nothing else. Each later ticket adds its commands in
its own file, which registers on them by import at the bottom (the files below are empty until
then), so no two tickets edit this one.
"""

from __future__ import annotations

import typer

permit_app = typer.Typer(no_args_is_help=True, help="Permits to work.")
isolation_app = typer.Typer(no_args_is_help=True, help="Isolations (lockout of energy).")
gastest_app = typer.Typer(no_args_is_help=True, help="Gas tests.")

# Each ticket's commands register on the objects above when its module is imported.
import tl_mod_permits.cli_gastest  # noqa: E402, F401
import tl_mod_permits.cli_isolation  # noqa: E402, F401
import tl_mod_permits.cli_permit_read  # noqa: E402, F401
import tl_mod_permits.cli_permit_write  # noqa: E402, F401
