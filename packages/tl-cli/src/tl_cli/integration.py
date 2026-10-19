"""The `tl integration` group: run the integration workers, and see where they stand (P1-I7).

`serve` is the one process that makes the integration layer work: it follows the ledger for the
rules and the enrichers, and runs the queued jobs of two kinds, `action` (an invoked action) and
`inbound.map` (a received delivery). Each pass reads the kill switch and the egress allow-list
afresh, so a change takes effect at the next pass. `--once` runs until nothing is left and exits,
which is what a test or a cron job wants. `status` prints the cursors, the queues and the switch.
"""

from __future__ import annotations

import time
from typing import Annotated

import typer
from tl_adapters.objectstore import make_object_store
from tl_adapters.queue import job_queue_for
from tl_api.commands import command_runner
from tl_core.integration.actions.jobs import ActionJobKind
from tl_core.integration.actions.service import default_policy
from tl_core.integration.actions.wiring import action_executors
from tl_core.integration.apps import (
    RegisterIntegrationApp,
    SetIntegrationAppEnabled,
    handle_register_app,
    handle_set_app_enabled,
)
from tl_core.integration.contract import ACTION_MAX_RESULT_BYTES
from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
from tl_core.integration.inbound.store import configure as configure_inbound_store
from tl_core.integration.inbound.worker import InboundMapJobKind
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.rules.engine import RulesWorker
from tl_core.jobs.runner import JobRunner
from tl_core.webhooks.base import UowFactory
from tl_core.webhooks.transport import HttpxTransport

