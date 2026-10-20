"""The `tl enricher` group: register enrichers and switch them on and off (P1-I7-T05a).

An enricher is code shipped with the server; an admin registers it by name, says which events it
follows and which properties of its own layer `enrich.<name>` it fills, and with which acceptance
policy per property (`auto` above a threshold, `propose`, or `shadow`). It starts switched off.
Each subcommand parses options, makes one call into `tl_core.integration.enrichers`, and prints.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast

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
    refuse_server_fields,
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
    """List the enrichers of a scope (every scope when neither option is given), one line each."""
    scope = scope_of(project, company) if project is not None or company else None
    sql = "SELECT * FROM cur_enricher"
    params: dict[str, object] = {}
    if scope is not None:
        sql += " WHERE scope = :scope"
        params["scope"] = scope
    sql += " ORDER BY name"
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        for row in rows(uow, sql, **params):
            typer.echo(enricher_line(row))


@app.command("show")
def show(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The enricher's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one registration."""
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"enricher {name}", _ENRICHER_SQL, name=name, scope=scope)
        shown = [
            f"enricher {name}",
            f"id {row['enricher_id']}",
            f"scope {row['scope']}",
            f"version {row['version']}",
            f"code_version {row['code_version']}",
            f"state {'on' if row['enabled'] else 'off'}",
            f"access {row['access']}",
            f"owner {row['owner']}",
            f"actor {row['service_actor']}",
            f"when {json.dumps(row['when'], sort_keys=True)}",
        ]
        shown += [
            f"property {p['name']} {p['kind']} {p['policy']} {p['threshold']}"
            for p in row["properties"]
        ]
        for text_line in shown:
            typer.echo(text_line)


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
    """
    admin_gate(ctx)
    scope = scope_of(project, company)
    body = read_json_file(file)
    if not isinstance(body, dict):
        fail("the file must hold a JSON object")
    refuse_server_fields(body, also=("name", "access"))
    with factory(ctx) as opened, service_errors(), opened() as uow:
        made = handle_register_enricher(
            uow,
            RegisterEnricher(
                actor=actor,
                source=SOURCE,
                scope=scope,
                name=name,
                # the service validates the value (pydantic Literal); this only narrows the type
                access=cast(Literal["user", "controller"], access),
                **body,
            ),
        )
    typer.echo(f"enricher {name}")
    typer.echo(f"id {made.stream_id}")


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
