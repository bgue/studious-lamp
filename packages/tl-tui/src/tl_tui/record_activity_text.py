"""Activity text (P2-INS): table columns and cells of the record's Activity tab.

Pure functions: no client call, no I/O, no ``textual`` import. The signatures are frozen; the
bodies are the plain placeholders T02 (the tab) is built against, and T01 replaces them.
"""

from __future__ import annotations

import re

from tl_core.insights.types import ActivityRow

from tl_tui.display import Labels, actor_label
from tl_tui.record_text import event_label, event_summary, history_cells
from tl_tui.text import EMPTY, timestamp

KIND_WORDS: dict[str, str] = {
    "change": "Change",
    "move": "Move",
    "link": "Link",
    "file": "File",
    "post": "Post",
    "proposal": "Proposal",
    "constraint": "Constraint",
    "check": "Check run",
}
PROPOSAL_WORDS: dict[str, str] = {
    "Proposal.Created": "Proposal filed",
    "Proposal.Accepted": "Proposal accepted",
    "Proposal.Rejected": "Proposal rejected",
}
DECIDED_WORDS: dict[str, str] = {"Proposal.Accepted": "accepted", "Proposal.Rejected": "rejected"}
READINESS_EVENT = "IWP.ReadinessEvaluated"
ACTIVITY_DROP = ("Kind", "From", "What", "Why")  # the order the Activity table drops columns
TECHNICAL_COLUMNS = ("#", "When", "Event", "Actor", "Summary", "From")
PLAIN_COLUMNS = ("When", "Who", "Kind", "What", "From")


def kind_word(kind: str) -> str:
    """The Kind column's word; a kind the table does not name reads as it is capitalised."""
    return KIND_WORDS.get(kind, kind.capitalize())


def page_has_why(rows: list[ActivityRow]) -> bool:
    return any(r.why for r in rows)


def activity_columns(rows: list[ActivityRow], *, technical: bool) -> tuple[str, ...]:
    base = TECHNICAL_COLUMNS if technical else PLAIN_COLUMNS
    return (*base, "Why") if page_has_why(rows) else base


def _name(actor: str, labels: Labels) -> str:
    """A decider's name: an agent by its id, anyone else as ``display.actor_label`` gives it."""
    if actor.startswith("agent:"):
        return actor[len("agent:") :]
    return actor_label(labels, actor)


def who_text(row: ActivityRow, labels: Labels) -> str:
    """The actor's words: a person by name and a service by its label (``display.actor_label``);
    an agent as ``Agent: <id>`` (brief A1.1). A decided proposal reads ``accepted by <decider>``
    or ``rejected by <decider>``; the filing row already names who filed it."""
    actor = row.event.actor
    verb = DECIDED_WORDS.get(row.event.event_type)
    if row.kind == "proposal" and verb:
        return f"{verb} by {_name(row.decided_by or actor, labels)}"
    if actor.startswith("agent:"):
        return f"Agent: {actor[len('agent:') :]}"
    return actor_label(labels, actor)


def what_text(row: ActivityRow, labels: Labels, *, technical: bool) -> str:
    """What happened: the proposal and readiness words, else the event's label, and the summary
    for the record's own rows (a related row reads as its label only). A summary that already
    begins with the label's word stands alone."""
    event = row.event
    if row.kind == "proposal" and event.event_type in PROPOSAL_WORDS:
        return PROPOSAL_WORDS[event.event_type]
    if event.event_type == READINESS_EVENT:
        return f"Readiness checked: {row.note}" if row.note else "Readiness checked"
    label = event.event_type if technical else event_label(event.event_type)
    if row.related:
        return label
    summary = event_summary(event, labels, technical=technical)
    if not summary:
        return label
    if re.match(rf"{re.escape(label)}\b", summary, re.IGNORECASE):
        return summary
    return f"{label}: {summary}"


def why_text(row: ActivityRow) -> str:
    return row.why or EMPTY


def from_text(row: ActivityRow) -> str:
    return f"↳ {row.from_key}" if row.related and row.from_key else EMPTY


def activity_cells(
    row: ActivityRow, labels: Labels, *, technical: bool, with_why: bool
) -> tuple[str, ...]:
    if technical:
        cells = (*history_cells(row.event, labels, technical=True), from_text(row))
    else:
        cells = (
            timestamp(row.event.recorded_at.isoformat()),
            who_text(row, labels),
            kind_word(row.kind),
            what_text(row, labels, technical=False),
            from_text(row),
        )
    return (*cells, why_text(row)) if with_why else cells


def filter_title(revisions_only: bool, related: bool, text: str) -> str:
    title = "Activity"
    if revisions_only:
        title += " · Revisions only"
    if not related:
        title += " · Related off"
    if text:
        title += f' · "{text}"'
    return title


def row_matches(row: ActivityRow, text: str, labels: Labels) -> bool:
    needle = text.lower()
    haystack = (
        what_text(row, labels, technical=False),
        who_text(row, labels),
        from_text(row),
    )
    return any(needle in cell.lower() for cell in haystack)
