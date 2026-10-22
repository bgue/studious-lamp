"""The status timeline of a correspondence record, as text (P1-UX2-S5; SCOPE clause 3).

Pure functions of what the client returns: the record's events (``client.history``) and its clocks
(``client.list_clocks``). A row is one state change or clock outcome with its date, the person's
plain name and the note, oldest first. Property edits (``Technical.Updated``) and event types
this module does not know are not rows, never shown raw. History is already filtered for the
viewer (ADR-0016), so a row can only name what the viewer may read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from tl_core.ledger import Event
from tl_mod_correspondence.names import COMMERCIAL, TECHNICAL
from tl_mod_correspondence.views import ClockView

from tl_tui.display import Labels, actor_label, humanize

SYSTEM = "System"
AGENT_MARK = "⚙"

#: Domain events that are a row on their own: event type -> the words of the row.
_EVENT_WORDS = {
    "Technical.Defined": "Raised",
    "Commercial.Defined": "Raised",
    "Correspondence.Triaged": "Triaged",
    "Correspondence.Issued": "Issued",
    "Technical.Answered": "Answered",
}
#: Workflow transitions that are a row: transition name -> the words. The rest (the automatic
#: ``await_response``, and the answer, review and reissue that a domain event already reports)
#: are not rows.
_TRANSITION_WORDS = {
    "submit": "Submitted",
    "return": "Returned",
    "close": "Closed",
    "void": "Void",
    "escalate": "Escalated",
}
_REVIEW_WORDS = {"accepted": "Answer accepted", "rejected": "Answer rejected"}
_ITEM_STREAMS = (TECHNICAL, COMMERCIAL)  # these report their own Defined and answer events


@dataclass(frozen=True)
class TimelineRow:
    when: str
    who: str
    what: str
    note: str = ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def person(actor: str, labels: Labels, *, technical: bool) -> str:
    """A user by name, a service as ``System`` (or its label), an agent as ``name ⚙``.

    Technical mode keeps the stored form (``user:amy``, ``svc:rules``, ``agent:planner ⚙``).
    """
    if actor.startswith("agent:"):
        if technical:
            return f"{actor} {AGENT_MARK}"
        return f"{labels.services.get(actor) or actor.removeprefix('agent:')} {AGENT_MARK}"
    if actor.startswith("svc:"):
        if technical:
            return actor
        return labels.services.get(actor) or SYSTEM
    return actor if technical else actor_label(labels, actor)


def _moment(event: Event) -> datetime:
    at = event.effective_at
    return at.astimezone(UTC) if at.tzinfo else at.replace(tzinfo=UTC)


def _when(at: datetime, *, technical: bool) -> str:
    return at.strftime("%Y-%m-%d %H:%M" if technical else "%Y-%m-%d")


def _event_words(event: Event) -> tuple[str, str] | None:
    """``(what, note)`` for an event that is a row; ``None`` for one that is not."""
    kind, payload = event.event_type, event.payload
    if kind == "Correspondence.Defined":
        if event.stream_type in _ITEM_STREAMS:
            return None  # Technical.Defined / Commercial.Defined report it
        return ("Received" if payload.get("direction") == "in" else "Drafted"), ""
    if kind == "Correspondence.Responded":
        return None if event.stream_type in _ITEM_STREAMS else ("Responded", "")
    if kind == "Technical.Reviewed":
        words = _REVIEW_WORDS.get(_text(payload.get("decision")))
        return None if words is None else (words, _text(payload.get("note")))
    if kind == "Technical.Reissued":
        return "Reissued", _text(payload.get("reason"))
    if kind == "Workflow.Transitioned":
        words = _TRANSITION_WORDS.get(_text(payload.get("transition")))
        return None if words is None else (words, _text(payload.get("reason")))
    words = _EVENT_WORDS.get(kind)
    return None if words is None else (words, "")


def _day(value: str | None) -> datetime | None:
    try:
        return datetime.combine(date.fromisoformat(value or ""), time.max, tzinfo=UTC)
    except ValueError:
        return None


def _clock_row(clock: ClockView) -> tuple[datetime, TimelineRow] | None:
    """The outcome of a clock: met on a day, expired on its date, cancelled; else no row."""
    name = clock.label or humanize(clock.kind)
    state = clock.effective_state or clock.state
    if state == "met":
        day, what = clock.closed_on, f"{name} clock met"
        note = humanize(clock.closed_reason) if clock.closed_reason else ""
    elif state == "cancelled":
        day, what = clock.closed_on, f"{name} clock cancelled"
        note = humanize(clock.closed_reason) if clock.closed_reason else ""
    elif state == "expired":
        day, what = clock.due_on, f"{name} clock expired"
        left = clock.days_left
        note = f"{-left} {clock.day_type} days overdue" if left is not None and left < 0 else ""
    else:
        return None
    at = _day(day)
    if at is None or not day:
        return None
    return at, TimelineRow(day, SYSTEM, what, note)


def timeline_rows(
    events: Sequence[Event],
    clocks: Sequence[ClockView],
    labels: Labels,
    *,
    technical: bool,
    escalations: Sequence[Event] = (),
) -> list[TimelineRow]:
    """Every state change and clock outcome, oldest first (``effective_at``, then ``seq``).

    ``escalations`` are the first events of the Commercial items raised from this record: an
    escalation writes nothing on the RFI's own stream (ADR-0016), so a reader who may read the new
    item sees it through the item's history. A clock's day has no time of day, so a clock row
    follows the events of its day.
    """
    keyed: list[tuple[tuple[datetime, int, int], TimelineRow]] = []
    for event in events:
        words = _event_words(event)
        if words is None:
            continue
        at = _moment(event)
        row = TimelineRow(
            _when(at, technical=technical),
            person(event.actor, labels, technical=technical),
            words[0],
            words[1],
        )
        keyed.append(((at, 0, event.seq), row))
    for event in escalations:
        at = _moment(event)
        number = _text(event.payload.get("number"))
        row = TimelineRow(
            _when(at, technical=technical),
            person(event.actor, labels, technical=technical),
            "Escalated",
            f"to {number}" if number else "",
        )
        keyed.append(((at, 0, event.seq), row))
    for position, clock in enumerate(clocks):
        found = _clock_row(clock)
        if found is not None:
            keyed.append(((found[0], 1, position), found[1]))
    return [row for _, row in sorted(keyed, key=lambda pair: pair[0])]


def timeline_lines(rows: Sequence[TimelineRow]) -> list[str]:
    """``2026-10-12  Amy Chen  Issued  - sent to Acme Piling``, one line per row."""
    return [
        f"{row.when}  {row.who}  {row.what}" + (f"  - {row.note}" if row.note else "")
        for row in rows
    ]
