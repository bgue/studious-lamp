"""The dispatch planner: from a command line to a preview (FANOUT D10; ADR-0018).

:class:`ThreadPlanner` implements :class:`~tl_core.threads.contract.DispatchPlanner`. For one record
and one actor it

1. parses the line (``ParseProblem`` is returned as it is);
2. reads the record the way the record route does (a record the caller cannot read is
   ``RecordNotFoundError``) and checks the gate: threads on for the type, dispatch on, the caller's
   role in ``threads.dispatch.roles`` (an agent only proposes: ``threads.agents.can_dispatch``);
3. asks the :class:`~tl_core.threads.targets.TargetRegistry` for the target and lets it build the
   commands;
4. validates each command with the runner's model, sets its ``access`` from the runner (a target
   cannot grant itself anything) and its ``permitted`` from ``holds``: the caller's access, never
   more (ADR-0014 section 8);
5. dry-runs the commands in a unit of work that is rolled back (``factory``), so a refusal of the
   handlers, a failed guard or a missing number shows in the preview;
6. computes the token: the SHA-256 of the canonical JSON of the record id, the record version, the
   command line and the planned commands (type and fields only: who may run them and what the dry
   run said can change between a preview and an acceptance without the plan changing).

``preview`` writes nothing. :func:`confirm_token` is what the confirmation compares.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ValidationError

from tl_core.integration.contract import (
    SERVER_SET_FIELDS,
    Access,
    CommandRunner,
    PlannedCommand,
    Problem,
)
from tl_core.threads.config import (
    agents_can_dispatch,
    dispatch_enabled,
    dispatch_roles,
    role_may_dispatch,
    threads_enabled,
)
from tl_core.threads.contract import (
    MAX_PLANNED_COMMANDS,
    PREVIEW_TTL_S,
    SIDE_EFFECTING_VERBS,
    DispatchContext,
    DispatchParser,
    DispatchPreview,
    ParsedDispatch,
    ParseProblem,
    PlannedLink,
)
from tl_core.threads.effects import EFFECT_MODELS, validate_effect
from tl_core.threads.engine import PlanStepError, execute_plan, server_fields
from tl_core.threads.errors import (
    DispatchDisabledError,
    DispatchForbiddenError,
    ThreadsDisabledError,
)
from tl_core.threads.parser import CommandLineParser
from tl_core.threads.targets import TargetRegistry, load_targets
from tl_core.threads.visibility import ThreadRecord, readable_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

NOT_A_DISPATCH = "not_a_dispatch"
UNAVAILABLE = "dispatch_unavailable"

#: Fields no planned command may carry: the server's (D2) and the two that grant rights a command
#: line must never hold (a workflow role, the "I accept the risk" of a dangerous setting).
NEVER_FORWARDED = SERVER_SET_FIELDS | {"actor_roles", "accept_risk"}


class Factory(Protocol):
    """``factory(readonly=...)`` yields an entered unit of work (every entry point has one)."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


class _DryRun(Exception):
    """Raised at the end of the dry run so its unit of work rolls back."""


@dataclass
class DispatchPlan:
    """A plan the planner made: everything the confirmation needs to run it."""

    record: ThreadRecord
    parsed: ParsedDispatch
    planned: list[PlannedCommand]
    context: DispatchContext
    links: list[PlannedLink] = field(default_factory=list[PlannedLink])
    problems: list[Problem] = field(default_factory=list[Problem])
    notes: list[str] = field(default_factory=list[str])
    token: str = ""

    @property
    def side_effecting(self) -> bool:
        return self.parsed.verb in SIDE_EFFECTING_VERBS

    @property
    def can_dispatch(self) -> bool:
        return not self.problems and all(p.permitted and p.problem is None for p in self.planned)


def token_of(
    record_id: str, record_version: int | None, line: str, planned: list[PlannedCommand]
) -> str:
    """The preview token: SHA-256 of the canonical JSON of the plan (see the module docstring)."""
    body = {
        "record": record_id,
        "version": record_version,
        "line": line,
        "planned": [{"type": p.command_type, "command": p.command} for p in planned],
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _issues(exc: ValidationError) -> str:
    """The messages of a validation error without the values that failed (nothing is echoed)."""
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:300]


