"""``/raise record <title>``: create a ``core.Record`` pre-linked to the thread (FANOUT D10).

The engine adds the ``dispatched_from`` link to the thread's record; this target adds one
``raised_against`` link for each ``#KEY`` target. Modules register their own aliases (``rfi``) under
the same verb.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchContext, DispatchVerb, ParsedDispatch, RaiseArgs
from tl_core.threads.resolve import resolve_keys
from tl_core.threads.targets import first_problem
from tl_core.uow import UnitOfWork

MAX_TITLE_CHARS = 200


class RaiseRecordTarget:
    verb: DispatchVerb = "raise"
    name: str = "record"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        args = parsed.args
        assert isinstance(args, RaiseArgs)
        title = (args.text or "").strip()
        if not title:
            return Problem(code="missing_argument", message="/raise record needs a title")
        if len(title) > MAX_TITLE_CHARS:
            return Problem(
                code="too_long", message=f"a title is at most {MAX_TITLE_CHARS} characters"
            )
        refs, problems = resolve_keys(uow, context.scope, args.against)
        if problems:
            return first_problem(problems)
        create: dict[str, object] = {"record_type": "core.Record", "title": title}
        if args.note:
            create["description"] = args.note
        planned = [
            PlannedCommand(
                command_type="CreateRecord", command=create, summary=f"Create record: {title}"
            )
        ]
        for ref in refs:
            planned.append(
                PlannedCommand(
                    command_type="AddLink",
                    command={"from_id": "$result:0", "to_id": ref.id, "relation": "raised_against"},
                    summary=f"Link the new record raised against {ref.key}",
                )
            )
        return planned
