# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema package publish|deprecate|retire` and `tl schema adopt|adoptions|drift` (T05a2).

STUB: this file is the interface P1-I8-T05a2 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `register` is complete.

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
from tl_mod_schemareg import analysis, views
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
    # STEPS
    # 1. db = ctx.obj; require_admin(db); target = resolve_package(db, ref).
    # 2. In `with service_errors(), open_uow(db) as uow:` call handle_publish_schema_package with
    #    a PublishSchemaPackage(actor=acting(db, actor), source=SOURCE, scope="company",
    #    package_id=target, auto_adopt=auto_adopt); keep the CommandResult.
    # 3. Print `published <result.key> <result.stream_id>`. With --auto-adopt print a second line
    #    `auto-adopted <n>`, where n counts the events of the result whose event_type is
    #    "Adoption.Pinned".
    raise NotImplementedError("STEPS: see the comments")


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
    # STEPS
    # 1. require_admin(db); target = resolve_package(db, ref).
    # 2. Call handle_deprecate_schema_package with DeprecateSchemaPackage(actor, source, scope
    #    "company" as in publish, package_id=target, reason=reason, replacement=replacement).
    # 3. Print `deprecated <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


def retire(ctx: typer.Context, ref: _Ref, reason: _Reason, actor: Actor = DEV_ACTOR) -> None:
    """Take a deprecated version out of every effective schema (admin).

    Refused while a project pins it. Prints `retired <name@version>`.
    """
    # STEPS
    # 1. require_admin(db); target = resolve_package(db, ref).
    # 2. Call handle_retire_schema_package with RetireSchemaPackage(actor, source, scope "company",
    #    package_id=target, reason=reason).
    # 3. Print `retired <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


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
    # STEPS
    # 1. require_admin(db).
    # 2. Call handle_adopt_schema_package with AdoptSchemaPackage(actor=acting(db, actor),
    #    source=SOURCE, scope=f"project:{project}", project=project, package=package,
    #    version=version, impact_sha256=impact_sha256).
    # 3. Print `adopted <project> <package>@<version>`.
    raise NotImplementedError("STEPS: see the comments")


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
    # STEPS
    # 1. require_session(db); read views.adoption_views(uow.conn(), project) in a read-only unit of
    #    work inside service_errors().
    # 2. With none print `no adoptions` and return.
    # 3. Otherwise one line per adoption in the format of the docstring; cell() for the previous
    #    version and the class, which may be None.
    raise NotImplementedError("STEPS: see the comments")


def drift(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
) -> None:
    """Show which company packages a project is behind on, one line each.

    `<package>  project <version>  company <version>  behind|current  pinned|following`.
    """
    # STEPS
    # 1. require_session(db); inside service_errors() call views.drift_views(project).
    # 2. One line per item in the format of the docstring: `behind` when item.behind else
    #    `current`; `pinned` when item.pinned else `following`.
    raise NotImplementedError("STEPS: see the comments")


def register(package_app: typer.Typer, schema_app: typer.Typer) -> None:
    """Add the commands: three to `tl schema package`, three to `tl schema`."""
    package_app.command("publish")(publish)
    package_app.command("deprecate")(deprecate)
    package_app.command("retire")(retire)
    schema_app.command("adopt")(adopt)
    schema_app.command("adoptions")(adoptions)
    schema_app.command("drift")(drift)
