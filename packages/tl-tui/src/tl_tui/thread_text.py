"""Display text of a record thread: header, message lines and result cards (P1-I7; brief 21.5,
sketch 13).

Pure functions of what the client returns; no widget, no client. The thread tab shows these lines
and decides nothing. The composer's text (verb completion, the preview panel) is in
`tl_tui.compose_text`.
"""

from __future__ import annotations

from tl_core.threads.contract import DispatchOutcome
from tl_core.threads.queries import ThreadPage


def person(actor: str) -> str:
    """``rgarcia`` for ``user:rgarcia``; agents read ``agent:planner ⚙``; others as they are."""
    if actor.startswith("user:"):
        return actor.removeprefix("user:")
    if actor.startswith("agent:"):
        return f"{actor} ⚙"
    return actor


def header_text(page: ThreadPage) -> str:
    """``REC-1 · Thread · 3 participants · dispatch on``; says so when the type has no thread."""
    key = page.record.key or page.record.id
    if not page.enabled:
        return f"{key} · Thread · threads are off for {page.record.record_type}"
    n = len(page.participants)
    state = "on" if page.dispatch_enabled else "off"
    return f"{key} · Thread · {n} participant{'' if n == 1 else 's'} · dispatch {state}"


def clock(posted_at: str) -> str:
    """``07:02`` from an ISO timestamp."""
    return posted_at[11:16] if len(posted_at) >= 16 else posted_at


def card_lines(outcome: DispatchOutcome) -> list[str]:
    """The result card under a dispatch message: ``▤ <verb>: <summary>`` and one line per command
    that ran (``  CreateRecord P123-REC-0044 v1``)."""
    lines = [f"▤ {outcome.verb}: {outcome.summary or 'done'}"]
    for item in outcome.results:
        lines.append(f"  {item.command_type} {item.key or item.stream_id} v{item.version}")
    if outcome.link_ids:
        n = len(outcome.link_ids)
        lines.append(f"  {n} dispatched-from link{'' if n == 1 else 's'} added")
    return lines


def message_lines(page: ThreadPage) -> list[str]:
    """One block per message: ``07:02 rgarcia  <first line>`` then the rest of the body indented,
    ``(edited)`` after an edited one, ``[retracted]`` for a tombstone, and the result card of a
    dispatch indented under its line. A reminder or summary reads as the system's (its kind)."""
    lines: list[str] = []
    for message, kind in zip(page.messages, page.kinds, strict=True):
        who = person(message.author)
        if message.retracted:
            lines.append(f"{clock(message.posted_at)} {who}  [retracted]")
            continue
        body = [ln for ln in message.body.splitlines()] or [""]
        tag = {"reminder": "⏰ ", "summary": "Σ "}.get(kind, "")
        suffix = " (edited)" if message.edited else ""
        lines.append(f"{clock(message.posted_at)} {who}  {tag}{body[0]}{suffix}")
        lines.extend(f"      {ln}" for ln in body[1:])
        if message.dispatch is not None:
            lines.extend(f"      {ln}" for ln in card_lines(message.dispatch))
    return lines
