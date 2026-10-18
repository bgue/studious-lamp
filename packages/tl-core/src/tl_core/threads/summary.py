"""The deterministic thread summary of ``/summarise`` (ADR-0008 decision 8: no model, no spend).

A pure function of a page of the thread: the same page gives the same text, so the preview token of
a ``/summarise`` stays valid until the thread changes.
"""

from __future__ import annotations

from tl_core.threads.contract import SUMMARY_MAX_CHARS, SUMMARY_MAX_MESSAGES
from tl_core.threads.queries import ThreadPage

LINE_CHARS = 100


def _first_line(body: str) -> str:
    line = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    return line if len(line) <= LINE_CHARS else line[: LINE_CHARS - 1] + "…"


def build_summary(page: ThreadPage) -> str:
    """The summary text of ``page`` (oldest message first), at most ``SUMMARY_MAX_CHARS``.

    Lines, in order: a heading that says no model wrote it; the counts of messages and the
    participants; the commands that were dispatched (verb and result line); then the first line of
    each of the last ``SUMMARY_MAX_MESSAGES`` messages that a person wrote (retracted, summary and
    reminder messages are left out). A text over the limit is cut and ends with an ellipsis.
    """
    people = [p.actor for p in page.participants]
    written = [
        m
        for m, kind in zip(page.messages, page.kinds, strict=True)
        if kind == "message" and not m.retracted
    ]
    names = ", ".join(people) if people else "none"
    lines = [
        "Thread summary (counted by the system, no model).",
        f"Messages: {page.message_count}. Participants: {names}.",
    ]
    dispatched = [m.dispatch for m in page.messages if m.dispatch is not None]
    if dispatched:
        lines.append("Dispatched:")
        lines.extend(f"- {d.verb}: {d.summary or 'done'}" for d in dispatched)
    shown = written[-SUMMARY_MAX_MESSAGES:]
    if shown:
        lines.append("Last messages:")
        lines.extend(f"- {m.author}: {_first_line(m.body)}" for m in shown)
    text = "\n".join(lines)
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    return text[: SUMMARY_MAX_CHARS - 1] + "…"
