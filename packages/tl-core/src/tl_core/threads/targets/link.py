"""``/link``: add a link from the thread's record to each key named (FANOUT D10)."""

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
        args = parsed.args
        assert isinstance(args, LinkArgs)
        refs, problems = resolve_keys(uow, context.scope, args.keys)
        if problems:
            return first_problem(problems)
        planned: list[PlannedCommand] = []
        for ref in refs:
            command: dict[str, object] = {"from_id": context.record.id, "to_id": ref.id}
            if args.relation:
                command["relation"] = args.relation
            if args.note:
                command["note"] = args.note
            how = f" ({args.relation})" if args.relation else ""
            planned.append(
                PlannedCommand(
                    command_type="AddLink",
                    command=command,
                    summary=f"Link {context.record.key or context.record.id} to {ref.key}{how}",
                )
            )
        return planned
