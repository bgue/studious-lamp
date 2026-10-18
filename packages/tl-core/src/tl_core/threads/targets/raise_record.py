"""``/raise record <title>``: create a ``core.Record`` pre-linked to the thread (FANOUT D10).

The engine adds the ``dispatched_from`` link to the thread's record; this target adds one
``raised_against`` link for each ``#KEY`` target. Modules register their own aliases (``rfi``) under
the same verb.

STUB: RaiseRecordTarget.plan is yours to write (ticket P1-I7-T10b). Remove this paragraph, every
STEPS comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
        # STEPS
        # 1. args = parsed.args; assert isinstance(args, RaiseArgs) (this narrows the type
        #    for pyright). title = (args.text or "").strip().
        # 2. No title: return Problem(code="missing_argument", message="/raise record needs
        #    a title"). Longer than MAX_TITLE_CHARS: return Problem(code="too_long",
        #    message=f"a title is at most {MAX_TITLE_CHARS} characters").
        # 3. refs, problems = resolve_keys(uow, context.scope, args.against). With problems
        #    return first_problem(problems).
        # 4. create = {"record_type": "core.Record", "title": title}; add "description":
        #    args.note when args.note is set.
        # 5. planned = [PlannedCommand(command_type="CreateRecord", command=create,
        #    summary=f"Create record: {title}")].
        # 6. For each ref append PlannedCommand(command_type="AddLink", command={"from_id":
        #    "$result:0", "to_id": ref.id, "relation": "raised_against"}, summary=f"Link the
        #    new record raised against {ref.key}"). The string "$result:0" is written
        #    exactly so: the engine replaces it with the id of the record item 0 creates.
        # 7. Return planned.
        raise NotImplementedError
