"""``/dispatch <action> [name=value ...] [text]``: invoke a registered action (FANOUT D10).

The command is ``InvokeAction`` (WS-A, ``tl_core.integration.contract``) with the thread's record
as the target. The text, when there is one, is the parameter ``text`` unless the line names one.
The runner (``tl_api.commands.command_runner``) runs it as the caller: the action's own ``access``
is checked against what the caller holds, so a dispatch never invokes more than the person could
by hand. A line that names no such action is the plan's problem (``command_refused``).
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
