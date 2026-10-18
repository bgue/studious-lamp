# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
"""The `tl enricher` group: register enrichers and switch them on and off (P1-I7-T05a).

An enricher is code shipped with the server; an admin registers it by name, says which events it
follows and which properties of its own layer `enrich.<name>` it fills, and with which acceptance
policy per property (`auto` above a threshold, `propose`, or `shadow`). It starts switched off.
Each subcommand parses options, makes one call into `tl_core.integration.enrichers`, and prints.


STUB (P1-I7): the functions below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph and the two lint-silencing lines at the top
of the file, and `NotImplementedError`, when you implement them.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from tl_core.integration.enrichers.service import (
    RegisterEnricher,
    SetEnricherEnabled,
    handle_register_enricher,
    handle_set_enricher_enabled,
)

from tl_cli.integration_support import (
    DEFAULT_ACTOR,
    SOURCE,
    ActorOption,
    CompanyOption,
    ProjectOption,
    admin_gate,
    factory,
    fail,
    line,
    one,
    read_json_file,
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Enrichers: register, list, show, switch.", no_args_is_help=True)

_ENRICHER_SQL = "SELECT * FROM cur_enricher WHERE name = :name AND scope = :scope"


def enricher_line(row: dict[str, object]) -> str:
    """``doc_classifier  off  user  v1  1.0.0``: name, on/off, access, version, code version."""
    state = "on" if row["enabled"] else "off"
    return line(row["name"], state, row["access"], f"v{row['version']}", row["code_version"])


@app.command("ls")
def ls(ctx: typer.Context, project: ProjectOption = None, company: CompanyOption = False) -> None:
    """List the enrichers of a scope (every scope when neither option is given), one line each.

    STEPS: ``scope = scope_of(project, company)`` when either option is given, else no filter.
    In a read-only unit of work inside ``service_errors()`` read ``SELECT * FROM cur_enricher
    [WHERE scope = :scope] ORDER BY name`` with ``rows(...)`` and print ``enricher_line(row)``.
    """
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The enricher's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one registration.

    STEPS: ``scope = scope_of(project, company)``; ``row = one(uow, f"enricher {name}",
    _ENRICHER_SQL, name=name, scope=scope)`` in a read-only unit of work inside
    ``service_errors()``. Print, in this order: ``enricher <name>``, ``id <enricher_id>``,
    ``scope``, ``version``, ``code_version``, ``state on|off``, ``access``, ``owner``, ``actor
    <service_actor>``, ``when <json.dumps(row["when"], sort_keys=True)>``; then for each property
    of ``row["properties"]`` one line ``property <name> <kind> <policy> <threshold>``.
    """
    raise NotImplementedError


@app.command("register")
def register(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The name of an installed enricher.")],
    file: Annotated[str, typer.Option("--file", help="JSON file (or -) with when and properties.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    access: Annotated[str, typer.Option("--access", help="user or controller.")] = "user",
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Register an installed enricher. It starts switched off.

    The file holds ``when`` (the events it follows, a filter object) and ``properties`` (a list of
    ``{"name", "kind", "policy", "threshold"}``).

    STEPS: ``admin_gate(ctx)``; ``scope = scope_of(project, company)``; ``body =
    read_json_file(file)``, which must be a JSON object (else ``fail("the file must hold a JSON
    object")``). In a write unit of work inside ``service_errors()`` call
    ``handle_register_enricher(uow, RegisterEnricher(actor=actor, source=SOURCE, scope=scope,
    name=name, access=access, **body))``. Print ``enricher <name>`` and ``id <stream_id>``.
    """
    raise NotImplementedError


def _switch(
    ctx: typer.Context, name: str, project: str | None, company: bool, actor: str, *, on: bool
) -> None:
    admin_gate(ctx)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"enricher {name}", _ENRICHER_SQL, name=name, scope=scope)
        handle_set_enricher_enabled(
            uow,
            SetEnricherEnabled(
                actor=actor, source=SOURCE, scope=scope, enricher_id=row["enricher_id"], enabled=on
            ),
        )
    typer.echo(f"enricher {name} {'on' if on else 'off'}")


@app.command("enable")
def enable(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The enricher's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an enricher on. Prints ``enricher <name> on``. (Given: it calls ``_switch``.)"""
    _switch(ctx, name, project, company, actor, on=True)


@app.command("disable")
def disable(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The enricher's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an enricher off. Prints ``enricher <name> off``. (Given: it calls ``_switch``.)"""
    _switch(ctx, name, project, company, actor, on=False)
