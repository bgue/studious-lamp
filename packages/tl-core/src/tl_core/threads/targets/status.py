"""``/status``: move the thread's record along its workflow (FANOUT D10).

The target is a state (its name or label) or a transition name. Guards apply when the command
runs: the dry run of the preview shows a failed guard as the item's problem.
"""

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
        args = parsed.args
        assert isinstance(args, StatusArgs)
        definition = get_workflows().find(context.record.record_type, context.scope)
        if definition is None:
            return Problem(
                code="no_workflow",
                message=f"no workflow applies to {context.record.record_type} here",
            )
        state = context.record_status or definition.initial_state
        labels = {s.name: (s.label or s.name) for s in definition.states}
        wanted = args.target.strip().lower()
        options = definition.transitions_from(state)
        matching = [
            t
            for t in options
            if wanted in (t.name.lower(), t.to.lower(), labels.get(t.to, t.to).lower())
        ]
        if not matching:
            reachable = sorted({labels.get(t.to, t.to) for t in options})
            reachable_text = ", ".join(reachable) if reachable else "none"
            return Problem(
                code="unknown_state",
                message=(f"from {labels.get(state, state)} the record can go to: {reachable_text}"),
            )
        if len(matching) > 1:
            names = ", ".join(t.name for t in matching)
            return Problem(
                code="ambiguous_transition",
                message=f"several transitions fit; name one: {names}",
            )
        transition = matching[0]
        command: dict[str, object] = {
            "stream_id": context.record.id,
            "expected_version": context.record.version,
            "transition": transition.name,
        }
        if args.text is not None:
            command["reason"] = args.text
        label = labels.get(transition.to, transition.to)
        return [
            PlannedCommand(
                command_type="TransitionWorkflow",
                command=command,
                summary=f"Move {context.record.key or context.record.id} to {label}",
            )
        ]
