"""`tl agent stop`, `resume` and `stopped`: the per-agent stop switch (P2-X2; ADR-0029 decision 6).

An admin stops one agent so that its new filings and its pending proposals' accepts are refused
(held), and resumes it to lift both. Each command is one call into ``tl_core.services.agent_stop``
as the signed-in admin; the service decides and refuses. ``stopped`` is a read through the viewer
filter. An agent never runs these commands (ADR-0009).
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from pydantic import ValidationError
from tl_core import confidentiality
from tl_core.services.agent_stop import (
    AGENT_PREFIX,
    ResumeAgent,
    StopAgent,
    handle_resume_agent,
    handle_stop_agent,
    list_stopped,
)

from tl_cli.admin import backend_of
from tl_cli.session import fail, require_admin, service_errors

app = typer.Typer(help="Agents: stop, resume, stopped.", no_args_is_help=True)

_Name = Annotated[str, typer.Argument(help="The agent's username (agent:NAME is accepted).")]
_Reason = Annotated[
    str | None, typer.Option("--reason", help="Why (kept in the history, 200 characters).")
]
_Json = Annotated[bool, typer.Option("--json", help="Print a JSON list.")]


def agent_id(name: str) -> str:
    """``triage`` and ``agent:triage`` are the same agent, ``agent:triage``."""
    return name if name.startswith(AGENT_PREFIX) else f"{AGENT_PREFIX}{name}"


@app.command("stop")
def stop(ctx: typer.Context, name: _Name, reason: _Reason = None) -> None:
    """Stop NAME: its new filings are refused and its pending proposals show as held."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    agent = agent_id(name)
    with service_errors():
        try:
            command = StopAgent(actor=admin.actor, source="cli", agent=agent, reason=reason)
        except ValidationError as exc:
            fail(f"invalid agent stop request: {exc.errors()[0]['msg']}")
        with backend() as uow:
            result = handle_stop_agent(uow, command)
    if result.changed:
        typer.echo(f"stopped {agent}")
    else:
        typer.echo(f"already stopped: {agent}")


@app.command("resume")
def resume(ctx: typer.Context, name: _Name) -> None:
    """Resume NAME: lift the stop, so its filings and accepts are allowed again."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    agent = agent_id(name)
    with service_errors():
        with backend() as uow:
            result = handle_resume_agent(
                uow, ResumeAgent(actor=admin.actor, source="cli", agent=agent)
            )
    if result.changed:
        typer.echo(f"resumed {agent}")
    else:
        typer.echo(f"not stopped: {agent}")


@app.command("stopped")
def stopped(ctx: typer.Context, as_json: _Json = False) -> None:
    """List the stopped agents, with the held proposals the viewer may see."""
    require_admin(ctx.obj)
    backend = backend_of(ctx)
    viewer = confidentiality.current_viewer()
    with service_errors(), backend(readonly=True) as uow:
        agents = list_stopped(uow.conn(), viewer)
    if as_json:
        typer.echo(json.dumps([a.model_dump() for a in agents], indent=2))
        return
    if not agents:
        typer.echo("none stopped")
        return
    for a in agents:
        typer.echo(
            f"{a.agent}  since {a.stopped_at or '-'}  by {a.stopped_by or '-'}"
            f"  held {a.held}  {a.reason or '-'}"
        )
