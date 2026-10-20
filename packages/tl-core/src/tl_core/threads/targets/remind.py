"""``/remind <when> [@who] [text]``: queue a ``thread.reminder`` job (FANOUT D10).

The planned item is the ``ThreadReminder`` effect. ``when`` stays as typed so the preview token is
stable; it is resolved when the dispatch runs. With no mention the reminder is for the person who
set it: the plan names nobody, so the token is the same whoever previews or accepts it, and the
job reads the setter from the message it belongs to.
"""

from __future__ import annotations

from datetime import datetime

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchContext, DispatchVerb, ParsedDispatch, RemindArgs
from tl_core.threads.effects import EFFECT_REMINDER, reminder_problem
from tl_core.threads.resolve import resolve_mentions
from tl_core.threads.targets import first_problem
from tl_core.uow import UnitOfWork


class RemindTarget:
    verb: DispatchVerb = "remind"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        args = parsed.args
        assert isinstance(args, RemindArgs)
        why = reminder_problem(args.when, datetime.fromisoformat(context.now))
        if why is not None:
            return Problem(code="bad_time", message=f"{args.when}: {why}")
        resolved = resolve_mentions(uow, args.who, record_id=context.record.id)
        if resolved.problems:
            return first_problem(resolved.problems)
        who = resolved.found
        command: dict[str, object] = {"when": args.when, "who": who}
        if args.text:
            command["text"] = args.text
        return [
            PlannedCommand(
                command_type=EFFECT_REMINDER,
                command=command,
                summary=f"Remind {', '.join(who) if who else 'you'} at {args.when}",
            )
        ]
