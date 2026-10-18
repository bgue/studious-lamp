"""Text of the thread composer: slash-verb completion and the preview panel (P1-I7; brief 21.5,
sketch 13).

Pure functions of what the client returns; no widget, no client. The composer shows these lines and
decides nothing about what a command line means.

STUB: verb_candidates and preview_lines are yours to write (ticket P1-I7-T11b). Remove this
paragraph, every STEPS comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. wanted = prefix.lower() with "summarize" replaced by "summarise".
    # 2. Return [(verb, help) for verb, help in VERB_HELP if verb.startswith(wanted)], in
    #    the order of VERB_HELP.
    raise NotImplementedError


def preview_lines(preview: DispatchPreview) -> list[str]:
    """The preview panel of the composer.

    The command line, then one line per planned command (``1. CreateRecord · user · ok · Create
    record: Clash``; the state is ``ok``, ``not permitted`` or the problem code), the problem
    messages, the notes, and last the question: ``Enter to run, Esc to edit`` when it can be
    dispatched, else ``Cannot be dispatched: Esc to edit``.
    """
    # STEPS
    # 1. lines = [preview.parsed.line].
    # 2. For each planned command (n counts from 1): state = item.problem.code when
    #    item.problem is not None, else "ok" when item.permitted, else "not permitted".
    #    Append f"{n}. {item.command_type} · {item.access or '-'} · {state} ·
    #    {item.summary}".
    # 3. For each planned command with a problem append f"! {item.problem.message}". Then
    #    for each problem of preview.problems append f"! {problem.message}".
    # 4. For each note of preview.notes append f"· {note}".
    # 5. Last append "Enter to run, Esc to edit" when preview.can_dispatch, else "Cannot be
    #    dispatched: Esc to edit". Return lines.
    raise NotImplementedError
