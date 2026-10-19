"""The `tl endpoint` group: inbound endpoints, `/in/<app>/<name>` (P1-I7-T04b).

Each subcommand parses options, makes one call into `tl_core.integration.inbound`, and prints. An
endpoint is the admin's to author. It starts disabled and in dry-run mode: nothing is applied until
an admin switches it on and sets it live. An endpoint is named by its path ``<app>/<name>`` and the
scope it was made in. The signing secret is printed once, by `create` and `rotate-secret`; it is
in no event and cannot be shown again.
"""

from __future__ import annotations

import json
from typing import Annotated, cast

import typer
from tl_core.integration.contract import AutomationAccess, InboundAuth
from tl_core.integration.inbound.service import (
    CreateInboundEndpoint,
    ReviseInboundEndpoint,
    RotateInboundSecret,
    SetInboundEndpointEnabled,
    create_endpoint,
    handle_revise_endpoint,
    handle_set_endpoint_enabled,
    rotate_endpoint_secret,
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
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Inbound endpoints: create, show, switch, rotate.", no_args_is_help=True)

_ENDPOINT_SQL = (
    "SELECT * FROM cur_inbound_endpoint WHERE app = :app AND name = :name AND scope = :scope"
)
PathArg = Annotated[str, typer.Argument(help="The endpoint path, <app>/<name>.")]


def split_path(path: str) -> tuple[str, str]:
    """``("erp", "orders")`` for ``erp/orders``; anything else is `error: ...`, exit 1."""
    app_name, sep, name = path.partition("/")
    if not sep or not app_name or not name or "/" in name:
        fail(f"an endpoint is named <app>/<name>, not {path!r}")
    return app_name, name


def endpoint_line(row: dict[str, object]) -> str:
    """``erp/orders  off  hmac_sha256  user  dry-run  v1``: path, on/off, auth, access, mode,
    version."""
    mode = "dry-run" if row["dry_run"] else "live"
    state = "on" if row["enabled"] else "off"
    path = f"{row['app']}/{row['name']}"
    return line(path, state, row["auth"], row["access"], mode, f"v{row['version']}")


@app.command("ls")
def ls(ctx: typer.Context, project: ProjectOption = None, company: CompanyOption = False) -> None:
    """List the endpoints of a scope (every scope when neither option is given), one line each."""
    if project is None and not company:
        sql = "SELECT * FROM cur_inbound_endpoint ORDER BY app, name"
        params: dict[str, str] = {}
    else:
        sql = "SELECT * FROM cur_inbound_endpoint WHERE scope = :scope ORDER BY app, name"
        params = {"scope": scope_of(project, company)}
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        found = rows(uow, sql, **params)
    for row in found:
        typer.echo(endpoint_line(row))


@app.command("show")
def show(
    ctx: typer.Context, path: PathArg, project: ProjectOption = None, company: CompanyOption = False
) -> None:
    """Print one endpoint (never a secret)."""
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"endpoint {path}", _ENDPOINT_SQL, app=app_name, name=name, scope=scope)
    shown = [
        f"endpoint {row['app']}/{row['name']}",
        f"id {row['endpoint_id']}",
        f"scope {row['scope']}",
        f"version {row['version']}",
        f"state {'on' if row['enabled'] else 'off'}",
        f"mode {'dry-run' if row['dry_run'] else 'live'}",
        f"auth {row['auth']}",
        f"access {row['access']}",
        f"max_body_bytes {row['max_body_bytes']}",
        f"rate_per_minute {row['rate_per_minute']}",
        f"actor {row['service_actor']}",
        f"owner {row['owner']}",
        f"allowed {','.join(row['allowed_commands'])}",
        f"mapping {json.dumps(row['mapping'])}",
    ]
    for item in shown:
        typer.echo(item)


