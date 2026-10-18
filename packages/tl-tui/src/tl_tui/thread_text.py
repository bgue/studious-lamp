"""Display text of a record thread: header, message lines and result cards (P1-I7; brief 21.5,
sketch 13).

Pure functions of what the client returns; no widget, no client. The thread tab shows these lines
and decides nothing. The composer's text (verb completion, the preview panel) is in
`tl_tui.compose_text`.

STUB: header_text, card_lines and message_lines are yours to write (ticket P1-I7-T11a). Remove
this paragraph, every STEPS comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. key = page.record.key or page.record.id.
    # 2. When page.enabled is false return f"{key} · Thread · threads are off for
    #    {page.record.record_type}".
    # 3. n = len(page.participants); state = "on" if page.dispatch_enabled else "off".
    # 4. Return f"{key} · Thread · {n} participant{'' if n == 1 else 's'} · dispatch
    #    {state}" (the dot is the middle dot " · ").
    raise NotImplementedError


def clock(posted_at: str) -> str:
    """``07:02`` from an ISO timestamp."""
    return posted_at[11:16] if len(posted_at) >= 16 else posted_at


def card_lines(outcome: DispatchOutcome) -> list[str]:
    """The result card under a dispatch message: ``▤ <verb>: <summary>`` and one line per command
    that ran (``  CreateRecord P123-REC-0044 v1``)."""
    # STEPS
    # 1. lines = [f"▤ {outcome.verb}: {outcome.summary or 'done'}"].
    # 2. For each item of outcome.results append f"  {item.command_type} {item.key or
    #    item.stream_id} v{item.version}" (two leading spaces).
    # 3. When outcome.link_ids is not empty, n = len(outcome.link_ids): append f"  {n}
    #    dispatched-from link{'' if n == 1 else 's'} added".
    # 4. Return lines.
    raise NotImplementedError


def message_lines(page: ThreadPage) -> list[str]:
    """One block per message: ``07:02 rgarcia  <first line>`` then the rest of the body indented,
    ``(edited)`` after an edited one, ``[retracted]`` for a tombstone, and the result card of a
    dispatch indented under its line. A reminder or summary reads as the system's (its kind)."""
    # STEPS
    # 1. lines = []. For each message and kind of zip(page.messages, page.kinds,
    #    strict=True):
    # 2. who = person(message.author). When message.retracted append
    #    f"{clock(message.posted_at)} {who}  [retracted]" and go on to the next message.
    # 3. body = message.body.splitlines() or [""]. tag = "⏰ " for kind "reminder", "Σ " for
    #    kind "summary", else "". suffix = " (edited)" when message.edited, else "".
    # 4. Append f"{clock(message.posted_at)} {who}  {tag}{body[0]}{suffix}" (two spaces
    #    after who).
    # 5. Append the other lines of body, each with six leading spaces.
    # 6. When message.dispatch is not None append every line of
    #    card_lines(message.dispatch), each with six leading spaces. Return lines.
    raise NotImplementedError
