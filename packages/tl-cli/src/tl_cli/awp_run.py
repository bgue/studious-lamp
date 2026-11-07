"""`tl awp rollup` and `tl awp worker`: the budget rollup is requested and run from the CLI.

This is P2-I1-T04e. `rollup --project P` queues the rollup of the project through
``RequestRollup``; the handler is idempotent, so a second call queues nothing new and prints the
same line. `worker` runs the awp job queue (D12) until the queue is idle (``--once``) or until
interrupted; it is not project-scoped. Both verbs sit on the ``tl awp`` app itself, with no group.
Mounting ``register`` in ``tl_cli.awp`` is supervisor glue.
"""

from __future__ import annotations

import time
from typing import Annotated

import typer
from tl_adapters.db import DbTarget
from tl_mod_awp.commands import RequestRollup
from tl_mod_awp.worker import build_worker, requeue_orphans

from tl_cli.awp_write import _execute
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    scope_of,
    service_errors,
)


def rollup(
    ctx: typer.Context,
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Queue the budget rollup of the project; prints `rollup requested  job <job id>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        command = RequestRollup(actor=who, source=SOURCE, scope=scope_of(project))
    result = _execute(db, lambda _uow: command)
    typer.echo(f"rollup requested  job {result.stream_id}")


def worker(
    ctx: typer.Context,
    once: Annotated[bool, typer.Option("--once", help="Run what is queued, then exit.")] = False,
    requeue: Annotated[
        bool, typer.Option("--requeue", help="First queue again jobs a restore lost.")
    ] = False,
    idle: Annotated[
        float, typer.Option("--idle", min=0.1, help="Seconds to wait when idle.")
    ] = 2.0,
) -> None:
    """Run the awp job queue.

    Prints `ran <job id> <kind> <outcome>` per job and `worker done: ran=<n>`.

    Without --once it keeps waiting for jobs until interrupted (Ctrl-C ends it cleanly).
    """
    db: DbTarget = ctx.obj
    with service_errors():
        if requeue:
            typer.echo(f"requeued {requeue_orphans(db)}")
        ran = 0
        with build_worker(db) as made:
            try:
                while True:
                    made.follower.poll()  # events -> readiness requests (D13)
                    result = made.runner.run_once()
                    if result is None:
                        if once:
                            break
                        time.sleep(idle)
                        continue
                    typer.echo(f"ran {result.job_id} {result.kind} {result.outcome}")
                    ran += 1
            except KeyboardInterrupt:
                pass
    typer.echo(f"worker done: ran={ran}")


def register(app: typer.Typer) -> None:
    """Add the `rollup` and `worker` verbs to the ``tl awp`` app (no group)."""
    app.command("rollup")(rollup)
    app.command("worker")(worker)
