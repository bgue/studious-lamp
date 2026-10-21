"""Display text of a record thread: header, message lines and result cards (P1-I7; brief 21.5,
sketch 13).

Pure functions of what the client returns; no widget, no client. The thread tab shows these lines
and decides nothing. The composer's text (verb completion, the preview panel) is in
`tl_tui.compose_text`.

Plain words are the default for the thread tab (P1-UX-T08b): a service reads by its label, an agent
as ``{name} ⚙``, a result card names the command as words and the record key. ``technical=True``
keeps the raw text (``agent:planner ⚙``, ``CreateRecord P123-REC-0044 v1``) for the technical toggle
and for callers that want the stored form.
"""

from __future__ import annotations

from tl_core.threads.contract import DispatchOutcome
from tl_core.threads.queries import ThreadPage

from tl_tui.display import Labels, actor_label, humanize, type_label


def person(actor: str, labels: Labels | None = None, *, technical: bool = True) -> str:
    """``rgarcia`` for ``user:rgarcia``; agents read ``agent:planner ⚙``; others as they are.

    Plain: ``planner ⚙`` for an agent; a ``svc:`` by its label (``a service`` when unknown).
    """
    if actor.startswith("user:"):
        return actor.removeprefix("user:")
    if actor.startswith("agent:"):
        return f"{actor if technical else actor.removeprefix('agent:')} ⚙"
    if actor.startswith("svc:") and not technical:
        return actor_label(labels or Labels(), actor)
    return actor


def header_text(page: ThreadPage, labels: Labels | None = None, *, technical: bool = True) -> str:
    """``REC-1 · Thread · 3 participants · dispatch on``; says so when the type has no thread."""
    if technical:
        key = page.record.key or page.record.id
        type_name = page.record.record_type
    else:
        key = page.record.key or "this record"
        type_name = type_label(labels or Labels(), page.record.record_type)
    if not page.enabled:
        return f"{key} · Thread · threads are off for {type_name}"
    n = len(page.participants)
    state = "on" if page.dispatch_enabled else "off"
    return f"{key} · Thread · {n} participant{'' if n == 1 else 's'} · dispatch {state}"


def clock(posted_at: str) -> str:
    """``07:02`` from an ISO timestamp."""
    return posted_at[11:16] if len(posted_at) >= 16 else posted_at


def card_lines(outcome: DispatchOutcome, *, technical: bool = True) -> list[str]:
    """The result card under a dispatch message: ``▤ <verb>: <summary>`` and one line per command
    that ran (``  CreateRecord P123-REC-0044 v1``).

    Plain: the command as words and the record key (``  Create record P123-REC-0044``), never the
    stream id or the version.
    """
    lines = [f"▤ {outcome.verb}: {outcome.summary or 'done'}"]
    for item in outcome.results:
        if technical:
            lines.append(f"  {item.command_type} {item.key or item.stream_id} v{item.version}")
        else:
            lines.append(f"  {humanize(item.command_type)} {item.key or 'a record'}")
    if outcome.link_ids:
        n = len(outcome.link_ids)
        lines.append(f"  {n} dispatched-from link{'' if n == 1 else 's'} added")
    return lines


def message_lines(
    page: ThreadPage, labels: Labels | None = None, *, technical: bool = True
) -> list[str]:
    """One block per message: ``07:02 rgarcia  <first line>`` then the rest of the body indented,
    ``(edited)`` after an edited one, ``[retracted]`` for a tombstone, and the result card of a
    dispatch indented under its line. A reminder or summary reads as the system's (its kind)."""
    lines: list[str] = []
    for message, kind in zip(page.messages, page.kinds, strict=True):
        who = person(message.author, labels, technical=technical)
        when = clock(message.posted_at)
        if message.retracted:
            lines.append(f"{when} {who}  [retracted]")
            continue
        body = message.body.splitlines() or [""]
        tag = ""
        if kind == "reminder":
            tag = "⏰ "
        elif kind == "summary":
            tag = "Σ "
        suffix = " (edited)" if message.edited else ""
        lines.append(f"{when} {who}  {tag}{body[0]}{suffix}")
        lines.extend(f"      {line}" for line in body[1:])
        if message.dispatch is not None:
            card = card_lines(message.dispatch, technical=technical)
            lines.extend(f"      {line}" for line in card)
    return lines
