"""The `tl wf` group: show a record's workflow state and run a transition (brief 8).

Each subcommand parses options, makes one call into `tl_core.services.workflow`, and prints. Guards,
roles and state rules live in the service. Roles are a stub list given with `--role` until auth
exists; nothing checks that the caller really holds them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.links.expected import ExpectedLinkError
from tl_core.services.errors import GuardFailedError, ServiceError
from tl_core.services.queries import get_record
from tl_core.services.workflow import (
    TransitionWorkflow,
    handle_transition_workflow,
    workflow_status,
)
from tl_core.workflow.engine import GuardResult
from tl_core.workflow.loader import WorkflowError
from tl_schema.compile import SchemaCompileError
from tl_schema.registry import PackageError

app = typer.Typer(help="Show workflow state and run transitions.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _guard_line(result: GuardResult) -> str:
    return f"  guard {result.kind} {'ok' if result.passed else 'FAILED'} {result.message}"


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, definition or input failure into `error:` on stderr, exit 1.

    A refused transition also lists every guard on stderr, passed or not.
    """
    try:
        yield
    except GuardFailedError as exc:
        typer.echo(f"error: {exc}", err=True)
        for result in exc.results:
            typer.echo(_guard_line(result), err=True)
        raise typer.Exit(code=1) from exc
    except (
        ServiceError,
        ConcurrencyError,
        PackageError,
        SchemaCompileError,
        WorkflowError,
        ExpectedLinkError,
    ) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


@app.command("show")
def show(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    key: Annotated[str, typer.Argument(help="Record key.")],
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="A role the caller holds (a stub until auth); repeatable."),
    ] = None,
) -> None:
    """Show a record's workflow state and, for each transition, whether its guards pass."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = get_record(uow, scope, key)
        if row is None:
            _fail(f"no record with key {key!r} in project {project!r}")
        found = workflow_status(uow, row["id"], roles=tuple(role or ()))
    typer.echo(f"key: {found.key}")
    typer.echo(f"workflow: {found.workflow} v{found.workflow_version}")
    typer.echo(f"state: {found.state}")
    typer.echo(f"entered_at: {found.entered_at}")
    typer.echo(f"version: {found.version}")
    for option in found.options:
        verdict = "allowed" if option.allowed else "blocked"
        typer.echo(f"option {option.transition} -> {option.to_state} {verdict}")
        for result in option.guards:
            typer.echo(_guard_line(result))


@app.command("transition")
def transition(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    key: Annotated[str, typer.Argument(help="Record key.")],
    name: Annotated[str, typer.Argument(help="Transition name, as `tl wf show` lists it.")],
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="A role the caller holds (a stub until auth); repeatable."),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Optional reason.")] = None,
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Run a transition if every guard passes; otherwise list the guards and exit 1."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        current = get_record(uow, scope, key)
        if current is None:
            _fail(f"no record with key {key!r} in project {project!r}")
        result = handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=current["id"],
                expected_version=current["version"],
                transition=name,
                actor_roles=list(role or ()),
                reason=reason,
            ),
        )
    payload = result.events[0].payload
    typer.echo(f"transitioned {key} {payload['from_state']} -> {payload['to_state']}")
    typer.echo(f"version {result.version}")
    typer.echo(f"conformance {payload['conformance']}")
