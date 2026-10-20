# ruff: noqa: F401, F841
"""``/raise rfi <title>`` from a record thread: a real RFI of the correspondence module (P1-I6 T05).

The core has a placeholder target for ``/raise rfi`` (a labelled ``core.Record``); a module's target
of the same verb and name replaces it (``TargetRegistry.register(..., module=True)``). The module
registers this one under the entry-point group ``throughline.dispatch_targets``.

The target only builds the command; the planner checks the person's access (``RaiseTechnical`` is
any signed-in person's), dry-runs it and shows the preview. The thread engine adds the
``dispatched_from`` link from the new RFI to the thread's record.

STUB (P1-I6-T05b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import (
    DispatchContext,
    DispatchTarget,
    DispatchVerb,
    ParsedDispatch,
    RaiseArgs,
)
from tl_core.threads.resolve import resolve_keys
from tl_core.threads.targets import first_problem
from tl_core.uow import UnitOfWork

from tl_mod_correspondence.limits import MAX_TEXT


def plan_raise_rfi(
    uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
) -> list[PlannedCommand] | Problem:
    """Plan one ``RaiseTechnical`` (subtype ``rfi``) from ``/raise rfi [#KEY ...] <title>``.

    The title is the subject; the lines after the first (``args.note``) are the question, the
    title when there are none. Each ``#KEY`` the line names becomes a reference of the new RFI,
    read as the person dispatching: a key that person may not read is ``unknown_key``, as a key
    no record has. Returns a ``Problem`` (``missing_argument`` for no title, ``too_long`` for a
    title over ``MAX_TEXT`` characters, or the first problem of the keys) instead of a plan.
    """
    # STEPS
    # 1. Read `args = parsed.args` and assert it is a `RaiseArgs`.
    # 2. `title = (args.text or "").strip()`. If it is empty return
    #    `Problem(code="missing_argument", message="/raise rfi needs a title")`.
    # 3. If `len(title) > MAX_TEXT` return `Problem(code="too_long", message=f"a title is
    #    at most {MAX_TEXT} characters")`.
    # 4. `refs, problems = resolve_keys(uow, context.scope, args.against,
    #    actor=context.actor)`. If `problems` is not empty return
    #    `first_problem(problems)`.
    # 5. Build the command dict: `"subtype": "rfi"`, `"subject": title`, `"question":
    #    args.note or title`, and `"references"`: one `{"record_id": ref.id, "note":
    #    "raised against"}` per ref, in order.
    # 6. Return a list with one `PlannedCommand(command_type="RaiseTechnical",
    #    command=command, summary=f"Raise RFI: {title}")`.
    raise NotImplementedError


class RaiseRfiTarget:
    """The module's ``/raise rfi``: replaces the core placeholder of that name."""

    verb: DispatchVerb = "raise"
    name: str = "rfi"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        return plan_raise_rfi(uow, context, parsed)


def targets() -> list[DispatchTarget]:
    """The entry point ``throughline.dispatch_targets`` / ``correspondence``."""
    return [RaiseRfiTarget()]
