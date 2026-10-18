"""``/status``: move the thread's record along its workflow (FANOUT D10).

The target is a state (its name or label) or a transition name. Guards apply when the command
runs: the dry run of the preview shows a failed guard as the item's problem.

STUB: StatusTarget.plan is yours to write (ticket P1-I7-T10b). Remove this paragraph, every STEPS
comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchContext, DispatchVerb, ParsedDispatch, StatusArgs
from tl_core.uow import UnitOfWork
from tl_core.workflow.provider import get_workflows


class StatusTarget:
    verb: DispatchVerb = "status"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        # STEPS
        # 1. args = parsed.args; assert isinstance(args, StatusArgs) (this narrows the type
        #    for pyright).
        # 2. definition = get_workflows().find(context.record.record_type, context.scope).
        #    None: return Problem(code="no_workflow", message=f"no workflow applies to
        #    {context.record.record_type} here").
        # 3. state = context.record_status or definition.initial_state. labels = {s.name:
        #    (s.label or s.name) for s in definition.states}. wanted =
        #    args.target.strip().lower().
        # 4. options = definition.transitions_from(state). matching = the transitions t of
        #    options with wanted in (t.name.lower(), t.to.lower(), labels.get(t.to,
        #    t.to).lower()).
        # 5. No match: reachable = the sorted labels of the states the options lead to,
        #    joined by ", " ("none" when there are no options). Return
        #    Problem(code="unknown_state", message=f"from {labels.get(state, state)} the
        #    record can go to: {reachable}").
        # 6. More than one match: return Problem(code="ambiguous_transition",
        #    message=f"several transitions fit; name one: {names}") with the transition
        #    names joined by ", ".
        # 7. One match: command = {"stream_id": context.record.id, "expected_version":
        #    context.record.version, "transition": transition.name}; add "reason": args.text
        #    when args.text is set. Never name actor_roles or any server-set field.
        # 8. Return a list of one PlannedCommand(command_type="TransitionWorkflow",
        #    command=command, summary=f"Move {record key or id} to {label of the target
        #    state}").
        raise NotImplementedError
