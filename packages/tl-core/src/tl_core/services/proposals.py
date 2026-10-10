"""Proposals: the review queue behind the propose-only MCP tools (brief 11.3, 18.12; FANOUT D4).

An agent never changes a record. A tool call validates the command and records a proposal
(``Proposal.Created``, its own stream ``core.Proposal``); a person accepts or rejects it. Accepting
runs the stored command, in the transaction that appends ``Proposal.Accepted``, as the accepting
person: ``actor`` is the person, ``source`` is ``mcp:<agent>`` and ``causation_id`` is the
``Proposal.Created`` event, so the ledger answers "who did this, on whose suggestion".

Functions, by the unit of work they need:

* ``propose(uow, ...)``, ``accept_proposal(uow, ...)``, ``reject_proposal(uow, ...)`` and
  ``fail_proposal(uow, ...)`` write inside the caller's unit of work and raise the command's own
  refusal unchanged, so the caller's block rolls back.
* ``submit(factory, ...)`` is ``propose`` as the tools use it: the command is first run to the end
  in a unit of work that is rolled back (``precheck``), so a proposal that could never be applied is
  refused at once with the error the handler gives; then it is recorded in a fresh one.
* ``accept_or_fail(factory, ...)`` is ``accept_proposal`` with the failure rule: when the command is
  refused (a stale ``expected_version``, a failed guard) its writes are rolled back and
  ``Proposal.Failed`` is appended in a fresh unit of work. Every caller that accepts for a person
  (CLI, API) uses this one.
* ``get_proposal`` and ``list_proposals`` read ``cur_proposals`` with a connection.

``factory(readonly=...)`` is the call shape every server-side caller already has
(``SqliteUowFactory``, ``PostgresUowFactory``, ``tl_tui.embedded.UowFactory``): it returns a
context manager that yields an entered unit of work.

Not a permission model (human gate, ADR-0005): the only rule here is the meaning of "accept". An
``agent:<id>`` never accepts, rejects or fails a proposal, and an agent cannot claim workflow roles
(``TransitionWorkflow.actor_roles`` is trusted input, so a proposal carries none; the accepting
person supplies them).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError
from sqlalchemy import Connection, text

from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.projection.proposals import PROPOSAL_STREAM_TYPE
from tl_core.proposals.types import (
    AGENT_DAILY_PROPOSALS,
    PROPOSABLE_TOOLS,
    PROPOSAL_ACCEPTED,
    PROPOSAL_CREATED,
    PROPOSAL_FAILED,
    PROPOSAL_REJECTED,
    ProposalStatus,
    ProposalView,
)
from tl_core.services.commands import Command, CommandResult, CreateRecord
from tl_core.services.errors import (
    BudgetExceededError,
    GuardFailedError,
    InvalidProposalError,
    ProposalDeciderError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    RetryableTransactionError,
    ServiceError,
)
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow


class Factory(Protocol):
    """``factory(readonly=...)`` yields an entered unit of work. ``readonly`` may be passed by
    position or by keyword (``SqliteUowFactory``, ``PostgresUowFactory``, ``tl_api.Backend``)."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


Handler = Callable[[UnitOfWork, Any], CommandResult]

BUDGET_ENV = "TL_AGENT_DAILY_PROPOSALS"
MAX_SUMMARY = 300
MAX_REASON = 1000
DEFAULT_SOURCE = "review"  # the Source of the decision events when the caller names none
ROLE_GUARD_KIND = "roles"

_PROPOSER = re.compile(r"(?:agent|user):[A-Za-z0-9][A-Za-z0-9_.@-]*")
_PERSON = re.compile(r"user:[A-Za-z0-9][A-Za-z0-9_.@-]*")

#: command type name -> (model, handler). The keys are the values of ``PROPOSABLE_TOOLS``.
COMMANDS: dict[str, tuple[type[Command], Handler]] = {
    "CreateRecord": (CreateRecord, handle_create_record),
    "SetPsetValues": (SetPsetValues, handle_set_pset_values),
    "AddLink": (AddLink, handle_add_link),
    "TransitionWorkflow": (TransitionWorkflow, handle_transition_workflow),
}

_COLUMNS = (
    "SELECT proposal_id, scope, tool, agent, command_type, command_json, summary, status, "
    "decided_by, reason, result_stream_id, seq, created_event_id, version FROM cur_proposals"
)
_BY_ID_SQL = text(_COLUMNS + " WHERE proposal_id = :proposal_id")
_BUDGET_SQL = text("SELECT COUNT(*) FROM cur_proposals WHERE agent = :agent AND created_day = :day")


class _DryRun(Exception):
    """Raised at the end of ``precheck`` so its unit of work rolls back."""


# --- naming ------------------------------------------------------------------------------------


