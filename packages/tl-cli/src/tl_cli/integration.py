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
from tl_core.integration.contract import ACTION_MAX_RESULT_BYTES
from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
from tl_core.integration.inbound.store import configure as configure_inbound_store
from tl_core.integration.inbound.worker import InboundMapJobKind
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.rules.engine import RulesWorker
from tl_core.jobs.runner import JobRunner
from tl_core.webhooks.base import UowFactory
from tl_core.webhooks.transport import HttpxTransport

from tl_cli.integration_support import factory, rows, service_errors

app = typer.Typer(help="Run the integration workers; see their state.", no_args_is_help=True)

IDLE_S = 2.0


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
