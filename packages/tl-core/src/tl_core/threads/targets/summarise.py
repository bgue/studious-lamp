"""``/summarise``: a deterministic summary of the thread, posted by the caller (FANOUT D10).

ADR-0008 decision 8: no model is called and nothing is spent. The text comes from
:func:`tl_core.threads.summary.build_summary`, a pure function of the thread's last messages.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import (
    SUMMARY_MAX_MESSAGES,
    DispatchContext,
    DispatchVerb,
    ParsedDispatch,
)
from tl_core.threads.effects import EFFECT_SUMMARY
from tl_core.threads.queries import read_thread
from tl_core.threads.summary import build_summary
from tl_core.uow import UnitOfWork


class SummariseTarget:
    verb: DispatchVerb = "summarise"
    name: str = "*"

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem:
        page = read_thread(uow, context.record.id, actor=context.actor, limit=SUMMARY_MAX_MESSAGES)
        if not page.messages:
            return Problem(code="empty_thread", message="the thread has no messages to summarise")
        return [
            PlannedCommand(
                command_type=EFFECT_SUMMARY,
                command={"text": build_summary(page)},
                summary="Post a deterministic summary of the thread",
            )
        ]