def source_for(agent: str) -> str:
    """``mcp:<id>`` for ``agent:<id>``: the ``source`` of everything done on the agent's behalf.

    Characters outside the ``source`` alphabet (``@``) become ``_``.
    """
    if _PROPOSER.fullmatch(agent) is None:
        raise InvalidProposalError(f"{agent!r} is not 'agent:<id>' or 'user:<id>'")
    return "mcp:" + re.sub(r"[^A-Za-z0-9_.-]", "_", agent.partition(":")[2])


def daily_budget() -> int:
    """Proposals one agent may create per UTC day: ``TL_AGENT_DAILY_PROPOSALS`` or the default.

    A value that is not a non-negative whole number is ignored. 0 refuses every proposal.
    """
    raw = os.environ.get(BUDGET_ENV, "").strip()
    if raw.isdigit():
        return int(raw)
    return AGENT_DAILY_PROPOSALS


def _require_person(by: str, what: str) -> None:
    if _PERSON.fullmatch(by) is None:
        raise ProposalDeciderError(f"only a person (user:<id>) can {what} a proposal, not {by!r}")


def _day(moment: datetime) -> str:
    return moment.astimezone(UTC).date().isoformat()


# --- reads -------------------------------------------------------------------------------------


def _as_object(value: Any) -> dict[str, Any]:
    loaded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    return dict(loaded) if isinstance(loaded, dict) else {}  # pyright: ignore[reportUnknownArgumentType]


def _view(row: Any) -> ProposalView:
    return ProposalView(
        proposal_id=row.proposal_id,
        scope=row.scope,
        tool=row.tool,
        agent=row.agent,
        command_type=row.command_type,
        command=_as_object(row.command_json),
        summary=row.summary,
        status=row.status,
        decided_by=row.decided_by,
        reason=row.reason,
        result_stream_id=row.result_stream_id,
        seq=row.seq,
    )


def get_proposal(conn: Connection, proposal_id: str, *, scope: str | None = None) -> ProposalView:
    """One proposal. Raises ``ProposalNotFoundError`` for an unknown id, or one of another scope
    when ``scope`` is given."""
    row = conn.execute(_BY_ID_SQL, {"proposal_id": proposal_id}).first()
    if row is None or (scope is not None and row.scope != scope):
        raise ProposalNotFoundError(f"no proposal {proposal_id!r}")
    return _view(row)


def list_proposals(
    conn: Connection,
    scope: str,
    *,
    status: ProposalStatus | None = "pending",
    agent: str | None = None,
    limit: int = 200,
) -> list[ProposalView]:
    """Proposals of ``scope``, oldest first (the review order). ``status`` None lists every
    status; ``agent`` narrows to one proposer. At most ``limit`` (default 200)."""
    clauses = ["scope = :scope"]
    params: dict[str, Any] = {"scope": scope, "limit": limit}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status
    if agent is not None:
        clauses.append("agent = :agent")
        params["agent"] = agent
    sql = f"{_COLUMNS} WHERE {' AND '.join(clauses)} ORDER BY seq ASC LIMIT :limit"
    return [_view(row) for row in conn.execute(text(sql), params).all()]


def proposals_today(conn: Connection, agent: str, *, now: datetime | None = None) -> int:
    """How many proposals ``agent`` has created on the UTC day of ``now`` (default: today)."""
    day = _day(now if now is not None else utcnow())
    return int(conn.execute(_BUDGET_SQL, {"agent": agent, "day": day}).scalar_one())


# --- propose -----------------------------------------------------------------------------------


def _check_proposal(tool: str, agent: str, command: Command, summary: str) -> str:
    command_type = PROPOSABLE_TOOLS.get(tool)
    if command_type is None:
        raise InvalidProposalError(
            f"{tool!r} does not propose changes; the tools that do are "
            f"{', '.join(sorted(PROPOSABLE_TOOLS))}"
        )
    if type(command).__name__ != command_type:
        raise InvalidProposalError(
            f"{tool} carries a {command_type}, not a {type(command).__name__}"
        )
    source_for(agent)  # checks the shape
    clean = summary.strip()
    if not clean or len(clean) > MAX_SUMMARY:
        raise InvalidProposalError(f"summary must be 1 to {MAX_SUMMARY} characters")
    if isinstance(command, TransitionWorkflow) and command.actor_roles:
        raise InvalidProposalError(
            "an agent cannot claim workflow roles; the person who accepts supplies them"
        )
    return clean


