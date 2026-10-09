"""Workflow commands and queries: ``TransitionWorkflow`` and ``workflow_status`` (brief 8).

A transition is one ``Workflow.Transitioned`` event on the record's own stream, appended only when
every guard of the transition passes. A record whose ``status`` is null is in the definition's
``initial_state``; creating a record emits no transition.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    GuardFailedError,
    InvalidStateError,
    NoWorkflowError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownTransitionError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow
from tl_core.workflow.definition import WorkflowDefinition
from tl_core.workflow.engine import GuardResult, RecordFacts, conformance_in_state, evaluate_guards
from tl_core.workflow.provider import get_workflows

_RECORD_SQL = text(
    "SELECT id, key, type, scope, status, psets_json, voided, version, created_at "
    "FROM cur_core_record WHERE id = :id"
)
_STATE_SQL = text("SELECT entered_at FROM cur_workflow_state WHERE record_id = :id")


class TransitionWorkflow(Command):
    stream_id: str
    expected_version: int
    transition: str
    # Roles the caller holds. A stub until auth exists (brief 8): the list is taken on trust.
    actor_roles: list[str] = []
    reason: str | None = None


class TransitionOption(BaseModel):
    transition: str
    label: str
    from_state: str
    to_state: str
    allowed: bool
    guards: list[GuardResult]


class WorkflowStatus(BaseModel):
    record_id: str
    key: str | None
    workflow: str
    workflow_version: int
    state: str
    state_label: str
    entered_at: str  # when the record entered the state (``state_entered_at``)
    version: int  # the record's stream version, for ``TransitionWorkflow.expected_version``
    options: list[TransitionOption]


def _load(uow: UnitOfWork, record_id: str, scope: str | None = None) -> Any:
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or (scope is not None and row.scope != scope):
        raise RecordNotFoundError(f"no record {record_id!r}")
    return row


def _facts(row: Any) -> RecordFacts:
    return RecordFacts(
        id=row.id,
        key=row.key,
        type=row.type,
        scope=row.scope,
        psets=json.loads(row.psets_json),
    )


def _definition(row: Any, record_label: str) -> WorkflowDefinition:
    definition = get_workflows().find(row.type, row.scope)
    if definition is None:
        raise NoWorkflowError(f"no workflow applies to {record_label} ({row.type} in {row.scope})")
    return definition


def _current_state(row: Any, definition: WorkflowDefinition) -> str:
    state: str = row.status or definition.initial_state
    if state not in definition.state_names():
        raise InvalidStateError(
            f"record {row.key or row.id} is in state {state!r}, which workflow "
            f"{definition.id} v{definition.version} does not define"
        )
    return state


def workflow_status(
    uow: UnitOfWork, record_id: str, *, roles: tuple[str, ...] = ()
) -> WorkflowStatus:
    """The record's state and every transition that starts there, each with its guard results.

    Raises ``RecordNotFoundError``, ``NoWorkflowError`` or ``InvalidStateError``. The guard
    results are the same ones ``TransitionWorkflow`` would act on, so a client can show why an
    action is blocked before the user tries it.
    """
    row = _load(uow, record_id)
    definition = _definition(row, f"record {row.key or record_id}")
    state = _current_state(row, definition)
    facts = _facts(row)
    today = utcnow().date()
    options: list[TransitionOption] = []
    for transition in definition.transitions_from(state):
        guards = evaluate_guards(uow, facts, transition, roles=roles, today=today)
        options.append(
            TransitionOption(
                transition=transition.name,
                label=transition.label or transition.name,
                from_state=state,
                to_state=transition.to,
                allowed=all(g.passed for g in guards),
                guards=guards,
            )
        )
    entered = uow.conn().execute(_STATE_SQL, {"id": record_id}).first()
    labels = {s.name: s.label or s.name for s in definition.states}
    return WorkflowStatus(
        record_id=record_id,
        key=row.key,
        workflow=definition.id,
        workflow_version=definition.version,
        state=state,
        state_label=labels[state],
        entered_at=entered.entered_at if entered is not None else row.created_at,
        version=row.version,
        options=options,
    )


def handle_transition_workflow(uow: UnitOfWork, cmd: TransitionWorkflow) -> CommandResult:
    """Run one transition if its guards pass; otherwise raise and write nothing.

    Raises ``RecordNotFoundError``, ``RecordVoidedError``, ``NoWorkflowError``,
    ``InvalidStateError``, ``UnknownTransitionError`` (no such transition, or not from the current
    state) and ``GuardFailedError`` (its ``results`` list every guard, passed or not).
    """
    row = _load(uow, cmd.stream_id, cmd.scope)
    if row.voided:
        raise RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot change state")
    definition = _definition(row, f"record {row.key or cmd.stream_id}")
    state = _current_state(row, definition)

    transition = definition.transition(cmd.transition)
    if transition is None:
        available = ", ".join(t.name for t in definition.transitions_from(state)) or "none"
        raise UnknownTransitionError(
            f"workflow {definition.id} has no transition {cmd.transition!r} "
            f"(from {state}: {available})"
        )
    if state not in transition.from_states:
        available = ", ".join(t.name for t in definition.transitions_from(state)) or "none"
        raise UnknownTransitionError(
            f"transition {cmd.transition!r} cannot start in state {state!r} (from {state}: "
            f"{available})"
        )

    facts = _facts(row)
    today = utcnow().date()
    results = evaluate_guards(uow, facts, transition, roles=cmd.actor_roles, today=today)
    failed = [r for r in results if not r.passed]
    if failed:
        raise GuardFailedError(
            f"cannot {cmd.transition} {row.key or cmd.stream_id}: "
            + "; ".join(f"{r.kind}: {r.message}" for r in failed),
            list(results),
        )

    status, schema_hash, _issues = conformance_in_state(facts, transition.to, today)
    result = uow.append(
        stream_id=cmd.stream_id,
        stream_type=row.type,
        scope=cmd.scope,
        expected_version=cmd.expected_version,
        events=[
            NewEvent(
                event_type="Workflow.Transitioned",
                payload={
                    "workflow": definition.id,
                    "workflow_version": definition.version,
                    "from_state": state,
                    "to_state": transition.to,
                    "transition": transition.name,
                    "guards_evaluated": [
                        {"kind": r.kind, "passed": r.passed, "message": r.message} for r in results
                    ],
                    "signature": None,
                    "reason": cmd.reason,
                    "conformance": status,
                    "effective_schema_hash": schema_hash,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.stream_id, key=row.key, version=result.new_version, events=result.events
    )
