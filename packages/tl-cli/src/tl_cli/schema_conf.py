"""`tl schema conformance --project P [--json]`: how a project's records stand (brief 27.3, 27.5).

Any signed-in person may read it. The counts are the module's (`tl_mod_schemareg.dashboard`) and are
taken as the signed-in person: a record they may not read is not counted. These lines parse the
option, make one call and print.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import dashboard

from tl_cli.derive_support import service_errors
from tl_cli.session import require_session

HASH_WIDTH = 12


def conformance(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="The project, for example P123.")],
    as_json: Annotated[bool, typer.Option("--json", help="Print the view as JSON only.")] = False,
) -> None:
    """Show the conformance of a project's records, its live waivers and its drift.

    `<project>  schema <12 of hash>  records <n>`, then one line per record type
    (`<type>  total  ok  warning  nonconformant  waived  stale`), per live waiver
    (`waiver <key>  until <date>  <n> days left`), `expired waivers <n>` when there are any, and
    `behind <package>  <project version> < <company version>` per package the project is behind on.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = dashboard.conformance_dashboard(uow.conn(), project)
    if as_json:
        typer.echo(found.model_dump_json(indent=2))
        return
    typer.echo(f"{found.project}  schema {found.schema_hash[:HASH_WIDTH]}  records {found.total}")
    for row in found.by_type:
        typer.echo(
            f"{row.type}  total {row.total}  ok {row.ok}  warning {row.warning}  "
            f"nonconformant {row.nonconformant}  waived {row.waived}  stale {row.stale}"
        )
    for waiver in found.waivers:
        typer.echo(f"waiver {waiver.key}  until {waiver.expires}  {waiver.days_left} days left")
    if found.expired_waivers > 0:
        typer.echo(f"expired waivers {found.expired_waivers}")
    for item in found.drift:
        typer.echo(f"behind {item.package}  {item.project_version} < {item.company_version}")


def register(schema_app: typer.Typer) -> None:
    """Add `tl schema conformance`."""
    schema_app.command("conformance")(conformance)