def _refusal(exc: Exception) -> Problem:
    cause = exc.cause if isinstance(exc, PlanStepError) else exc
    if isinstance(cause, ValidationError):
        return Problem(code="invalid_command", message=_issues(cause))
    return Problem(code="command_refused", message=f"{type(cause).__name__}: {cause}"[:500])


class ThreadPlanner:
    """The planner. ``factory`` opens the unit of work the dry run rolls back; without it the
    commands are validated and checked for access but not dry-run (a note says so)."""

    def __init__(
        self,
        *,
        parser: DispatchParser | None = None,
        targets: TargetRegistry | None = None,
        factory: Factory | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.parser: DispatchParser = parser or CommandLineParser()
        self.targets = targets or load_targets()
        self._factory = factory
        self._clock = clock

    # --- gate -----------------------------------------------------------------------------

    @staticmethod
    def gate(
        uow: UnitOfWork, record: ThreadRecord, actor: str, holds: Callable[[Access], bool]
    ) -> None:
        """Raise unless ``actor`` may dispatch on this record at all (not what the line asks)."""
        conn = uow.conn()
        if not threads_enabled(conn, record.scope, record.record_type):
            raise ThreadsDisabledError(
                f"threads are not switched on for {record.record_type} records in {record.scope}"
            )
        if not dispatch_enabled(conn, record.scope):
            raise DispatchDisabledError("dispatch from threads is switched off")
        if actor.startswith("agent:"):
            if not agents_can_dispatch(conn, record.scope):
                raise DispatchDisabledError("agents may not propose dispatches here")
            return  # the person who accepts is held to the roles
        if not role_may_dispatch(dispatch_roles(conn, record.scope), holds):
            raise DispatchForbiddenError("your role may not dispatch from threads")

    # --- plan -----------------------------------------------------------------------------

    def plan(
        self,
        uow: UnitOfWork,
        *,
        record_id: str,
        text: str,
        actor: str,
        holds: Callable[[Access], bool],
        runner: CommandRunner,
        dry_run: bool = True,
    ) -> DispatchPlan | ParseProblem:
        if actor.startswith("agent:"):
            dry_run = False  # an agent only proposes: nothing is run as it, even rolled back
        parsed = self.parser.parse(text)
        if parsed is None:
            return ParseProblem(code=NOT_A_DISPATCH, message="the text is a plain message")
        if isinstance(parsed, ParseProblem):
            return parsed
        record = readable_record(uow, record_id, actor=actor)
        self.gate(uow, record, actor, holds)
        now = self._clock()
        context = DispatchContext(
            record=record.ref(),
            record_status=record.status,
            scope=record.scope,
            actor=actor,
            today=now.date().isoformat(),
            now=now.isoformat(),
        )
        plan = DispatchPlan(record=record, parsed=parsed, planned=[], context=context)
        target = self.targets.find(parsed, record.record_type)
        if target is None:
            plan.problems.append(
                Problem(
                    code=UNAVAILABLE, message=f"/{parsed.verb} is not available for this record yet"
                )
            )
            return self._finish(plan)
        built = target.plan(uow, context, parsed)
        if isinstance(built, Problem):
            plan.problems.append(built)
            return self._finish(plan)
        if len(built) > MAX_PLANNED_COMMANDS:
            plan.problems.append(
                Problem(
                    code="too_many_commands", message=f"at most {MAX_PLANNED_COMMANDS} commands"
                )
            )
            built = built[:MAX_PLANNED_COMMANDS]
        plan.planned = [self._check(item, context, holds, runner) for item in built]
        if parsed.verb == "summarise":
            plan.notes.append("the summary is counted by the system: no model, no spend (ADR-0008)")
        if parsed.verb == "notify":
            plan.notes.append("mentions are recorded in the thread; inbox delivery comes later")
        if dry_run and plan.planned and all(p.problem is None for p in plan.planned):
            if self._factory is None:
                plan.notes.append("not dry-run: no way to open a unit of work to roll back")
            else:
                self._dry_run(plan, runner)
        return self._finish(plan)

    def _finish(self, plan: DispatchPlan) -> DispatchPlan:
        plan.token = token_of(plan.record.id, plan.record.version, plan.parsed.line, plan.planned)
        return plan

    def _check(
        self,
        item: PlannedCommand,
        context: DispatchContext,
        holds: Callable[[Access], bool],
        runner: CommandRunner,
    ) -> PlannedCommand:
        """The item with ``access`` and ``permitted`` set by the runner and ``holds``, and a
        ``problem`` when it cannot run as asked."""
        command = dict(item.command)

        def refuse(access: Access | None, problem: Problem) -> PlannedCommand:
            return item.model_copy(
                update={"access": access, "permitted": False, "problem": problem}
            )

        if NEVER_FORWARDED & command.keys():
            return refuse(
                None,
                Problem(
                    code="reserved_field", message="a command names a field only the server sets"
                ),
            )
        if item.command_type in EFFECT_MODELS:
            access: Access | None = "user"
            why = validate_effect(item.command_type, command)
            invalid = None if why is None else Problem(code="invalid_command", message=why)
        else:
            model = runner.model_of(item.command_type)
            if model is None:
                return refuse(
                    None,
                    Problem(code=UNAVAILABLE, message=f"{item.command_type} is not available yet"),
                )
            access = runner.access_of(item.command_type)
            invalid = None
            try:
                fixed = server_fields(context.record.id, context.scope, context.actor, "preview")
                model.model_validate({**command, **fixed})
            except ValidationError as exc:
                invalid = Problem(code="invalid_command", message=_issues(exc))
        if access is None:
            return refuse(
                None,
                Problem(code="no_access", message=f"{item.command_type} has no declared access"),
            )
        permitted = holds(access)
        problem = invalid
        if problem is None and not permitted:
            problem = Problem(
                code="not_permitted", message=f"{item.command_type} needs {access} access"
            )
        return item.model_copy(
            update={"access": access, "permitted": permitted, "problem": problem}
        )

    def _dry_run(self, plan: DispatchPlan, runner: CommandRunner) -> None:
        assert self._factory is not None
        message_id = new_ulid()
        executed = None
        failure: PlanStepError | None = None
        try:
            with self._factory(readonly=False) as write:
                record = readable_record(write, plan.record.id, actor=plan.context.actor)
                try:
                    executed = execute_plan(
                        write,
                        record=record,
                        actor=plan.context.actor,
                        planned=plan.planned,
                        runner=runner,
                        message_id=message_id,
                        causation_id=None,
                        now=self._clock(),
                    )
                except PlanStepError as exc:
                    failure = exc
                raise _DryRun
        except _DryRun:
            pass
        if failure is not None:
            for index, item in enumerate(plan.planned):
                if index == failure.index:
                    plan.planned[index] = item.model_copy(update={"problem": _refusal(failure)})
                elif index > failure.index:
                    plan.planned[index] = item.model_copy(
                        update={
                            "problem": Problem(
                                code="not_checked", message="an earlier item was refused"
                            )
                        }
                    )
        elif executed is not None:
            plan.links = [
                PlannedLink(
                    from_record_id=None,
                    to_record_id=plan.record.id,
                    note="the message that carries this command",
                )
                for step in executed.steps
                if step.created_record
            ]

    # --- the contract's entry point ---------------------------------------------------------

    def preview(
        self,
        uow: UnitOfWork,
        *,
        record_id: str,
        text: str,
        actor: str,
        holds: Callable[[Access], bool],
        runner: CommandRunner,
    ) -> DispatchPreview | ParseProblem:
        """The preview a person sees. An agent has none: it proposes (``build_dispatch_proposal``)."""
        if not actor.startswith("user:"):
            raise DispatchForbiddenError("only a person previews a dispatch; an agent proposes one")
        made = self.plan(
            uow, record_id=record_id, text=text, actor=actor, holds=holds, runner=runner
        )
        if isinstance(made, ParseProblem):
            return made
        return DispatchPreview(
            record=made.context.record,
            parsed=made.parsed,
            planned=made.planned,
            links=made.links,
            side_effecting=made.side_effecting,
            can_dispatch=made.can_dispatch,
            token=made.token,
            expires_at=(self._clock() + timedelta(seconds=PREVIEW_TTL_S)).isoformat(),
            problems=made.problems,
            notes=made.notes,
        )


class PreviewResult(BaseModel):
    """What the preview route and client return: a preview, or the parse problem to show.

    A command line that does not parse is feedback for the composer, not a failed request.
    """

    preview: DispatchPreview | None = None
    problem: ParseProblem | None = None