def propose(
    uow: UnitOfWork,
    *,
    tool: str,
    agent: str,
    command: Command,
    summary: str,
    now: datetime | None = None,
    budget: int | None = None,
) -> ProposalView:
    """Record ``Proposal.Created`` for ``command`` (nothing else is written).

    Checks, with ``InvalidProposalError``: ``tool`` is in ``PROPOSABLE_TOOLS`` and matches the
    command's type, ``agent`` looks like ``agent:<id>``, the summary has 1 to ``MAX_SUMMARY``
    characters, and a workflow transition claims no roles. Then the budget: the agent may create
    ``budget`` (default ``daily_budget()``) proposals per UTC day of ``now`` (default: today), else
    ``BudgetExceededError``. The count and the append happen in one write transaction, and
    both adapters serialise writers on the ledger (SQLite's write lock, Postgres's advisory lock),
    so simultaneous proposals cannot overshoot it.

    The stored command has ``actor`` = the agent, ``source`` = ``mcp:<id>``, the proposal as its
    correlation and no cause. This function does not run the command; use :func:`submit` to get the
    handler's own refusals at proposal time.
    """
    clean = _check_proposal(tool, agent, command, summary)
    source = source_for(agent)
    limit = budget if budget is not None else daily_budget()
    if proposals_today(uow.conn(), agent, now=now) >= limit:
        raise BudgetExceededError(
            f"{agent} has used its {limit} proposals for today (UTC); try again tomorrow"
        )
    proposal_id = new_ulid()
    stored = command.model_copy(
        update={
            "actor": agent,
            "source": source,
            "correlation_id": proposal_id,
            "causation_id": None,
            "idempotency_key": None,
        }
    )
    uow.append(
        stream_id=proposal_id,
        stream_type=PROPOSAL_STREAM_TYPE,
        scope=command.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=PROPOSAL_CREATED,
                effective_at=now,
                payload={
                    "proposal_id": proposal_id,
                    "tool": tool,
                    "agent": agent,
                    "command_type": type(command).__name__,
                    "command": stored.model_dump(mode="json"),
                    "summary": clean,
                },
            )
        ],
        actor=agent,
        source=source,
        correlation_id=proposal_id,
    )
    return get_proposal(uow.conn(), proposal_id)


def _only_role_guards_failed(exc: GuardFailedError) -> bool:
    failed = [r for r in exc.results if not r.passed]
    return bool(failed) and all(r.kind == ROLE_GUARD_KIND for r in failed)


def precheck(factory: Factory, *, tool: str, command: Command) -> None:
    """Run ``command`` through its handler in a unit of work that is rolled back.

    Raises what the handler raises (``RecordNotFoundError``, ``PsetValidationError``,
    ``ConcurrencyError``, ``GuardFailedError`` ...), so an agent learns at proposal time that a
    change could not be applied now. Nothing is kept: the unit of work ends in an exception, so no
    event is published and a number the allocator took goes back. A transition that is refused only
    by a role guard passes, because the agent has no roles; the accepting person supplies theirs.
    """
    command_type = PROPOSABLE_TOOLS.get(tool)
    if command_type is None or type(command).__name__ != command_type:
        raise InvalidProposalError(f"{tool!r} does not carry a {type(command).__name__}")
    handler = COMMANDS[command_type][1]
    try:
        with factory(readonly=False) as uow:
            try:
                handler(uow, command)
            except GuardFailedError as exc:
                if not _only_role_guards_failed(exc):
                    raise
            raise _DryRun
    except _DryRun:
        return


def submit(
    factory: Factory,
    *,
    tool: str,
    agent: str,
    command: Command,
    summary: str,
    now: datetime | None = None,
    budget: int | None = None,
) -> ProposalView:
    """:func:`precheck` the command, then :func:`propose` it in a fresh unit of work.

    The cheap checks (tool, summary, roles, budget) run first, so an over-budget agent costs no
    dry run. Raises what either step raises.
    """
    _check_proposal(tool, agent, command, summary)
    with factory(readonly=True) as uow:
        limit = budget if budget is not None else daily_budget()
        if proposals_today(uow.conn(), agent, now=now) >= limit:
            raise BudgetExceededError(
                f"{agent} has used its {limit} proposals for today (UTC); try again tomorrow"
            )
    precheck(factory, tool=tool, command=command.model_copy(update={"actor": agent}))
    with factory(readonly=False) as uow:
        return propose(
            uow, tool=tool, agent=agent, command=command, summary=summary, now=now, budget=budget
        )


# --- decide ------------------------------------------------------------------------------------


def _pending(uow: UnitOfWork, proposal_id: str) -> Any:
    row = uow.conn().execute(_BY_ID_SQL, {"proposal_id": proposal_id}).first()
    if row is None:
        raise ProposalNotFoundError(f"no proposal {proposal_id!r}")
    if row.status != "pending":
        raise ProposalNotPendingError(f"proposal {proposal_id} is already {row.status}")
    return row


