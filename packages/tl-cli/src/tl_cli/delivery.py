# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
"""The `tl delivery` group: the inbound error queue and the dry run of a mapping (P1-I7-T04d).

Each subcommand parses options, makes one call into `tl_core.integration.inbound`, and prints.
A delivery is what a signed POST became: queued, applied, a dry run, failed or killed. The error
queue is the deliveries in `failed` and `killed`; an admin retries one with the endpoint's
current mapping, optionally with a corrected payload. The received body is never shown or changed.


STUB (P1-I7): the functions below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph and the two lint-silencing lines at the top
of the file, and `NotImplementedError`, when you implement them.
"""

from __future__ import annotations

from typing import Annotated

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

    STEPS: admin only: ``admin_gate(ctx)``. ``state`` given and not in ``_STATES``: ``fail(f"--state
    must be one of {', '.join(_STATES)}")``. ``scope = scope_of(project, company)`` when either
    option is given. Build ``WHERE`` clauses on ``_LIST_SQL``: ``d.scope = :scope``, ``d.state =
    :state``, and for ``--endpoint`` (split with ``split_path``) ``e.app = :app AND e.name =
    :name``; add ``ORDER BY d.received_at DESC, d.delivery_id DESC LIMIT :n``. In a read-only unit
    of work inside ``service_errors()`` read with ``rows(...)`` and print ``delivery_line(row)``.
    """
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    delivery_id: Annotated[str, typer.Argument(help="The delivery id from `tl delivery ls`.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one delivery: what happened, never the payload.

    STEPS: ``admin_gate(ctx)``; ``scope = scope_of(project, company)``; ``row = one(uow,
    f"delivery {delivery_id}", _DELIVERY_SQL, id=delivery_id, scope=scope)`` in a read-only unit
    of work inside ``service_errors()``. Print, in this order: ``delivery <id>``, ``endpoint
    <app>/<name>``, ``version <endpoint_version>``, ``state <state>``, ``received
    <received_at>``, ``size <payload_size>``, ``sha256 <payload_sha256>``, ``attempts
    <attempts>``; then, only when set, ``finished <finished_at>``, ``commands <command_count>``,
    ``error <error_code>: <error_message>`` and ``corrected yes`` (when ``corrected_object_key``
    is set).
    """
    raise NotImplementedError


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
    """Queue a failed delivery again with the endpoint's current mapping.

    STEPS: ``admin_gate(ctx)``; ``scope = scope_of(project, company)``; ``corrected =
    read_json_file(file)`` when ``--file`` is given, else ``None``; ``_configure_store()``. In a
    write unit of work inside ``service_errors()`` call ``handle_retry_delivery(uow,
    RetryInboundDelivery(actor=actor, source=SOURCE, scope=scope, delivery_id=delivery_id,
    corrected_payload=corrected))``. Print ``queued <delivery_id>``.
    """
    raise NotImplementedError


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
    """What the endpoint's current mapping would do with a payload. Nothing is written.

    STEPS: ``admin_gate(ctx)``; exactly one of ``--sample`` and ``--delivery``, else ``fail("give
    --sample or --delivery, not both and not neither")``. ``app_name, name = split_path(path)``;
    ``scope = scope_of(project, company)``; the endpoint id from ``one(uow, f"endpoint {path}",
    "SELECT endpoint_id FROM cur_inbound_endpoint WHERE app = :app AND name = :name AND scope =
    :scope", ...)``; ``_configure_store()``; ``payload = read_json_file(sample)`` for ``--sample``.
    In a read-only unit of work inside ``service_errors()`` call ``dry_run_mapping(uow,
    command_runner(), endpoint_id=..., scope=scope, sample=payload, delivery_id=delivery)`` where
    ``command_runner`` is ``tl_api.commands.command_runner`` (import it inside the function).
    Print ``status <report.status>``, ``endpoint <path>``, ``version <report.endpoint_version>``;
    for each command ``<command_type>  ok|refused  <summary>`` (``line(...)``; ``ok`` when
    ``permitted``) and, for a refused one, ``  problem <code>: <message>``; for each problem of the
    report ``problem <code>: <message>``.
    """
    raise NotImplementedError
