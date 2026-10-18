"""The deterministic thread summary of ``/summarise`` (ADR-0008 decision 8: no model, no spend).

A pure function of a page of the thread: the same page gives the same text, so the preview token of
a ``/summarise`` stays valid until the thread changes.

STUB: build_summary is yours to write (ticket P1-I7-T10c). Remove this paragraph, every STEPS
comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. people = [p.actor for p in page.participants]. written = the messages m of
    #    page.messages (zip with page.kinds, strict=True) whose kind is "message" and that
    #    are not retracted.
    # 2. lines starts with two lines: "Thread summary (counted by the system, no model)."
    #    and f"Messages: {page.message_count}. Participants: {names}." where names is the
    #    people joined by ", ", or "none" when there are none.
    # 3. dispatched = [m.dispatch for m in page.messages if m.dispatch is not None]. When it
    #    is not empty add "Dispatched:" and then one line "- <verb>: <summary>" per outcome
    #    d (d.summary, or "done" when it is empty).
    # 4. shown = written[-SUMMARY_MAX_MESSAGES:]. When it is not empty add "Last messages:"
    #    and then one line "- <author>: <first line>" per message, using
    #    _first_line(m.body).
    # 5. text = "\n".join(lines). Return it when len(text) <= SUMMARY_MAX_CHARS, else text[:
    #    SUMMARY_MAX_CHARS - 1] + "…".
    raise NotImplementedError
