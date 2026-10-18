"""``/dispatch <action> [name=value ...] [text]``: invoke a registered action (FANOUT D10).

The command is ``InvokeAction`` (WS-A, ``tl_core.integration.contract``) with the thread's record
as the target. The text, when there is one, is the parameter ``text`` unless the line names one.
Until the integration layer is merged the runner does not know the command and the planner answers
``dispatch_unavailable``.

STUB: ActionTarget.plan is yours to write (ticket P1-I7-T10a). Remove this paragraph, every STEPS
comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
        # STEPS
        # 1. args = parsed.args; assert isinstance(args, DispatchArgs) (this narrows the
        #    type for pyright).
        # 2. parameters = dict(args.parameters). When args.text is set and the line gave no
        #    parameter named "text", set parameters["text"] = args.text.
        # 3. The action name is args.request_type in lower case.
        # 4. Return a list of one PlannedCommand(command_type="InvokeAction",
        #    command={"action": <name>, "targets": [context.record.id], "parameters":
        #    parameters}, summary="Run action <name> on <record key or id>"). The record key
        #    is context.record.key, else context.record.id.
        raise NotImplementedError
