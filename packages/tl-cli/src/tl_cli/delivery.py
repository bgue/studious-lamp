"""The `tl delivery` group: the inbound error queue and the dry run of a mapping (P1-I7-T04d).

Each subcommand parses options, makes one call into `tl_core.integration.inbound`, and prints.
A delivery is what a signed POST became: queued, applied, a dry run, failed or killed. The error
queue is the deliveries in `failed` and `killed`; an admin retries one with the endpoint's
current mapping, optionally with a corrected payload. The received body is never shown or changed.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from tl_adapters.objectstore import make_object_store
from tl_core.integration.inbound import store as body_store
from tl_core.integration.inbound.delivery import (
    RetryInboundDelivery,
    dry_run_mapping,
    handle_retry_delivery,
)

from tl_cli.endpoint import PathArg, split_path
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

app = typer.Typer(help="Inbound deliveries: list, show, retry, dry-run.", no_args_is_help=True)

_LIST_SQL = (
    "SELECT d.delivery_id, d.state, d.received_at, d.error_code, e.app, e.name "
    "FROM int_delivery d JOIN cur_inbound_endpoint e ON e.endpoint_id = d.endpoint_id"
)
_DELIVERY_SQL = (
    "SELECT d.*, e.app, e.name FROM int_delivery d "
    "JOIN cur_inbound_endpoint e ON e.endpoint_id = d.endpoint_id "
    "WHERE d.delivery_id = :id AND d.scope = :scope"
)
_STATES = ("queued", "applied", "failed", "dry_run", "killed")


def delivery_line(row: dict[str, object]) -> str:
    """``<id>  failed  erp/orders  2026-10-18T09:00:00Z  key_not_found``: the id, the state, the
    endpoint path, the time received and the error code (``-`` when there is none)."""
    path = f"{row['app']}/{row['name']}"
    return line(row["delivery_id"], row["state"], path, row["received_at"], row["error_code"])


def _configure_store() -> None:
    """Point the inbound payload store at the object store of the environment, when there is one."""
    try:
        body_store.configure(make_object_store())
    except ValueError:
        pass


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: ProjectOption = None,
    company: CompanyOption = False,
    state: Annotated[
        str | None, typer.Option("--state", help="queued, applied, failed, ...")
    ] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Only <app>/<name>.")] = None,
    n: Annotated[int, typer.Option("-n", min=1, help="How many (newest first).")] = 50,
) -> None:
    """List deliveries, newest first. The default state is every one; ``--state failed`` is the
    error queue.
    """
    admin_gate(ctx)
    if state is not None and state not in _STATES:
        fail(f"--state must be one of {', '.join(_STATES)}")
    clauses: list[str] = []
    params: dict[str, Any] = {"n": n}
    if project is not None or company:
        clauses.append("d.scope = :scope")
        params["scope"] = scope_of(project, company)
    if state is not None:
        clauses.append("d.state = :state")
        params["state"] = state
    if endpoint is not None:
        app_name, name = split_path(endpoint)
        clauses.append("e.app = :app AND e.name = :name")
        params.update(app=app_name, name=name)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"{_LIST_SQL}{where} ORDER BY d.received_at DESC, d.delivery_id DESC LIMIT :n"
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        for row in rows(uow, sql, **params):
            typer.echo(delivery_line(row))


@app.command("show")
def show(
    ctx: typer.Context,
    delivery_id: Annotated[str, typer.Argument(help="The delivery id from `tl delivery ls`.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one delivery: what happened, never the payload."""
    admin_gate(ctx)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"delivery {delivery_id}", _DELIVERY_SQL, id=delivery_id, scope=scope)
    typer.echo(f"delivery {delivery_id}")
    typer.echo(f"endpoint {row['app']}/{row['name']}")
    typer.echo(f"version {row['endpoint_version']}")
    typer.echo(f"state {row['state']}")
    typer.echo(f"received {row['received_at']}")
    typer.echo(f"size {row['payload_size']}")
    typer.echo(f"sha256 {row['payload_sha256']}")
    typer.echo(f"attempts {row['attempts']}")
    if row["finished_at"] is not None:
        typer.echo(f"finished {row['finished_at']}")
    if row["command_count"] is not None:
        typer.echo(f"commands {row['command_count']}")
    if row["error_code"] is not None:
        typer.echo(f"error {row['error_code']}: {row['error_message']}")
    if row["corrected_object_key"] is not None:
        typer.echo("corrected yes")


@app.command("retry")
def retry(
    ctx: typer.Context,
    delivery_id: Annotated[str, typer.Argument(help="A failed delivery.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    file: Annotated[
        str | None, typer.Option("--file", help="JSON file (or -) holding a corrected payload.")
    ] = None,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Queue a failed delivery again with the endpoint's current mapping."""
    admin_gate(ctx)
    scope = scope_of(project, company)
    corrected = read_json_file(file) if file is not None else None
    _configure_store()
    with factory(ctx) as opened, service_errors(), opened() as uow:
        handle_retry_delivery(
            uow,
            RetryInboundDelivery(
                actor=actor,
                source=SOURCE,
                scope=scope,
                delivery_id=delivery_id,
                corrected_payload=corrected,
            ),
        )
    typer.echo(f"queued {delivery_id}")


@app.command("dry-run")
def dry_run(
    ctx: typer.Context,
    path: PathArg,
    project: ProjectOption = None,
    company: CompanyOption = False,
    sample: Annotated[
        str | None, typer.Option("--sample", help="JSON file (or -) holding a payload.")
    ] = None,
    delivery: Annotated[
        str | None, typer.Option("--delivery", help="Use the payload of this stored delivery.")
    ] = None,
) -> None:
    """What the endpoint's current mapping would do with a payload. Nothing is written."""
    admin_gate(ctx)
    if (sample is None) == (delivery is None):
        fail("give --sample or --delivery, not both and not neither")
    app_name, name = split_path(path)
    scope = scope_of(project, company)
    _configure_store()
    payload = read_json_file(sample) if sample is not None else None
    from tl_api.commands import command_runner

    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        endpoint_row = one(
            uow,
            f"endpoint {path}",
            "SELECT endpoint_id FROM cur_inbound_endpoint "
            "WHERE app = :app AND name = :name AND scope = :scope",
            app=app_name,
            name=name,
            scope=scope,
        )
        report = dry_run_mapping(
            uow,
            command_runner(),
            endpoint_id=endpoint_row["endpoint_id"],
            scope=scope,
            sample=payload,
            delivery_id=delivery,
        )
    typer.echo(f"status {report.status}")
    typer.echo(f"endpoint {path}")
    typer.echo(f"version {report.endpoint_version}")
    for item in report.commands:
        typer.echo(line(item.command_type, "ok" if item.permitted else "refused", item.summary))
        if not item.permitted and item.problem is not None:
            typer.echo(f"  problem {item.problem.code}: {item.problem.message}")
    for problem in report.problems:
        typer.echo(f"problem {problem.code}: {problem.message}")
