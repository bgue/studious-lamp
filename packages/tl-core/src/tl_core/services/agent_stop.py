"""The per-agent stop switch (P2-X2, ADR-0029 decision 6).

An admin stops one agent: ``Agent.Stopped`` goes on the agent's account stream and
``cur_agent_stop`` holds the state. While it stands, ``submit`` and ``propose`` refuse a new
filing and ``accept_proposal`` refuses to accept what the agent filed (the proposal stays
pending, so it reads as held). ``Agent.Resumed`` lifts both. The policy path calls
``is_stopped``, the one stop check; it never copies it.

``StopAgent`` and ``ResumeAgent`` are admin commands, a person's alone (ADR-0009: an agent never
runs them). Stopping a stopped agent, or resuming a running one, appends nothing and answers
``changed: false``, as ``GrantModuleRole`` does for a held role. An agent is known when it has an
agent account and has filed; any other id is refused with one text, so the command is no oracle.

The events carry the agent actor string and an optional short reason, never record text, and they
sit on ``core.Account``, a stream the events API shows to admins only.

Reads (``held_count``, ``list_stopped``) run the viewer filter before they count and before any
LIMIT: a held proposal that carries a record the viewer may not read is neither counted nor named
(ADR-0016). An admin is not clearance.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.auth.errors import AccountNotFoundError, ForbiddenError
from tl_core.auth.module_roles import (
    ALL_MODULES,
    COMPANY,
    effective_roles,
    holder_for_actor,
)
from tl_core.auth.names import check_text
from tl_core.auth.projector import ACCOUNT_STREAM_TYPE, account_stream_id
from tl_core.auth.queries import find_account
from tl_core.ledger import NewEvent
from tl_core.projection.agent_stop import AGENT_RESUMED, AGENT_STOPPED
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

MAX_REASON = 200
AGENT_PREFIX = "agent:"
#: The one refusal of a filing or an accept: no counts, no id.
STOPPED_TEXT = "this agent is stopped"
#: The one refusal for an agent that is not known: unknown, never filed, or not an agent.
UNKNOWN_TEXT = "no such agent"
ADMIN_ONLY_TEXT = "only an admin may stop or resume an agent"


class _AgentStopCommand(Command):
    scope: str = COMPANY
    agent: str = Field(max_length=200)  # ``agent:<name>``


class StopAgent(_AgentStopCommand):
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class ResumeAgent(_AgentStopCommand): ...


class AgentStopResult(CommandResult):
    """A ``CommandResult`` that also says whether anything was written."""

    changed: bool = True


class StoppedAgent(BaseModel):
    agent: str
    stopped_at: str | None
    stopped_by: str | None
    reason: str | None
    held: int


def is_stopped(conn: Connection, agent: str) -> bool:
    """True while ``Agent.Stopped`` has no later ``Agent.Resumed`` for ``agent:<name>``."""
    row = conn.execute(
        text("SELECT stopped FROM cur_agent_stop WHERE agent = :agent"), {"agent": agent}
    ).first()
    return row is not None and int(row[0]) == 1


def require_not_stopped(conn: Connection, agent: str) -> None:
    """Refuse (fixed text, no counts, no id) a filing or an accept for a stopped agent."""
    if is_stopped(conn, agent):
        raise ForbiddenError(STOPPED_TEXT)


# --- commands ----------------------------------------------------------------------------------


def _require_admin_person(conn: Connection, actor: str) -> None:
    # an agent holder never resolves to admin, even one named like an admin (tested)
    holder = holder_for_actor(conn, actor)
    if effective_roles(conn, holder, scope=COMPANY, module=ALL_MODULES).source != "admin":
        raise ForbiddenError(ADMIN_ONLY_TEXT)


def _known(conn: Connection, agent: str) -> tuple[str, int]:
    """``(account id, stream version)`` of a known agent, or ``AccountNotFoundError``."""
    if not agent.startswith(AGENT_PREFIX) or len(agent) == len(AGENT_PREFIX):
        raise AccountNotFoundError(UNKNOWN_TEXT)
    try:
        account = find_account(conn, username=agent[len(AGENT_PREFIX) :])
    except Exception:  # an unusable name is no account
        account = None
    if account is None or account.kind != "agent":
        raise AccountNotFoundError(UNKNOWN_TEXT)
    filed = conn.execute(
        text(
            "SELECT 1 FROM cur_proposals WHERE agent = :a UNION ALL "
            "SELECT 1 FROM cur_agent_stop WHERE agent = :a"
        ),
        {"a": agent},
    ).first()
    if filed is None:
        raise AccountNotFoundError(UNKNOWN_TEXT)
    version = conn.execute(
        text("SELECT version FROM cur_account WHERE account_id = :a"), {"a": account.account_id}
    ).scalar_one()
    return account.account_id, int(version)


def _result(account_id: str, version: int, *, events: list[Any], changed: bool) -> AgentStopResult:
    return AgentStopResult(
        stream_id=account_stream_id(account_id),
        key=None,
        version=version,
        events=events,
        changed=changed,
    )


def _append(
    uow: UnitOfWork, cmd: _AgentStopCommand, account_id: str, version: int, event: NewEvent
) -> AgentStopResult:
    done = uow.append(
        stream_id=account_stream_id(account_id),
        stream_type=ACCOUNT_STREAM_TYPE,
        scope="company",
        expected_version=version,
        events=[event],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return _result(account_id, done.new_version, events=done.events, changed=True)


def handle_stop_agent(uow: UnitOfWork, cmd: StopAgent) -> AgentStopResult:
    conn = uow.conn()
    _require_admin_person(conn, cmd.actor)
    account_id, version = _known(conn, cmd.agent)
    if is_stopped(conn, cmd.agent):
        return _result(account_id, version, events=[], changed=False)
    payload: dict[str, Any] = {"agent": cmd.agent}
    if cmd.reason:
        payload["reason"] = check_text(cmd.reason, what="reason", limit=MAX_REASON)
    return _append(
        uow, cmd, account_id, version, NewEvent(event_type=AGENT_STOPPED, payload=payload)
    )


def handle_resume_agent(uow: UnitOfWork, cmd: ResumeAgent) -> AgentStopResult:
    conn = uow.conn()
    _require_admin_person(conn, cmd.actor)
    account_id, version = _known(conn, cmd.agent)
    if not is_stopped(conn, cmd.agent):
        return _result(account_id, version, events=[], changed=False)
    return _append(
        uow,
        cmd,
        account_id,
        version,
        NewEvent(event_type=AGENT_RESUMED, payload={"agent": cmd.agent}),
    )


# --- reads -------------------------------------------------------------------------------------


def held_count(conn: Connection, agent: str, viewer: confidentiality.Viewer) -> int:
    """Pending proposals of ``agent`` the viewer may read (one with a hidden record is not counted).

    The filter runs over every pending proposal first and the count is taken after it; no LIMIT
    caps the rows that are filtered.
    """
    # lazy: proposals imports this module; one scan of carried ids for both readers
    from tl_core.services.proposals import _carried_ids  # pyright: ignore[reportPrivateUsage]

    rows = conn.execute(
        text(
            "SELECT proposal_id, command_json FROM cur_proposals "
            "WHERE agent = :agent AND status = 'pending'"
        ),
        {"agent": agent},
    ).all()
    carried: dict[str, set[str]] = {}
    every: set[str] = set()
    for row in rows:
        ids: set[str] = set()
        command = row.command_json
        if isinstance(command, str):
            command = json.loads(command)
        _carried_ids(command, ids)
        carried[row.proposal_id] = ids
        every |= ids
    hidden = confidentiality.hidden_among(conn, sorted(every), viewer)
    return sum(1 for ids in carried.values() if not (ids & hidden))


def list_stopped(
    conn: Connection, viewer: confidentiality.Viewer, *, limit: int = 200
) -> list[StoppedAgent]:
    """Agents stopped now, longest stopped first, each with the held count the viewer may see."""
    rows = conn.execute(
        text(
            "SELECT agent, stopped_at, stopped_by, reason FROM cur_agent_stop "
            "WHERE stopped = 1 ORDER BY stopped_at ASC, agent ASC LIMIT :limit"
        ),
        {"limit": limit},
    ).all()
    return [
        StoppedAgent(
            agent=row.agent,
            stopped_at=row.stopped_at,
            stopped_by=row.stopped_by,
            reason=row.reason,
            held=held_count(conn, row.agent, viewer),
        )
        for row in rows
    ]
