"""`tl schema package publish|deprecate|retire` and `tl schema adopt|adoptions|drift` (T05a2).

Publishing, deprecating, retiring and adopting are the administrator's (FANOUT D2); the lists are
any signed-in person's. The rules are the module's (`tl_mod_schemareg.handlers`); these commands
parse options, make one call and print. A package that is not in the right state, an adoption that
needs the digest of the impact report and a retire that a project still pins are the module's
errors (`error: ...` on stderr, exit 1).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import views
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage, handle_adopt_schema_package
from tl_mod_schemareg.handlers.packages import (
    DeprecateSchemaPackage,
    PublishSchemaPackage,
    RetireSchemaPackage,
    handle_deprecate_schema_package,
    handle_publish_schema_package,
    handle_retire_schema_package,
)

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, cell, service_errors
from tl_cli.schema_pkg import resolve_package
from tl_cli.session import require_admin, require_session

_Ref = Annotated[str, typer.Argument(help="A package id or name@version, for example acme@1.1.0.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why; kept in the ledger.")]


def publish(
    ctx: typer.Context,
    ref: _Ref,
    auto_adopt: Annotated[
        bool,
        typer.Option(
            "--auto-adopt", help="Move the projects that pin the version below, if it is additive."
        ),
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Publish an approved package version (admin). Prints `published <name@version> <id>`.

    With `--auto-adopt` it adds `auto-adopted <n>`: the projects whose pin moved to this version.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    target = resolve_package(db, ref)
    with service_errors(), open_uow(db) as uow:
        made = handle_publish_schema_package(
            uow,
            PublishSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=target,
                auto_adopt=auto_adopt,
            ),
        )
    typer.echo(f"published {made.key} {made.stream_id}")
    if auto_adopt:
        moved = sum(1 for event in made.events if event.event_type == "Adoption.Pinned")
        typer.echo(f"auto-adopted {moved}")


def deprecate(
    ctx: typer.Context,
    ref: _Ref,
    reason: _Reason,
    replacement: Annotated[
        str | None, typer.Option("--replacement", help="The version to use instead.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Stop new adoptions of a published version (admin). Prints `deprecated <name@version>`."""
    db: DbTarget = ctx.obj
    require_admin(db)
    target = resolve_package(db, ref)
    with service_errors(), open_uow(db) as uow:
        done = handle_deprecate_schema_package(
            uow,
            DeprecateSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=target,
                reason=reason,
                replacement=replacement,
            ),
        )
    typer.echo(f"deprecated {done.key}")


def retire(ctx: typer.Context, ref: _Ref, reason: _Reason, actor: Actor = DEV_ACTOR) -> None:
    """Take a deprecated version out of every effective schema (admin).

    Refused while a project pins it. Prints `retired <name@version>`.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    target = resolve_package(db, ref)
    with service_errors(), open_uow(db) as uow:
        done = handle_retire_schema_package(
            uow,
            RetireSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope="company",
                package_id=target,
                reason=reason,
            ),
        )
    typer.echo(f"retired {done.key}")


def adopt(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
    package: Annotated[str, typer.Argument(help="The company package, for example acme.")],
    version: Annotated[str, typer.Argument(help="The version to pin, for example 1.1.0.")],
    impact_sha256: Annotated[
        str | None,
        typer.Option(
            "--impact-sha256",
            help="The digest `tl schema package impact --project` printed; needed unless additive.",
        ),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Pin a company package version for a project (admin).

    Prints `adopted <project> <package>@<version>`. A change that is not additive is refused
    without the digest of the impact report the caller read.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    with service_errors(), open_uow(db) as uow:
        handle_adopt_schema_package(
            uow,
            AdoptSchemaPackage(
                actor=acting(db, actor),
                source=SOURCE,
                scope=f"project:{project}",
                project=project,
                package=package,
                version=version,
                impact_sha256=impact_sha256,
            ),
        )
    typer.echo(f"adopted {project} {package}@{version}")


def adoptions(
    ctx: typer.Context,
    project: Annotated[
        str | None, typer.Option("--project", help="Only this project's pins.")
    ] = None,
) -> None:
    """List the pins, one line each.

    `<project>  <package>@<version>  from <previous or ->  <class or ->  by <actor>`. With none:
    `no adoptions`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        rows = views.adoption_views(uow.conn(), project)
    if not rows:
        typer.echo("no adoptions")
        return
    for row in rows:
        typer.echo(
            f"{row.project}  {row.package}@{row.version}  from {cell(row.previous_version)}  "
            f"{cell(row.worst_class)}  by {row.adopted_by}"
        )


def drift(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
) -> None:
    """Show which company packages a project is behind on, one line each.

    `<package>  project <version>  company <version>  behind|current  pinned|following`.
    """
    db: DbTarget = ctx.obj
    require_session(db)
    with service_errors():
        items = views.drift_views(project)
    for item in items:
        state = "behind" if item.behind else "current"
        pin = "pinned" if item.pinned else "following"
        typer.echo(
            f"{item.package}  project {item.project_version}  company {item.company_version}  "
            f"{state}  {pin}"
        )


def register(package_app: typer.Typer, schema_app: typer.Typer) -> None:
    """Add the commands: three to `tl schema package`, three to `tl schema`."""
    package_app.command("publish")(publish)
    package_app.command("deprecate")(deprecate)
    package_app.command("retire")(retire)
    schema_app.command("adopt")(adopt)
    schema_app.command("adoptions")(adoptions)
    schema_app.command("drift")(drift)
