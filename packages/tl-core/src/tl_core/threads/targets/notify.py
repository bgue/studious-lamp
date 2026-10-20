"""``/notify @who text``: record mentions; nothing else runs (FANOUT D10).

The message itself carries the mentions (the thread detects them in the body). Inbox delivery
waits for its model. The only check is that every mention is a person or agent that exists.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchContext, DispatchVerb, NotifyArgs, ParsedDispatch
from tl_core.threads.resolve import resolve_mentions
from tl_core.threads.targets import first_problem
from tl_core.uow import UnitOfWork


class NotifyTarget:
    verb: DispatchVerb = "notify"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        args = parsed.args
        assert isinstance(args, NotifyArgs)
        resolved = resolve_mentions(uow, args.who, record_id=context.record.id)
        if resolved.problems:
            return first_problem(resolved.problems)
        return []
