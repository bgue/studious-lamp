# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
"""The `tl endpoint` group: inbound endpoints, `/in/<app>/<name>` (P1-I7-T04b).

Each subcommand parses options, makes one call into `tl_core.integration.inbound`, and prints. An
endpoint is the admin's to author. It starts disabled and in dry-run mode: nothing is applied until
an admin switches it on and sets it live. An endpoint is named by its path ``<app>/<name>`` and the
scope it was made in. The signing secret is printed once, by `create` and `rotate-secret`; it is
in no event and cannot be shown again.


STUB (P1-I7): the functions below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph and the two lint-silencing lines at the top
of the file, and `NotImplementedError`, when you implement them.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
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
    """List the endpoints of a scope (every scope when neither option is given), one line each.

    STEPS: ``scope = scope_of(project, company)`` when either option is given, else no filter.
    In a read-only unit of work (``factory(ctx)`` then ``opened(readonly=True)``) inside
    ``service_errors()`` read ``SELECT * FROM cur_inbound_endpoint [WHERE scope = :scope] ORDER BY
    app, name`` with ``rows(...)`` and print ``endpoint_line(row)`` for each.
    """
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context, path: PathArg, project: ProjectOption = None, company: CompanyOption = False
) -> None:
    """Print one endpoint (never a secret).

    STEPS: ``app_name, name = split_path(path)``; ``scope = scope_of(project, company)``;
    ``row = one(uow, f"endpoint {path}", _ENDPOINT_SQL, app=app_name, name=name, scope=scope)``.
    Print, in this order: ``endpoint <app>/<name>``, ``id <endpoint_id>``, ``scope``, ``version``,
    ``state on|off``, ``mode live|dry-run``, ``auth``, ``access``, ``max_body_bytes``,
    ``rate_per_minute``, ``actor <service_actor>``, ``owner``, ``allowed <commands joined by ,>``
    (from ``row["allowed_commands"]``), ``mapping <json.dumps(row["mapping"])>``.
    """
    raise NotImplementedError


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
    """Create an endpoint (disabled, in dry-run). Prints its path, id and signing secret, once.

    STEPS: ``admin_gate(ctx)``; ``app_name, name = split_path(path)``; ``scope =
    scope_of(project, company)``; the mapping is the text of ``mapping_file`` (``-`` is standard
    input; use ``typer.get_text_stream("stdin").read()`` or ``open(mapping_file).read()``; an
    ``OSError`` is caught by ``service_errors()``), stripped. Inside ``service_errors()`` open a
    unit of work and call ``create_endpoint(uow, CreateInboundEndpoint(actor=actor, source=SOURCE,
    scope=scope, app=app_name, name=name, mapping=mapping, allowed_commands=allow, auth=auth,
    access=access))`` (``auth`` and ``access`` are validated by the model: a bad value is a
    ``ValidationError`` that ``service_errors()`` prints). Print ``endpoint <app>/<name>``,
    ``id <endpoint_id>``, ``secret_id <secret_id>`` and ``secret <issued.secret.secret>`` to
    stdout, then ``keep the secret: it is not shown again`` to stderr (``issued.secret`` is not
    ``None`` for a new endpoint).
    """
    raise NotImplementedError


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
    """Set an endpoint live (commands run) or back to dry-run (they are only planned).

    STEPS: ``admin_gate(ctx)``; ``new_mode`` not in ("live", "dry-run"): ``fail("the mode is live
    or dry-run")``. Split the path and read the scope and the row as ``show`` does, inside
    ``service_errors()`` and a write unit of work, and call ``handle_revise_endpoint(uow,
    ReviseInboundEndpoint(actor=actor, source=SOURCE, scope=scope, endpoint_id=row["endpoint_id"],
    changes={"dry_run": new_mode == "dry-run"}, reason=reason))``. Print ``endpoint <path> mode
    <new_mode>``.
    """
    raise NotImplementedError


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
    """Issue a new signing secret; the old one verifies for the overlap. Printed once.

    STEPS: ``admin_gate(ctx)``; split the path, scope and row as ``show`` does; in a write unit of
    work inside ``service_errors()`` call ``rotate_endpoint_secret(uow, RotateInboundSecret(
    actor=actor, source=SOURCE, scope=scope, endpoint_id=row["endpoint_id"],
    overlap_hours=overlap_hours))``. Print ``endpoint <path>``, ``secret_id <secret_id>`` and
    ``secret <issued.secret.secret>`` to stdout and ``keep the secret: it is not shown again`` to
    stderr.
    """
    raise NotImplementedError
