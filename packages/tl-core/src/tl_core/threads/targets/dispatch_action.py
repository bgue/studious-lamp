"""``/dispatch <action> [name=value ...] [text]``: invoke a registered action (FANOUT D10).

The command is ``InvokeAction`` (WS-A, ``tl_core.integration.contract``) with the thread's record
as the target. The text, when there is one, is the parameter ``text`` unless the line names one.
Until the integration layer is merged the runner does not know the command and the planner answers
``dispatch_unavailable``.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchArgs, DispatchContext, DispatchVerb, ParsedDispatch
from tl_core.uow import UnitOfWork


class ActionTarget:
    verb: DispatchVerb = "dispatch"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        args = parsed.args
        assert isinstance(args, DispatchArgs)
        parameters: dict[str, str] = dict(args.parameters)
        if args.text is not None and "text" not in parameters:
            parameters["text"] = args.text
        action = args.request_type.lower()
        record_label = context.record.key or context.record.id
        return [
            PlannedCommand(
                command_type="InvokeAction",
                command={
                    "action": action,
                    "targets": [context.record.id],
                    "parameters": parameters,
                },
                summary=f"Run action {action} on {record_label}",
            )
        ]
