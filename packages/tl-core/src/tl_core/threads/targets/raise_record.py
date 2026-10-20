"""``/raise record <title>``: create a ``core.Record`` pre-linked to the thread (FANOUT D10).

The engine adds the ``dispatched_from`` link to the thread's record; this target adds one
``raised_against`` link for each ``#KEY`` target. Modules register their own aliases under
the same verb; a module's ``rfi`` replaces the core placeholder of that name.
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
    #: Written into the description of the new record when the text gave none.
    lead: str | None = None

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
                code="too_long",
                message=f"a title is at most {MAX_TITLE_CHARS} characters",
            )
        refs, problems = resolve_keys(uow, context.scope, args.against, actor=context.actor)
        if problems:
            return first_problem(problems)
        create: dict[str, object] = {"record_type": "core.Record", "title": title}
        if args.note is not None:
            create["description"] = args.note
        elif self.lead is not None:
            create["description"] = self.lead
        planned = [
            PlannedCommand(
                command_type="CreateRecord",
                command=create,
                summary=f"Create record: {title}",
            )
        ]
        for ref in refs:
            planned.append(
                PlannedCommand(
                    command_type="AddLink",
                    command={
                        "from_id": "$result:0",
                        "to_id": ref.id,
                        "relation": "raised_against",
                    },
                    summary=f"Link the new record raised against {ref.key}",
                )
            )
        return planned


class RaiseRfiTarget(RaiseRecordTarget):
    """``/raise rfi <title>``: until the RFI register of P1-I6 registers its own ``rfi`` target
    (a module's target replaces this placeholder, see ``TargetRegistry.register``), a request for
    information is a ``core.Record`` raised from the thread, labelled as one in its description,
    linked to the thread's record and to each ``#KEY`` it was raised against."""

    name: str = "rfi"
    #: A module's target for the same verb and name replaces this one (and no core target).
    placeholder: bool = True
    lead: str | None = "Request for information raised from a record thread."
