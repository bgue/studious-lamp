"""``/link``: add a link from the thread's record to each key named (FANOUT D10).

STUB: LinkTarget.plan is yours to write (ticket P1-I7-T10a). Remove this paragraph, every STEPS
comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchContext, DispatchVerb, LinkArgs, ParsedDispatch
from tl_core.threads.resolve import resolve_keys
from tl_core.threads.targets import first_problem
from tl_core.uow import UnitOfWork


class LinkTarget:
    verb: DispatchVerb = "link"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        # STEPS
        # 1. args = parsed.args; assert isinstance(args, LinkArgs) (this narrows the type
        #    for pyright).
        # 2. Resolve the keys: refs, problems = resolve_keys(uow, context.scope, args.keys).
        # 3. If problems is not empty return first_problem(problems): one Problem that
        #    carries every message.
        # 4. For each ref build the command dict {"from_id": context.record.id, "to_id":
        #    ref.id}. Add "relation" only when args.relation is set and "note" only when
        #    args.note is set. Never name actor, source, scope, correlation_id, causation_id
        #    or link_source: the server sets those.
        # 5. The summary is "Link <record key>" then " to <ref.key>" with " (<relation>)"
        #    after it when args.relation is set. The record key is context.record.key.
        # 6. Return one PlannedCommand(command_type="AddLink", command=command,
        #    summary=summary) per ref, in order.
        raise NotImplementedError
