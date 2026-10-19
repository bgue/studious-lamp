"""Text of the thread composer: slash-verb completion and the preview panel (P1-I7; brief 21.5,
sketch 13).

Pure functions of what the client returns; no widget, no client. The composer shows these lines and
decides nothing about what a command line means.
"""

from __future__ import annotations

from tl_core.threads.contract import DispatchPreview

#: Every verb the composer completes after ``/``, with the line shown beside it (sketch 13).
VERB_HELP: tuple[tuple[str, str], ...] = (
    ("assign", "@person|@crew [items]  set an assignee"),
    ("dispatch", "<request-type> [name=value] [text]  run an action"),
    ("due", "<date>  set a due date"),
    ("hold", "[reason]  add a constraint"),
    ("link", "<keys> [as <relation>]  add links"),
    ("notify", "@who [text]  mention people"),
    ("raise", "<type> [#KEY ...] <text>  create a linked record"),
    ("release", "[text]  clear a constraint"),
    ("remind", "<when> [@who] [text]  a reminder"),
    ("status", "<state> [reason]  move along the workflow"),
    ("summarise", "a counted summary of the thread"),
)


def verb_candidates(prefix: str) -> list[tuple[str, str]]:
    """The verbs that start with ``prefix`` (case-insensitive; ``summarize`` counts as
    ``summarise``), in the order of :data:`VERB_HELP`."""
    wanted = prefix.lower().replace("summarize", "summarise")
    return [(verb, help_text) for verb, help_text in VERB_HELP if verb.startswith(wanted)]


def preview_lines(preview: DispatchPreview) -> list[str]:
    """The preview panel of the composer.

    The command line, then one line per planned command (``1. CreateRecord · user · ok · Create
    record: Clash``; the state is ``ok``, ``not permitted`` or the problem code), the problem
    messages, the notes, and last the question: ``Enter to run, Esc to edit`` when it can be
    dispatched, else ``Cannot be dispatched: Esc to edit``.
    """
    lines = [preview.parsed.line]
    for n, item in enumerate(preview.planned, start=1):
        if item.problem is not None:
            state = item.problem.code
        else:
            state = "ok" if item.permitted else "not permitted"
        lines.append(f"{n}. {item.command_type} · {item.access or '-'} · {state} · {item.summary}")
    for item in preview.planned:
        if item.problem is not None:
            lines.append(f"! {item.problem.message}")
    for problem in preview.problems:
        lines.append(f"! {problem.message}")
    for note in preview.notes:
        lines.append(f"· {note}")
    if preview.can_dispatch:
        lines.append("Enter to run, Esc to edit")
    else:
        lines.append("Cannot be dispatched: Esc to edit")
    return lines
