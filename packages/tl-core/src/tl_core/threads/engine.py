"""Running a plan: the one place that executes planned commands (FANOUT D10).

:func:`execute_plan` runs a list of :class:`~tl_core.integration.contract.PlannedCommand` items in
the unit of work it is given, as the caller, with the server-set identifiers of a dispatch: the
source ``thread:<record id>``, the correlation id ``dispatch:<message id>`` and the dispatch
message's event as the cause. The planner calls it inside a unit of work it rolls back (the
preview's dry run); the confirmation calls it inside the unit of work that commits. It is the
same code, so a preview shows what the run will do.

Between items, the exact string ``"$result:<n>"`` anywhere in a command is replaced by the stream
id item ``n`` produced (``n`` must be an earlier item): that is how ``/raise`` links the record it
creates. After an item that created a record, the engine adds the ``dispatched_from`` link from that
record to the thread's record (link source ``thread_dispatch``, the message id as the note).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tl_core.integration.actor_access import require_access
from tl_core.integration.contract import CommandRunner, PlannedCommand
from tl_core.services.links import AddLink, handle_add_link
from tl_core.threads.effects import EFFECT_MODELS, StepResult, run_effect
from tl_core.threads.visibility import ThreadRecord
from tl_core.uow import UnitOfWork

_RESULT_REF = re.compile(r"\$result:(\d{1,3})")


class PlanStepError(Exception):
    """Item ``index`` of a plan was refused; ``cause`` is what the handler raised."""

    def __init__(self, index: int, cause: Exception) -> None:
        super().__init__(str(cause))
        self.index = index
        self.cause = cause


@dataclass(frozen=True)
class Executed:
    steps: list[StepResult]
    link_ids: list[str]


def substitute(value: Any, results: list[StepResult]) -> Any:
    """``value`` with every ``"$result:<n>"`` string replaced by item ``n``'s stream id.

    Raises ``ValueError`` for a reference to an item that has not run.
    """
    if isinstance(value, str):
        found = _RESULT_REF.fullmatch(value)
        if found is None:
            return value
        index = int(found.group(1))
        if index >= len(results):
            raise ValueError(f"{value} refers to an item that has not run")
        return results[index].stream_id
    if isinstance(value, dict):
        return {k: substitute(v, results) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [substitute(v, results) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def server_fields(record_id: str, scope: str, actor: str, message_id: str) -> dict[str, Any]:
    """What the server sets on every command of a dispatch; a target never names these."""
    return {
        "actor": actor,
        "source": f"thread:{record_id}",
        "scope": scope,
        "correlation_id": f"dispatch:{message_id}",
    }


def execute_plan(
    uow: UnitOfWork,
    *,
    record: ThreadRecord,
    actor: str,
    planned: list[PlannedCommand],
    runner: CommandRunner,
    message_id: str,
    causation_id: str | None,
    now: datetime,
) -> Executed:
    """Run every item in order. Raises :class:`PlanStepError` at the first refusal; the caller's
    unit of work then rolls back (the dry run always does)."""
    steps: list[StepResult] = []
    link_ids: list[str] = []
    fixed = {
        **server_fields(record.id, record.scope, actor, message_id),
        "causation_id": causation_id,
    }
    for index, item in enumerate(planned):
        try:
            data = substitute(item.command, steps)
            if item.command_type in EFFECT_MODELS:
                # An effect is not a table command, so the runner does not check who runs it:
                # the actor needs an account that holds `user` (M2).
                require_access(uow.conn(), actor, "user", item.command_type)
                step = run_effect(
                    uow,
                    record=record,
                    actor=actor,
                    command_type=item.command_type,
                    data=data,
                    message_id=message_id,
                    now=now,
                )
            else:
                model = runner.model_of(item.command_type)
                if model is None:
                    raise ValueError(f"unknown command {item.command_type}")
                result = runner.run(uow, model.model_validate({**data, **fixed}))
                step = StepResult(
                    item.command_type,
                    result.stream_id,
                    result.key,
                    result.version,
                    created_record=any(
                        e.event_type == "Record.Created" and e.stream_id == result.stream_id
                        for e in result.events
                    ),
                    events=list(result.events),
                )
            steps.append(step)
            if step.created_record:
                link = handle_add_link(
                    uow,
                    AddLink(
                        actor=actor,
                        source=f"thread:{record.id}",
                        scope=record.scope,
                        correlation_id=f"dispatch:{message_id}",
                        causation_id=causation_id,
                        from_id=step.stream_id,
                        to_id=record.id,
                        relation="dispatched_from",
                        link_source="thread_dispatch",
                        note=message_id,
                    ),
                    system_source="thread_dispatch",  # the narrow form: this link source only
                )
                link_ids.append(link.stream_id)
        except Exception as exc:
            raise PlanStepError(index, exc) from exc
    return Executed(steps, link_ids)