def _decide(
    uow: UnitOfWork,
    row: Any,
    *,
    event_type: str,
    payload: dict[str, Any],
    by: str,
    source: str,
) -> None:
    uow.append(
        stream_id=row.proposal_id,
        stream_type=PROPOSAL_STREAM_TYPE,
        scope=row.scope,
        expected_version=row.version,
        events=[
            NewEvent(event_type=event_type, payload={"proposal_id": row.proposal_id, **payload})
        ],
        actor=by,
        source=source,
        correlation_id=row.proposal_id,
        causation_id=row.created_event_id,
    )


def accept_proposal(
    uow: UnitOfWork,
    *,
    proposal_id: str,
    by: str,
    roles: Sequence[str] = (),
    source: str = DEFAULT_SOURCE,
) -> ProposalView:
    """Run the stored command as ``by`` and append ``Proposal.Accepted``, in ``uow``.

    ``by`` must be a person (``ProposalDeciderError``); the proposal must be pending
    (``ProposalNotPendingError``). The command runs with ``actor`` = ``by``, ``source`` =
    ``mcp:<agent>``, ``causation_id`` = the ``Proposal.Created`` event and ``correlation_id`` = the
    proposal id. ``roles`` are the workflow roles ``by`` holds, used by a transition (a stub until
    auth exists, brief 8). If the command is refused its error propagates and the caller's block
    rolls back; callers use :func:`accept_or_fail`, which then records ``Proposal.Failed``.
    ``source`` labels the decision event (``cli``, ``api``).
    """
    _require_person(by, "accept")
    row = _pending(uow, proposal_id)
    model, handler = COMMANDS[row.command_type]
    data = _as_object(row.command_json)
    data.update(
        actor=by,
        source=source_for(row.agent),
        correlation_id=proposal_id,
        causation_id=row.created_event_id,
    )
    if model is TransitionWorkflow:
        data["actor_roles"] = list(roles)
    result = handler(uow, model.model_validate(data))
    _decide(
        uow,
        row,
        event_type=PROPOSAL_ACCEPTED,
        payload={"by": by, "result_stream_id": result.stream_id, "result_version": result.version},
        by=by,
        source=source,
    )
    return get_proposal(uow.conn(), proposal_id)


def reject_proposal(
    uow: UnitOfWork, *, proposal_id: str, by: str, reason: str, source: str = DEFAULT_SOURCE
) -> ProposalView:
    """Append ``Proposal.Rejected``. The command never runs. ``reason`` has 1 to ``MAX_REASON``
    characters."""
    _require_person(by, "reject")
    clean = reason.strip()
    if not clean or len(clean) > MAX_REASON:
        raise InvalidProposalError(f"reason must be 1 to {MAX_REASON} characters")
    row = _pending(uow, proposal_id)
    _decide(
        uow,
        row,
        event_type=PROPOSAL_REJECTED,
        payload={"by": by, "reason": clean},
        by=by,
        source=source,
    )
    return get_proposal(uow.conn(), proposal_id)


def fail_proposal(
    uow: UnitOfWork, *, proposal_id: str, by: str, error: str, source: str = DEFAULT_SOURCE
) -> ProposalView:
    """Append ``Proposal.Failed`` for a pending proposal whose command was refused on accept."""
    _require_person(by, "accept")
    row = _pending(uow, proposal_id)
    _decide(
        uow,
        row,
        event_type=PROPOSAL_FAILED,
        payload={"by": by, "error": error[:MAX_REASON]},
        by=by,
        source=source,
    )
    return get_proposal(uow.conn(), proposal_id)


def accept_or_fail(
    factory: Factory,
    *,
    proposal_id: str,
    by: str,
    roles: Sequence[str] = (),
    source: str = DEFAULT_SOURCE,
) -> ProposalView:
    """Accept; if the command is refused, roll it back and record ``Proposal.Failed``.

    Returns the proposal as ``accepted`` or as ``failed`` (the view's ``reason`` is the error).
    Raises, without recording anything, for an unknown or already decided proposal, a decider that
    is not a person, and a transient database failure (``RetryableTransactionError``: running it
    again may work). A second person accepting at the same moment gets
    ``ProposalNotPendingError``.
    """
    try:
        with factory(readonly=False) as uow:
            return accept_proposal(uow, proposal_id=proposal_id, by=by, roles=roles, source=source)
    except (ProposalNotFoundError, ProposalNotPendingError, ProposalDeciderError):
        raise
    except RetryableTransactionError:
        raise
    except (ServiceError, ConcurrencyError, ValidationError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    with factory(readonly=False) as uow:
        _pending(uow, proposal_id)  # decided meanwhile (a race on the proposal stream): not ours
        return fail_proposal(uow, proposal_id=proposal_id, by=by, error=error, source=source)
