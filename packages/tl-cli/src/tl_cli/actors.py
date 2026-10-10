"""Who may run a write command from the shell (P0-I8 decision D3).

An ``agent:<id>`` never changes a setting directly: it proposes and a person accepts. The API
refuses an agent token with 403 ``agent_must_propose``; the CLI trusts its operator's ``--actor``
for everything else, but not for this. ``refuse_agent`` is the callback of the ``--actor`` option of
the ``tl config`` write commands.
"""

from __future__ import annotations

import typer
from tl_api.auth import AGENT_MUST_PROPOSE, AGENT_MUST_PROPOSE_MESSAGE


def refuse_agent(actor: str) -> str:
    """Return ``actor``; for an ``agent:<id>`` print `error: agent_must_propose: ...`, exit 1."""
    if actor.startswith("agent:"):
        typer.echo(f"error: {AGENT_MUST_PROPOSE}: {AGENT_MUST_PROPOSE_MESSAGE}", err=True)
        raise typer.Exit(code=1)
    return actor