@app.command("create")
def create(
    ctx: typer.Context,
    path: PathArg,
    mapping_file: Annotated[
        str, typer.Option("--mapping-file", help="File (or -) holding the JSONata mapping.")
    ],
    allow: Annotated[
        list[str], typer.Option("--allow", help="A command the mapping may produce; repeatable.")
    ],
    project: ProjectOption = None,
    company: CompanyOption = False,
    auth: Annotated[str, typer.Option("--auth", help="hmac_sha256 or jwt_hs256.")] = "hmac_sha256",
    access: Annotated[str, typer.Option("--access", help="user or controller.")] = "user",
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Create an endpoint (disabled, in dry-run). Prints its path, id and signing secret, once."""
    admin_gate(ctx)
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors():
        if mapping_file == "-":
            raw = typer.get_text_stream("stdin").read()
        else:
            with open(mapping_file) as handle:
                raw = handle.read()
        mapping = raw.strip()
        with opened() as uow:
            issued = create_endpoint(
                uow,
                CreateInboundEndpoint(
                    actor=actor,
                    source=SOURCE,
                    scope=scope,
                    app=app_name,
                    name=name,
                    mapping=mapping,
                    allowed_commands=allow,
                    # the model validates the values at run time; the cast only types them
                    auth=cast(InboundAuth, auth),
                    access=cast(AutomationAccess, access),
                ),
            )
    assert issued.secret is not None  # a new endpoint always has its first secret
    typer.echo(f"endpoint {app_name}/{name}")
    typer.echo(f"id {issued.endpoint_id}")
    typer.echo(f"secret_id {issued.secret_id}")
    typer.echo(f"secret {issued.secret.secret}")
    typer.echo("keep the secret: it is not shown again", err=True)


def _switch(
    ctx: typer.Context, path: str, project: str | None, company: bool, actor: str, *, on: bool
) -> None:
    admin_gate(ctx)
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"endpoint {path}", _ENDPOINT_SQL, app=app_name, name=name, scope=scope)
        handle_set_endpoint_enabled(
            uow,
            SetInboundEndpointEnabled(
                actor=actor, source=SOURCE, scope=scope, endpoint_id=row["endpoint_id"], enabled=on
            ),
        )
    typer.echo(f"endpoint {path} {'on' if on else 'off'}")


@app.command("enable")
def enable(
    ctx: typer.Context,
    path: PathArg,
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an endpoint on. Prints ``endpoint <path> on``. (Given: it calls ``_switch``.)"""
    _switch(ctx, path, project, company, actor, on=True)


@app.command("disable")
def disable(
    ctx: typer.Context,
    path: PathArg,
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an endpoint off. Prints ``endpoint <path> off``. (Given: it calls ``_switch``.)"""
    _switch(ctx, path, project, company, actor, on=False)


@app.command("mode")
def mode(
    ctx: typer.Context,
    path: PathArg,
    new_mode: Annotated[str, typer.Argument(help="live or dry-run.")],
    reason: Annotated[str, typer.Option("--reason", help="Why (kept on the revision).")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Set an endpoint live (commands run) or back to dry-run (they are only planned)."""
    admin_gate(ctx)
    if new_mode not in ("live", "dry-run"):
        fail("the mode is live or dry-run")
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"endpoint {path}", _ENDPOINT_SQL, app=app_name, name=name, scope=scope)
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=actor,
                source=SOURCE,
                scope=scope,
                endpoint_id=row["endpoint_id"],
                changes={"dry_run": new_mode == "dry-run"},
                reason=reason,
            ),
        )
    typer.echo(f"endpoint {path} mode {new_mode}")


@app.command("rotate-secret")
def rotate_secret(
    ctx: typer.Context,
    path: PathArg,
    project: ProjectOption = None,
    company: CompanyOption = False,
    overlap_hours: Annotated[
        float,
        typer.Option("--overlap-hours", min=0, max=24, help="Hours the old secret still works."),
    ] = 24.0,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Issue a new signing secret; the old one verifies for the overlap. Printed once."""
    admin_gate(ctx)
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"endpoint {path}", _ENDPOINT_SQL, app=app_name, name=name, scope=scope)
        issued = rotate_endpoint_secret(
            uow,
            RotateInboundSecret(
                actor=actor,
                source=SOURCE,
                scope=scope,
                endpoint_id=row["endpoint_id"],
                overlap_hours=overlap_hours,
            ),
        )
    assert issued.secret is not None  # a rotation always issues the new secret
    typer.echo(f"endpoint {path}")
    typer.echo(f"secret_id {issued.secret_id}")
    typer.echo(f"secret {issued.secret.secret}")
    typer.echo("keep the secret: it is not shown again", err=True)