from tl_cli.integration_support import (
    DEFAULT_ACTOR,
    SOURCE,
    ActorOption,
    CompanyOption,
    ProjectOption,
    admin_gate,
    factory,
    line,
    one,
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Run the integration workers; see their state.", no_args_is_help=True)

apps = typer.Typer(
    help="Integration apps: the owner of endpoints, rules, actions, enrichers.",
    no_args_is_help=True,
)
app.add_typer(apps, name="app")

IDLE_S = 2.0
_APP_SQL = "SELECT * FROM cur_integration_app WHERE name = :name AND scope = :scope"


def one_pass(opened: UowFactory) -> tuple[int, int, int, int]:
    """Run the rules, the enrichers and the queued jobs until each is idle once.

    Returns ``(events read by rules, events read by enrichers, jobs run, killed)``. The egress
    policy is read from the settings and the kinds are built here, every pass.
    """
    runner = command_runner()
    rule_stats = RulesWorker(opened, runner).run_until_idle()
    enrich_stats = EnrichmentDispatcher(opened).run_until_idle()
    with opened(readonly=True) as uow:
        policy = default_policy(uow)
        queue = job_queue_for(uow.conn())
    executors = action_executors(
        opened, policy=policy, transport=HttpxTransport(max_response_bytes=ACTION_MAX_RESULT_BYTES)
    )
    try:
        store = make_object_store()
        configure_inbound_store(store)
    except ValueError:
        store = None  # no object store configured: deliveries cannot be mapped, actions still run
    kinds: list[ActionJobKind | InboundMapJobKind] = [ActionJobKind(executors)]
    if store is not None:
        kinds.append(InboundMapJobKind(runner, store))
    jobs = JobRunner(opened, queue, kinds).run_until_idle()
    return (
        rule_stats.read,
        enrich_stats.read,
        len(jobs),
        rule_stats.killed + enrich_stats.killed,
    )


@app.command("serve")
def serve(
    ctx: typer.Context,
    once: Annotated[
        bool, typer.Option("--once", help="Run until idle, print what was done, and exit.")
    ] = False,
    interval: Annotated[
        float, typer.Option("--interval", min=0.1, help="Seconds to wait when idle.")
    ] = IDLE_S,
) -> None:
    """Run the rules worker, the enrichment dispatcher and the action and inbound job runners.

    Prints ``rules <n> enrich <n> jobs <n> killed <n>`` after a ``--once`` run (the events the
    two followers read, the jobs run, and the events passed over while the kill switch was on).
    Without ``--once`` it runs until interrupted and prints nothing per pass.
    """
    with factory(ctx) as opened, service_errors():
        if once:
            r, e, j, k = one_pass(opened)
            typer.echo(f"rules {r} enrich {e} jobs {j} killed {k}")
            return
        try:
            while True:
                r, e, j, _ = one_pass(opened)
                if r == 0 and e == 0 and j == 0:
                    time.sleep(interval)
        except KeyboardInterrupt:
            typer.echo("stopped")


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Where the integration layer stands.

    Prints ``kill_switch on|off``, the cursor of each follower (``cursor rules <seq>``,
    ``cursor enrichers <seq>``), ``last_seq <seq>`` (the ledger's newest event), the jobs by kind
    and state (``jobs <kind> <state> <n>``), and the inbound deliveries by state
    (``deliveries <state> <n>``).
    """
    with factory(ctx) as opened, opened(readonly=True) as uow, service_errors():
        typer.echo(f"kill_switch {'on' if kill_switch_on(uow.conn()) else 'off'}")
        cursors = {
            "rules": "rule_cursor",
            "enrichers": "enrich_cursor",
        }
        for name, table in cursors.items():
            found = rows(uow, f"SELECT last_seq FROM {table} WHERE name = :n", n=name)  # noqa: S608
            typer.echo(f"cursor {name} {found[0]['last_seq'] if found else 0}")
        newest = rows(uow, "SELECT COALESCE(MAX(seq), 0) AS s FROM events")[0]["s"]
        typer.echo(f"last_seq {newest}")
        for row in rows(
            uow,
            "SELECT kind, state, COUNT(*) AS n FROM job_queue "
            "WHERE kind IN ('action', 'inbound.map') GROUP BY kind, state ORDER BY kind, state",
        ):
            typer.echo(f"jobs {row['kind']} {row['state']} {row['n']}")
        for row in rows(
            uow, "SELECT state, COUNT(*) AS n FROM int_delivery GROUP BY state ORDER BY state"
        ):
            typer.echo(f"deliveries {row['state']} {row['n']}")


# --- apps -------------------------------------------------------------------------------------


@apps.command("add")
def app_add(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The app's slug (a-z, 0-9, - and _).")],
    label: Annotated[str, typer.Option("--label", help="What people call it.")],
    description: Annotated[str, typer.Option("--description", help="What it is for.")] = "",
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Register an app. Prints ``app <name>`` and ``id <app id>``. It starts switched on."""
    admin_gate(ctx)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        made = handle_register_app(
            uow,
            RegisterIntegrationApp(
                actor=actor, source=SOURCE, scope=scope, name=name, label=label,
                description=description,
            ),
        )  # fmt: skip
    typer.echo(f"app {name}")
    typer.echo(f"id {made.stream_id}")


@apps.command("ls")
def app_ls(
    ctx: typer.Context, project: ProjectOption = None, company: CompanyOption = False
) -> None:
    """List the apps of a scope (every scope when neither option is given): name, on|off, owner,
    label."""
    if project is None and not company:
        sql, params = "SELECT * FROM cur_integration_app ORDER BY name", {}
    else:
        sql = "SELECT * FROM cur_integration_app WHERE scope = :scope ORDER BY name"
        params = {"scope": scope_of(project, company)}
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        found = rows(uow, sql, **params)
    for row in found:
        state = "on" if row["enabled"] else "off"
        typer.echo(line(row["name"], state, row["owner"], row["label"]))


def _app_switch(
    ctx: typer.Context, name: str, project: str | None, company: bool, actor: str, *, on: bool
) -> None:
    admin_gate(ctx)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"app {name}", _APP_SQL, name=name, scope=scope)
        handle_set_app_enabled(
            uow,
            SetIntegrationAppEnabled(
                actor=actor, source=SOURCE, scope=scope, app_id=row["app_id"], enabled=on
            ),
        )
    typer.echo(f"app {name} {'on' if on else 'off'}")


@apps.command("enable")
def app_enable(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The app's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an app on: its endpoints, rules, actions and enrichers may run again."""
    _app_switch(ctx, name, project, company, actor, on=True)


@apps.command("disable")
def app_disable(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The app's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch an app off: its endpoints, rules, actions and enrichers stop at once."""
    _app_switch(ctx, name, project, company, actor, on=False)
