"""Tool modes: Phase 0 has exactly one, ``propose``; asking for ``write`` is refused (human gate).

Who may change a record directly, and per-role tool permissions, belong to the permission model,
which is a human gate (build spec 04 §2, ADR-0005, FANOUT decision D4). Nothing here decides it:
the only mode is ``propose``, and a request for any other fails loudly so nobody believes a tool
was switched.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import get_args

from tl_core.proposals.types import PROPOSABLE_TOOLS, ToolMode

HUMAN_GATE_MESSAGE = (
    "tool mode 'write' is not available: deciding who may change records directly is part of the "
    "permission model, which is a human gate (ADR-0005, build spec 04-gates section 2). In "
    "Phase 0 record-changing tools only propose; a person accepts proposals with "
    "`tl proposal accept`."
)
DIRECT_TOOLS = frozenset({"post_feed"})
MODES: tuple[str, ...] = get_args(ToolMode)


class ToolModeError(ValueError):
    """A tool was asked to run in a mode that does not exist or is behind a human gate."""


def resolve_tool_modes(requested: Mapping[str, str] | None = None) -> dict[str, ToolMode]:
    """The mode of every record-changing tool, after checking ``requested`` (tool -> mode).

    ``propose`` is accepted (and is the default). ``write`` raises ``ToolModeError`` with
    ``HUMAN_GATE_MESSAGE``; so does an unknown mode, an unknown tool, and ``post_feed``, which has
    no mode: it always writes directly and is labelled with the agent.
    """
    modes: dict[str, ToolMode] = {tool: "propose" for tool in PROPOSABLE_TOOLS}
    for tool, mode in (requested or {}).items():
        if tool in DIRECT_TOOLS:
            raise ToolModeError(
                f"{tool} has no mode: it always writes directly, labelled with the agent"
            )
        if tool not in PROPOSABLE_TOOLS:
            known = ", ".join(sorted(PROPOSABLE_TOOLS))
            raise ToolModeError(f"{tool!r} is not a record-changing tool (modes apply to: {known})")
        if mode == "write":
            raise ToolModeError(HUMAN_GATE_MESSAGE)
        if mode != "propose":
            raise ToolModeError(f"unknown tool mode {mode!r}; the only mode is {MODES[0]!r}")
    return modes
