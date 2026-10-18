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

from tl_core.integration.contract import CommandRunner, InvokeAction
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.modules import module_proposables
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
    SettingProposalInfo,
)
from tl_core.services.commands import Command, CommandResult, CreateRecord, UpdateRecord
from tl_core.services.errors import (
    BudgetExceededError,
    GuardFailedError,
    InvalidProposalError,
    ProposalAccessError,
    ProposalDeciderError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    RetryableTransactionError,
    RiskNotAcceptedError,
    ServiceError,
)
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.links import AddLink, SuggestLink, handle_add_link, handle_suggest_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record, handle_update_record
from tl_core.services.reserved import refuse_reserved
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.settings.layers import parse_layer
from tl_core.settings.registry import get_definition
from tl_core.settings.resolver import value_of
from tl_core.settings.views import get_view
from tl_core.threads.dispatch import (
    DispatchFromThread,
    check_dispatch_proposal,
    handle_dispatch_from_thread,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow


class Factory(Protocol):
    """``factory(readonly=...)`` yields an entered unit of work. ``readonly`` may be passed by
    position or by keyword (``SqliteUowFactory``, ``PostgresUowFactory``, ``tl_api.Backend``)."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


Handler = Callable[[UnitOfWork, Any], CommandResult]


def _dispatch_needs_a_runner(uow: UnitOfWork, cmd: Any) -> CommandResult:
    """The table entry of ``DispatchFromThread``: it runs only through :func:`accept_proposal`."""
    raise ProposalAccessError("a dispatch is accepted with the accepting person's access")


BUDGET_ENV = "TL_AGENT_DAILY_PROPOSALS"
BUDGET_SETTING = "ai.agents.daily_proposals"
MAX_SUMMARY = 300
MAX_REASON = 1000
DEFAULT_SOURCE = "review"  # the Source of the decision events when the caller names none
ROLE_GUARD_KIND = "roles"

_PROPOSER = re.compile(r"(?:agent|user):[A-Za-z0-9][A-Za-z0-9_.@-]*")
#: A rule in ``propose`` mode proposes as ``svc:rule-<slug>`` (P1-I7, ADR-0017); nothing else with
#: the ``svc:`` prefix proposes. Accepting still needs the access of the command (ADR-0014).
_RULE_PROPOSER = re.compile(r"svc:rule-([a-z0-9][a-z0-9_.-]{0,80})")
#: The ``tool`` a rule's proposals carry: it is not an MCP tool and no agent can name it.
RULE_PROPOSAL_TOOL = "rule"
#: The ``tool`` of a proposal that holds an action needing approval (P1-I7): not an MCP tool either.
ACTION_PROPOSAL_TOOL = "action"
_PERSON = re.compile(r"user:[A-Za-z0-9][A-Za-z0-9_.@-]*")

#: command type name -> (model, handler) of the core commands. The keys are the values of
#: ``PROPOSABLE_TOOLS``. Use :func:`command_table` to include the modules' proposable commands.
COMMANDS: dict[str, tuple[type[Command], Handler]] = {
    "CreateRecord": (CreateRecord, handle_create_record),
    "SetPsetValues": (SetPsetValues, handle_set_pset_values),
    "AddLink": (AddLink, handle_add_link),
    "TransitionWorkflow": (TransitionWorkflow, handle_transition_workflow),
    "ChangeSetting": (ChangeSetting, handle_change_setting),
    # P1-I7 WS-B: ``accept_proposal`` runs it with the accepting person's ``holds`` and a runner.
    "DispatchFromThread": (DispatchFromThread, _dispatch_needs_a_runner),
    # P1-I7 WS-A: the commands a rule in ``propose`` mode may carry. No agent tool maps to them
    # (``PROPOSABLE_TOOLS`` is unchanged), so only ``propose_for_rule`` can create such a proposal.
    "UpdateRecord": (UpdateRecord, handle_update_record),
    "SuggestLink": (SuggestLink, handle_suggest_link),
    "PostToFeed": (PostToFeed, handle_post),
    "InvokeAction": (InvokeAction, lambda uow, cmd: _invoke_action(uow, cmd)),
}
#: What a rule may propose: the automation commands whose handler is in this table.
RULE_PROPOSABLE = frozenset(
    {
        "CreateRecord",
        "UpdateRecord",
        "SetPsetValues",
        "AddLink",
        "SuggestLink",
        "TransitionWorkflow",
        "PostToFeed",
        "InvokeAction",
    }
)

#: Who must accept a proposal of each core command: any signed-in person (ADR-0014).
CORE_ACCESS = dict.fromkeys(COMMANDS, "user")


def proposable_tools() -> dict[str, str]:
    """Tool name -> command type: the core tools and the proposable commands of the modules."""
    return {
        **PROPOSABLE_TOOLS,
        **{tool: item.model.__name__ for tool, item in module_proposables().items()},
    }


def command_table() -> dict[str, tuple[type[Command], Handler]]:
    """Command type name -> (model, handler), the core commands and the modules' proposable ones."""
    table = dict(COMMANDS)
    for item in module_proposables().values():
        table[item.model.__name__] = (item.model, item.handler)
    return table


def access_of(command_type: str) -> str | None:
    """What the accepting person must hold for a command type; ``None`` when nothing declares it.

    A command type with no declared access cannot be accepted (fail closed).
    """
    if command_type in CORE_ACCESS:
        return CORE_ACCESS[command_type]
    for item in module_proposables().values():
        if item.model.__name__ == command_type:
            return item.access
    return None


_COLUMNS = (
    "SELECT proposal_id, scope, tool, agent, command_type, command_json, summary, status, "
    "decided_by, reason, result_stream_id, seq, created_event_id, version FROM cur_proposals"
)
_BY_ID_SQL = text(_COLUMNS + " WHERE proposal_id = :proposal_id")
_BUDGET_SQL = text("SELECT COUNT(*) FROM cur_proposals WHERE agent = :agent AND created_day = :day")


class _DryRun(Exception):
    """Raised at the end of ``precheck`` so its unit of work rolls back."""


def _invoke_action(uow: UnitOfWork, cmd: InvokeAction) -> CommandResult:
    """The table's handler for ``InvokeAction``: without ``holds``, so only an action open to any
    signed-in person. ``accept_proposal`` calls the real handler with the accepting person's
    access. (Imported here: the actions service imports this module.)"""
    from tl_core.integration.actions.service import handle_invoke_action

    return handle_invoke_action(uow, cmd)


# --- naming ------------------------------------------------------------------------------------


def source_for(agent: str) -> str:
    """``mcp:<id>`` for ``agent:<id>``: the ``source`` of everything done on the agent's behalf.

    Characters outside the ``source`` alphabet (``@``) become ``_``.
    """
    rule = _RULE_PROPOSER.fullmatch(agent)
    if rule is not None:
        return "rule:" + rule.group(1)  # a reserved source: the server sets it (FANOUT D2)
    if _PROPOSER.fullmatch(agent) is None:
        raise InvalidProposalError(f"{agent!r} is not 'agent:<id>' or 'user:<id>'")
    return "mcp:" + re.sub(r"[^A-Za-z0-9_.-]", "_", agent.partition(":")[2])


def daily_budget(conn: Connection | None = None) -> int:
    """Proposals one agent may create per UTC day.

    ``TL_AGENT_DAILY_PROPOSALS`` wins when it is set to a non-negative whole number (an operator
    or test override; anything else in it is ignored). Otherwise the company-wide setting
    ``ai.agents.daily_proposals`` read on ``conn``, else the platform default (500). 0 refuses
    every proposal.
    """
    raw = os.environ.get(BUDGET_ENV, "").strip()
    if raw.isascii() and raw.isdigit():
        return int(raw)
    if conn is not None:
        return int(value_of(conn, BUDGET_SETTING))
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


def _setting_info(conn: Connection, command: dict[str, Any]) -> SettingProposalInfo:
    """The definition-backed facts about a ``ChangeSetting`` command (see SettingProposalInfo)."""
    key, layer = str(command.get("key", "")), str(command.get("layer", ""))
    reset = bool(command.get("reset", False))
    info = SettingProposalInfo(
        key=key,
        layer=layer,
        owner=layer.partition(":")[2] if layer.startswith("user:") else None,
        proposed_value=None if reset else command.get("value"),
        reset=reset,
    )
    try:
        defn = get_definition(key)
        ref = parse_layer(layer)
        view = get_view(
            conn,
            key,
            project=ref.ident if ref.kind == "project" else None,
            user=ref.ident if ref.kind == "user" else None,
        )
    except ServiceError:
        return info  # the key or layer is gone: risk and effect stay `unknown`
    return info.model_copy(
        update={
            "current_value": view.effective.value,
            "risk": defn.risk,
            "effect": defn.effect,
            "description": defn.description,
        }
    )


def _view(row: Any, conn: Connection | None = None) -> ProposalView:
    command = _as_object(row.command_json)
    setting = (
        _setting_info(conn, command)
        if conn is not None and row.command_type == "ChangeSetting"
        else None
    )
    return ProposalView(
        setting=setting,
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
    return _view(row, conn)


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
    return [_view(row, conn) for row in conn.execute(text(sql), params).all()]


def proposals_today(conn: Connection, agent: str, *, now: datetime | None = None) -> int:
    """How many proposals ``agent`` has created on the UTC day of ``now`` (default: today)."""
    day = _day(now if now is not None else utcnow())
    return int(conn.execute(_BUDGET_SQL, {"agent": agent, "day": day}).scalar_one())


# --- propose -----------------------------------------------------------------------------------


def _check_proposal(tool: str, agent: str, command: Command, summary: str) -> str:
    tools = proposable_tools()
    command_type = tools.get(tool)
    if command_type is None:
        raise InvalidProposalError(
            f"{tool!r} does not propose changes; the tools that do are {', '.join(sorted(tools))}"
        )
    if type(command).__name__ != command_type:
        raise InvalidProposalError(
            f"{tool} carries a {command_type}, not a {type(command).__name__}"
        )
    source_for(agent)  # checks the shape
    refuse_reserved(command)
    clean = summary.strip()
    if not clean or len(clean) > MAX_SUMMARY:
        raise InvalidProposalError(f"summary must be 1 to {MAX_SUMMARY} characters")
    if isinstance(command, TransitionWorkflow) and command.actor_roles:
        raise InvalidProposalError(
            "an agent cannot claim workflow roles; the person who accepts supplies them"
        )
    if isinstance(command, ChangeSetting) and command.accept_risk:
        raise InvalidProposalError(
            "an agent cannot accept a risk; the person who accepts the proposal decides"
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
    limit = budget if budget is not None else daily_budget(uow.conn())
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


def propose_for_rule(
    uow: UnitOfWork,
    *,
    proposer: str,
    command: Command,
    summary: str,
    trigger_event_id: str,
    correlation_id: str,
    now: datetime | None = None,
    budget: int | None = None,
) -> ProposalView:
    """Record ``Proposal.Created`` for one command of a rule in ``propose`` mode (D3, D7).

    ``proposer`` is ``svc:rule-<slug>``, the rule's service actor; ``trigger_event_id`` is the
    event that matched (the proposal's cause, kept in its correlation with ``correlation_id``, the
    triggering event's). The command must be one a rule may propose (``RULE_PROPOSABLE``) and must
    not name a server-set identifier. The proposer has the same daily budget as an agent: a rule
    cannot flood the review queue. Accepting is a person's, with the access of the command
    (``accept_proposal``); the stored command runs as that person with the source ``rule:<slug>``.
    """
    if _RULE_PROPOSER.fullmatch(proposer) is None:
        raise InvalidProposalError(f"{proposer!r} is not 'svc:rule-<slug>'")
    command_type = type(command).__name__
    if command_type not in RULE_PROPOSABLE:
        raise InvalidProposalError(f"a rule cannot propose a {command_type}")
    refuse_reserved(command)
    clean = summary.strip()
    if not clean or len(clean) > MAX_SUMMARY:
        raise InvalidProposalError(f"summary must be 1 to {MAX_SUMMARY} characters")
    if isinstance(command, TransitionWorkflow) and command.actor_roles:
        raise InvalidProposalError(
            "a rule cannot claim workflow roles; the person who accepts supplies them"
        )
    source = source_for(proposer)
    limit = budget if budget is not None else daily_budget(uow.conn())
    if proposals_today(uow.conn(), proposer, now=now) >= limit:
        raise BudgetExceededError(
            f"{proposer} has used its {limit} proposals for today (UTC); try again tomorrow"
        )
    proposal_id = new_ulid()
    stored = command.model_copy(
        update={
            "actor": proposer,
            "source": source,
            "correlation_id": correlation_id,
            "causation_id": trigger_event_id,
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
                    "tool": RULE_PROPOSAL_TOOL,
                    "agent": proposer,
                    "command_type": command_type,
                    "command": stored.model_dump(mode="json"),
                    "summary": clean,
                },
            )
        ],
        actor=proposer,
        source=source,
        correlation_id=correlation_id,
        causation_id=trigger_event_id,
    )
    return get_proposal(uow.conn(), proposal_id)


def propose_action(
    uow: UnitOfWork,
    *,
    proposer: str,
    command: InvokeAction,
    summary: str,
    now: datetime | None = None,
    budget: int | None = None,
) -> ProposalView:
    """Record an action that needs a second person's approval (brief §18.7 ``requires_approval``).

    ``proposer`` is the person who asked (``user:<id>``) or the rule that did. The stored command
    keeps the source it came with; accepting it runs ``InvokeAction`` again as the accepting
    person, who must hold the action's access and must not be the proposer
    (:func:`accept_proposal`). Same daily budget as an agent.
    """
    if _PERSON.fullmatch(proposer) is None and _RULE_PROPOSER.fullmatch(proposer) is None:
        raise InvalidProposalError(f"{proposer!r} is not 'user:<id>' or 'svc:rule-<slug>'")
    refuse_reserved(command)
    clean = summary.strip()
    if not clean or len(clean) > MAX_SUMMARY:
        raise InvalidProposalError(f"summary must be 1 to {MAX_SUMMARY} characters")
    limit = budget if budget is not None else daily_budget(uow.conn())
    if proposals_today(uow.conn(), proposer, now=now) >= limit:
        raise BudgetExceededError(
            f"{proposer} has used its {limit} proposals for today (UTC); try again tomorrow"
        )
    proposal_id = new_ulid()
    stored = command.model_copy(
        update={
            "actor": proposer,
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
                    "tool": ACTION_PROPOSAL_TOOL,
                    "agent": proposer,
                    "command_type": "InvokeAction",
                    "command": stored.model_dump(mode="json"),
                    "summary": clean,
                },
            )
        ],
        actor=proposer,
        source=command.source,
        correlation_id=proposal_id,
    )
    return get_proposal(uow.conn(), proposal_id)


