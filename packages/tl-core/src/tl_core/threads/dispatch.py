"""Confirming a dispatch: ``DispatchFromThread`` (brief 21.5; FANOUT D10; ADR-0018).

The confirmation runs *exactly what was previewed* and nothing more:

1. an agent is refused (it proposes; a person accepts, and the acceptance runs this same handler
   as the person);
2. the plan is made again as the caller, with the caller's own ``holds`` (never more than the
   caller holds, and never roles taken from a request);
3. its token must equal the one the caller was shown (``dispatch_stale``, 409, otherwise), and
   every planned command must be permitted and free of problems (``dispatch_refused``, 422);
4. in ONE unit of work: the message of kind ``dispatch`` carrying the command line, the planned
   commands through the runner (source ``thread:<record id>``, correlation id
   ``dispatch:<message id>``, the message's event as the cause), the ``dispatched_from`` link from
   each record created to the thread's record, and ``Thread.Dispatched`` with the outcome.

Any refusal raises, so the caller's unit of work rolls back and nothing is kept.
``CommandResult.stream_id`` is the thread stream, ``key`` the message id.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import field_validator

from tl_core.integration.actor_access import require_access
from tl_core.integration.contract import Access, CommandRunner
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.threads.contract import (
    PREVIEW_TTL_S,
    THREAD_DISPATCHED,
    THREAD_STREAM_TYPE,
    DispatchOutcome,
    DispatchResult,
    ParseProblem,
)
from tl_core.threads.engine import PlanStepError, execute_plan
from tl_core.threads.errors import (
    DispatchForbiddenError,
    DispatchRefusedError,
    DispatchStaleError,
    DispatchSyntaxError,
)
from tl_core.threads.messages import post_message, thread_stream_id, thread_version
from tl_core.threads.planner import DispatchPlan, Factory, ThreadPlanner
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

MAX_SUMMARY_CHARS = 500


class DispatchFromThread(Command):
    """Confirm the dispatch of ``text`` on the thread of ``record_id`` as ``actor``.

    ``token`` is the one a preview returned for the same text; ``expires_at`` (optional) is the
    preview's own, and a confirmation after it is stale. Who may run it is decided by the caller's
    access and ``threads.dispatch.roles``, never by a field here.
    """

    record_id: str
    text: str
    token: str
    expires_at: str | None = None

    @field_validator("token")
    @classmethod
    def _token_shape(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("token must be the 64 hex characters a preview returned")
        return value


def parse_expiry(value: str) -> datetime:
    """``value`` as an aware time (a naive one is UTC); ``DispatchStaleError`` if not a time."""
    try:
        found = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DispatchStaleError("the expiry is not a time; preview the command again") from exc
    return found if found.tzinfo is not None else found.replace(tzinfo=UTC)


def _summary(plan: DispatchPlan) -> str:
    verb = plan.parsed.verb
    if verb == "notify":
        args: Any = plan.parsed.args
        return f"Notified {', '.join('@' + w for w in args.who)}"[:MAX_SUMMARY_CHARS]
    line = "; ".join(p.summary for p in plan.planned if p.summary) or verb
    return line[:MAX_SUMMARY_CHARS]


def handle_dispatch_from_thread(
    uow: UnitOfWork,
    cmd: DispatchFromThread,
    *,
    holds: Callable[[Access], bool],
    runner: CommandRunner,
    planner: ThreadPlanner | None = None,
    now: datetime | None = None,
) -> CommandResult:
    """Run the confirmed dispatch in ``uow``.

    ``holds`` and ``runner`` come from the client layer (Python arguments, never request fields).
    Raises ``DispatchForbiddenError`` (an agent, a role), ``DispatchStaleError``,
    ``DispatchRefusedError`` (problems in the plan), ``DispatchSyntaxError`` (not a command line),
    ``ThreadsDisabledError``, ``DispatchDisabledError``, ``RecordNotFoundError`` and whatever a
    planned command's handler raises.
    """
    if not cmd.actor.startswith("user:"):
        raise DispatchForbiddenError("only a person dispatches; an agent proposes a dispatch")
    clock = now or utcnow()
    if cmd.expires_at is not None:
        expiry = parse_expiry(cmd.expires_at)
        # An expiry is a courtesy check (the token is what binds the plan), but it is bounded: a
        # preview never lives longer than its TTL, so a later time is not one a preview gave.
        if expiry < clock:
            raise DispatchStaleError("the preview has expired; preview the command again")
        if expiry > clock + timedelta(seconds=PREVIEW_TTL_S + 60):
            raise DispatchStaleError("the expiry is not one a preview gave; preview again")
    made = (planner or ThreadPlanner()).plan(
        uow,
        record_id=cmd.record_id,
        text=cmd.text,
        actor=cmd.actor,
        holds=holds,
        runner=runner,
        dry_run=False,
    )
    if isinstance(made, ParseProblem):
        raise DispatchSyntaxError(f"{made.code}: {made.message}")
    if not hmac.compare_digest(made.token, cmd.token):
        raise DispatchStaleError("the plan is not the one you previewed; preview it again")
    if not made.can_dispatch:
        raise DispatchRefusedError(*_refusal(made))
    # Whoever confirms needs an account that holds `user`, whatever the plan holds (even `/notify`,
    # which plans no command): the dispatch message is written as them.
    require_access(uow.conn(), cmd.actor, "user", "a dispatch")
    return _run(uow, cmd, made, runner)


def _refusal(plan: DispatchPlan) -> tuple[str, list[dict[str, Any]]]:
    problems = [p.model_dump() for p in plan.problems]
    for item in plan.planned:
        if item.problem is not None:
            problems.append(item.problem.model_dump())
        elif not item.permitted:
            problems.append({"code": "not_permitted", "message": f"{item.command_type}"})
    first = problems[0]["message"] if problems else "the dispatch cannot run"
    return f"cannot dispatch: {first}", problems


def _run(
    uow: UnitOfWork, cmd: DispatchFromThread, plan: DispatchPlan, runner: CommandRunner
) -> CommandResult:
    record = plan.record
    message_id = new_ulid()
    source = f"thread:{record.id}"
    correlation = f"dispatch:{message_id}"
    posted = post_message(
        uow,
        record=record,
        actor=cmd.actor,
        source=source,
        body=cmd.text,
        kind="dispatch",
        message_id=message_id,
        correlation_id=correlation,
    )
    try:
        executed = execute_plan(
            uow,
            record=record,
            actor=cmd.actor,
            planned=plan.planned,
            runner=runner,
            message_id=message_id,
            causation_id=posted.events[0].event_id,
            now=utcnow(),
        )
    except PlanStepError as exc:
        raise exc.cause from exc
    outcome = DispatchOutcome(
        message_id=message_id,
        verb=plan.parsed.verb,
        results=[
            DispatchResult(
                command_type=s.command_type, stream_id=s.stream_id, key=s.key, version=s.version
            )
            for s in executed.steps
        ],
        link_ids=executed.link_ids,
        summary=_summary(plan),
    )
    result = uow.append(
        stream_id=thread_stream_id(record.id),
        stream_type=THREAD_STREAM_TYPE,
        scope=record.scope,
        expected_version=thread_version(uow, record.id),
        events=[
            NewEvent(
                event_type=THREAD_DISPATCHED,
                payload={"record_id": record.id, **outcome.model_dump(mode="json")},
            )
        ],
        actor=cmd.actor,
        source=source,
        correlation_id=correlation,
        causation_id=posted.events[0].event_id,
    )
    return CommandResult(
        stream_id=thread_stream_id(record.id),
        key=message_id,
        version=result.new_version,
        events=[*posted.events, *(e for s in executed.steps for e in s.events), *result.events],
    )


def check_dispatch_proposal(
    factory: Factory, command: DispatchFromThread, *, runner: CommandRunner
) -> None:
    """Plan a proposed dispatch as the proposing agent and refuse one that could never run.

    The agent proposes anything a person could dispatch: every planned command counts as permitted
    (the person who accepts is held to their own access when the plan is made again, and the
    plan must still be the one proposed). A syntax error, a gate, a problem of the plan or a token
    that is not the plan's raises.
    """
    planner = ThreadPlanner(factory=factory)
    with factory(readonly=True) as uow:
        made = planner.plan(
            uow,
            record_id=command.record_id,
            text=command.text,
            actor=command.actor,
            holds=lambda level: True,
            runner=runner,
        )
    if isinstance(made, ParseProblem):
        raise DispatchSyntaxError(f"{made.code}: {made.message}")
    if not made.can_dispatch:
        raise DispatchRefusedError(*_refusal(made))
    if not hmac.compare_digest(made.token, command.token):
        raise DispatchStaleError("the plan changed since you previewed it")


def build_dispatch_proposal(
    factory: Factory,
    *,
    scope: str,
    record_id: str,
    text: str,
    agent: str,
    runner: CommandRunner,
) -> DispatchFromThread:
    """The ``DispatchFromThread`` an agent proposes for ``text``, with the token of its plan.

    Raises what :func:`check_dispatch_proposal` raises (the plan has problems, the gate is shut).
    """
    planner = ThreadPlanner(factory=factory)
    with factory(readonly=True) as uow:
        made = planner.plan(
            uow,
            record_id=record_id,
            text=text,
            actor=agent,
            holds=lambda level: True,
            runner=runner,
        )
    if isinstance(made, ParseProblem):
        raise DispatchSyntaxError(f"{made.code}: {made.message}")
    if not made.can_dispatch:
        raise DispatchRefusedError(*_refusal(made))
    return DispatchFromThread(
        actor=agent, source="mcp", scope=scope, record_id=record_id, text=text, token=made.token
    )
