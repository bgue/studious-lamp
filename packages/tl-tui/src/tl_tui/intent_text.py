"""The lines of an event's intent: Why, Next, Toward, Goal (P2-INT-T04, ADR-0025 d7).

Pure text, no widgets. A reference an intent could not show to this reader already arrives as
"not available" (the API and the embedded client redact it); it is shown as is.
"""

from __future__ import annotations

from collections.abc import Mapping

from tl_core.intent import Intent, IntentRef, intent_json


def _name(target: str, names: Mapping[str, str] | None, technical: bool) -> str:
    if technical or names is None:
        return target
    return names.get(target, target)


def _next(item: IntentRef, names: Mapping[str, str] | None, technical: bool) -> str:
    if item.command is not None:
        parts = [item.command]
        if item.target is not None:
            parts.append(_name(item.target, names, technical))
        return " ".join(parts)
    return item.text or ""


def intent_lines(
    intent: Intent | None, *, technical: bool, names: Mapping[str, str] | None = None
) -> list[str]:
    """Why, Next (one per item), Toward, Goal; ``[]`` for no intent or an empty one.

    Plain mode shows ``Label: value`` with record keys for ids (``names``: id -> key); technical
    mode shows the lower-case field names and raw ids, and ``~`` for a condition."""
    if intent is None or intent_json(intent) is None:
        return []

    def label(plain: str, raw: str) -> str:
        return raw if technical else plain

    lines: list[str] = []
    if intent.why:
        lines.append(f"{label('Why', 'why')}: {intent.why}")
    for item in intent.next:
        shown = _next(item, names, technical)
        if shown:
            lines.append(f"{label('Next', 'next')}: {shown}")
    toward = intent.toward
    if toward is not None:
        line = f"{label('Toward', 'toward')}: {_name(toward.target, names, technical)}"
        if toward.state:
            line += f" -> {toward.state}"
        elif toward.condition:
            line += f" {'~' if technical else '->'} {toward.condition}"
        lines.append(line)
    if intent.goal_ref:
        lines.append(f"{label('Goal', 'goal_ref')}: {intent.goal_ref}")
    return lines