def _only_role_guards_failed(exc: GuardFailedError) -> bool:
    failed = [r for r in exc.results if not r.passed]
    return bool(failed) and all(r.kind == ROLE_GUARD_KIND for r in failed)


def precheck(
    factory: Factory, *, tool: str, command: Command, runner: CommandRunner | None = None
) -> None:
    """Run ``command`` through its handler in a unit of work that is rolled back.

    Raises what the handler raises (``RecordNotFoundError``, ``PsetValidationError``,
    ``ConcurrencyError``, ``GuardFailedError`` ...), so an agent learns at proposal time that a
    change could not be applied now. Nothing is kept: the unit of work ends in an exception, so no
    event is published and a number the allocator took goes back. A transition that is refused only
    by a role guard passes, because the agent has no roles; the accepting person supplies theirs.

    A ``DispatchFromThread`` is not run: it is planned as the agent (``check_dispatch_proposal``),
    which needs ``runner``.
    """
    command_type = proposable_tools().get(tool)
    if command_type is None or type(command).__name__ != command_type:
        raise InvalidProposalError(f"{tool!r} does not carry a {type(command).__name__}")
    if isinstance(command, DispatchFromThread):
        if runner is None:
            raise InvalidProposalError("a dispatch is checked where commands can run")
        check_dispatch_proposal(factory, command, runner=runner)
        return
    handler = command_table()[command_type][1]
    try:
        with factory(readonly=False) as uow:
            try:
                handler(uow, command)
            except GuardFailedError as exc:
                if not _only_role_guards_failed(exc):
                    raise
            except RiskNotAcceptedError:
                pass  # a dangerous setting: the person who accepts supplies "I accept the risk"
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
    runner: CommandRunner | None = None,
) -> ProposalView:
    """:func:`precheck` the command, then :func:`propose` it in a fresh unit of work.

    The cheap checks (tool, summary, roles, budget) run first, so an over-budget agent costs no
    dry run. Raises what either step raises.
    """
    _check_proposal(tool, agent, command, summary)
    with factory(readonly=True) as uow:
        limit = budget if budget is not None else daily_budget(uow.conn())
        if proposals_today(uow.conn(), agent, now=now) >= limit:
            raise BudgetExceededError(
                f"{agent} has used its {limit} proposals for today (UTC); try again tomorrow"
            )
    precheck(factory, tool=tool, command=command.model_copy(update={"actor": agent}), runner=runner)
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


def _require_access(command_type: str, holds: Callable[[str], bool] | None) -> None:
    """Refuse to run a command whose accepting person lacks the access it needs (fail closed).

    ``holds(level)`` says whether the accepting person has ``controller`` or ``admin``; without it
    only ``user`` commands run. A command type nobody declared access for never runs.
    """
    needed = access_of(command_type)
    if needed is None:
        raise ProposalAccessError(
            f"{command_type} has no declared access, so it cannot be accepted"
        )
    if needed != "user" and (holds is None or not holds(needed)):
        raise ProposalAccessError(
            f"accepting a {command_type} proposal needs the {needed} role"
            + (" (admin or document controller)" if needed == "controller" else "")
        )


def accept_proposal(
    uow: UnitOfWork,
    *,
    proposal_id: str,
    by: str,
    roles: Sequence[str] = (),
    accept_risk: bool = False,
    source: str = DEFAULT_SOURCE,
    holds: Callable[[str], bool] | None = None,
    runner: CommandRunner | None = None,
) -> ProposalView:
    """Run the stored command as ``by`` and append ``Proposal.Accepted``, in ``uow``.

    ``by`` must be a person (``ProposalDeciderError``); the proposal must be pending
    (``ProposalNotPendingError``). The command runs with ``actor`` = ``by``, ``source`` =
    ``mcp:<agent>``, ``causation_id`` = the ``Proposal.Created`` event and ``correlation_id`` = the
    proposal id. ``roles`` are the workflow roles ``by`` holds, used by a transition (a stub until
    auth exists, brief 8). ``accept_risk`` is the person's "I accept the risk" for a setting change
    on a ``dangerous`` key (the stored command never carries it). If the command is refused its
    error propagates and the caller's block rolls back; callers use :func:`accept_or_fail`, which
    then records ``Proposal.Failed``. ``source`` labels the decision event (``cli``, ``api``).

    ``holds(level)`` tells whether ``by`` holds the ``controller`` or ``admin`` access a command may
    need (ADR-0014): the command runs as ``by`` and gets no more rights through a proposal than
    ``by`` has. Without it only commands that any signed-in person may run are accepted;
    ``ProposalAccessError`` otherwise, with the proposal still pending.

    A ``DispatchFromThread`` proposal needs ``runner`` (the typed command table, ADR-0018): its
    access depends on its content, so the handler plans the stored command line again as ``by``,
    with ``by``'s ``holds``, and runs it only if every planned command is permitted to ``by`` and
    the plan is the one the agent proposed (the stored token). Otherwise the proposal fails.
    """
    _require_person(by, "accept")
    row = _pending(uow, proposal_id)
    _require_access(row.command_type, holds)
    if row.tool == ACTION_PROPOSAL_TOOL and row.agent == by:
        raise ProposalDeciderError("an action that needs approval is approved by another person")
    model, handler = command_table()[row.command_type]
    data = _as_object(row.command_json)
    data.update(
        actor=by,
        correlation_id=proposal_id,
        causation_id=row.created_event_id,
    )
    if row.tool != ACTION_PROPOSAL_TOOL:
        data["source"] = source_for(row.agent)
    if model is TransitionWorkflow:
        data["actor_roles"] = list(roles)
    if model is ChangeSetting:
        data["accept_risk"] = accept_risk
    command = model.model_validate(data)
    if isinstance(command, DispatchFromThread):
        if runner is None:
            raise ProposalAccessError("a dispatch proposal is accepted where commands can run")
        result = handle_dispatch_from_thread(
            uow,
            command,
            holds=lambda level: level == "user" or (holds is not None and holds(level)),
            runner=runner,
        )
    elif isinstance(command, InvokeAction):
        from tl_core.integration.actions.service import handle_invoke_action
        from tl_core.integration.errors import ActionAccessError

        try:
            result = handle_invoke_action(
                uow, command, holds=holds, proposal_id=proposal_id, invoked_by=row.agent
            )
        except ActionAccessError as exc:  # the proposal stays pending; it is not a failure of it
            raise ProposalAccessError(str(exc)) from exc
    else:
        result = handler(uow, command)
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
    accept_risk: bool = False,
    source: str = DEFAULT_SOURCE,
    holds: Callable[[str], bool] | None = None,
    runner: CommandRunner | None = None,
) -> ProposalView:
    """Accept; if the command is refused, roll it back and record ``Proposal.Failed``.

    Returns the proposal as ``accepted`` or as ``failed`` (the view's ``reason`` is the error).
    Raises, without recording anything, for an unknown or already decided proposal, a decider that
    is not a person, a change to a ``dangerous`` setting without ``accept_risk``
    (``RiskNotAcceptedError``: the proposal stays pending, so the person can accept again after
    reading what it changes), and a transient database failure (``RetryableTransactionError``:
    running it again may work). A second person accepting at the same moment gets
    ``ProposalNotPendingError``.
    """
    try:
        with factory(readonly=False) as uow:
            return accept_proposal(
                uow,
                proposal_id=proposal_id,
                by=by,
                roles=roles,
                accept_risk=accept_risk,
                source=source,
                holds=holds,
                runner=runner,
            )
    except (
        ProposalNotFoundError,
        ProposalNotPendingError,
        ProposalDeciderError,
        ProposalAccessError,
    ):
        raise
    except RiskNotAcceptedError:
        raise  # the person has not confirmed the risk yet: the proposal stays pending
    except RetryableTransactionError:
        raise
    except (ServiceError, ConcurrencyError, ValidationError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    with factory(readonly=False) as uow:
        _pending(uow, proposal_id)  # decided meanwhile (a race on the proposal stream): not ours
        return fail_proposal(uow, proposal_id=proposal_id, by=by, error=error, source=source)
