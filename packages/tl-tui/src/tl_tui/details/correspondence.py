"""Details of a correspondence item and of a response clock (P1-UX-T03, P1-UX3).

An item is read by its number (``get_correspondence``, the key is the number); a clock by its
record id (``get_clock``), because the clock key is not the number. Plain rows carry domain labels
and actor names; the clock key, the calendar, the received-via and external-reference rows, and the
envelope rows are technical and show only in technical mode.

The rows sit in named sections (skill ``tui-layout``): the message, the key facts, the people, the
dates, the response clocks, the status timeline, the files. ``item_content`` and ``clock_content``
build them from a view already read, and the Details tab and the correspondence panel both use them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_core.ledger import Event
from tl_mod_correspondence.views import ClockView, ItemView, RecipientView

from tl_tui.client import ClientInterface
from tl_tui.details import (
    TECHNICAL_SECTION,
    DetailRow,
    file_rows,
    link_rows,
    plain_code,
    register,
    table_rows,
)
from tl_tui.details.generic import technical_rows
from tl_tui.display import (
    Labels,
    actor_label,
    domain_label,
    humanize,
)
from tl_tui.layout import Cell, state_style
from tl_tui.text import EMPTY
from tl_tui.timeline_text import person, timeline_lines, timeline_rows

ITEM_TYPE = "correspondence.Correspondence"
CLOCK_TYPE = "correspondence.ResponseClock"


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _people(people: Sequence[RecipientView]) -> str:
    """Names, else email addresses, comma-separated."""
    return ", ".join(p.name or p.email or EMPTY for p in people) or EMPTY


TIMELINE = "Timeline"
TIMELINE_COLUMNS = ("Date", "Who", "Event")
CLOCK_COLUMNS = ("Clock", "State", "Due", "Days left")
TIMELINE_TIMES = "Timeline times"
CLOCKS = "Response clocks"


def item_history(client: ClientInterface, record: dict[str, Any], item_id: str) -> list[Event]:
    """The viewer-filtered events of the item (empty when the record has none to show)."""
    return client.history(str(record.get("id") or item_id))


def timeline_detail_rows(
    client: ClientInterface,
    project: str,
    events: Sequence[Event],
    item_id: str,
    labels: Labels,
    *,
    escalations: Sequence[Event] = (),
    clocks: Sequence[ClockView] | None = None,
) -> list[DetailRow]:
    """The status timeline as rows of the ``Timeline`` section: one row per state change or clock
    outcome (label = the date, value = ``who: what - note``), oldest first.

    ``clocks`` are the item's own clocks, as its view holds them. Without them every clock of the
    project is read and the item's are picked out, which costs more the more the project holds.

    The technical mode adds one row with the same lines in full (time of day, stored actor). No
    row when the record has nothing to show.
    """
    if clocks is None:
        clocks = [c for c in client.list_clocks(project, open_only=False) if c.item_id == item_id]
    else:  # the order the project list gives: soonest due first
        clocks = sorted(clocks, key=lambda c: (c.due_on, c.id))
    plain = timeline_rows(events, clocks, labels, technical=False, escalations=escalations)
    if not plain:
        return []
    rows = table_rows(
        TIMELINE,
        TIMELINE_COLUMNS,
        [
            (row.when, row.who, f"{row.what} - {row.note}" if row.note else row.what)
            for row in plain
        ],
    )
    full = timeline_rows(events, clocks, labels, technical=True, escalations=escalations)
    rows.append(
        DetailRow(
            TIMELINE_TIMES,
            "\n".join(timeline_lines(full)),
            technical=True,
            section=TECHNICAL_SECTION,
            panel=False,
        )
    )
    return rows


def clock_state(clock: ClockView) -> str:
    """The state in words: ``Running``, ``Met``, ``Paused``, ``Expired``."""
    return humanize(clock.effective_state)


def clock_left(clock: ClockView) -> str:
    """The days left as a number, ``-3`` once over, ``10 working`` for working days (calendar days
    are the default and carry no unit); ``—`` once the clock is closed."""
    left = clock.days_left
    if left is None or clock.closed_on:
        return EMPTY
    return f"{left}" if clock.day_type == "calendar" else f"{left} {clock.day_type}"


def clock_value(clock: ClockView) -> str:
    """One clock under an item in words: ``Running · due 2026-11-02 · 14 calendar days left``,
    ``Met on 2026-10-12``."""
    state = humanize(clock.effective_state)
    if clock.closed_on:
        return f"{state} on {clock.closed_on}"
    parts = [state, f"due {clock.due_on}"]
    left = clock.days_left
    if left is not None:
        unit = f"{clock.day_type} day{'s' if abs(left) != 1 else ''}"
        parts.append(f"{abs(left)} {unit} {'over' if left < 0 else 'left'}")
    if clock.paused_on:
        parts.append(f"paused since {clock.paused_on}")
    return " · ".join(parts)


def clock_names(clocks: Sequence[ClockView]) -> list[str]:
    """Each clock's name; clocks that share one are told apart by round, oldest first:
    ``Answer required, round 2``."""
    names = [c.label or humanize(c.kind) for c in clocks]
    shown = list(names)
    for name in set(names):
        same = sorted(
            (i for i, other in enumerate(names) if other == name),
            key=lambda i: (clocks[i].start_on, i),
        )
        if len(same) > 1:
            for round_, index in enumerate(same, 1):
                shown[index] = f"{name}, round {round_}"
    return shown


def clock_rows_of(clocks: Sequence[ClockView]) -> list[DetailRow]:
    """The ``Response clocks`` section as a small table (clock, state, due, days left); in
    technical mode the clock key and calendar follow in the technical section."""
    names = clock_names(clocks)
    rows = table_rows(
        CLOCKS,
        CLOCK_COLUMNS,
        [
            (name, Cell(clock_state(c), state_style(clock_state(c))), c.due_on, clock_left(c))
            for name, c in zip(names, clocks, strict=True)
        ],
    )
    rows += [
        DetailRow(f"Clock {name}", f"{c.key} · calendar {c.calendar}", True, TECHNICAL_SECTION)
        for name, c in zip(names, clocks, strict=True)
    ]
    return rows


DIRECTIONS = {"in": "Incoming", "out": "Outgoing", "internal": "Internal"}


def direction_word(direction: str) -> str:
    """``Incoming``, ``Outgoing`` or ``Internal`` for a stored direction."""
    return DIRECTIONS.get(direction, humanize(direction))


def drafter_of(events: Sequence[Event], labels: Labels) -> str:
    """The plain name of whoever made the item (the actor of its first event); else empty."""
    return person(events[0].actor, labels, technical=False) if events else ""


def item_content(
    client: ClientInterface | None,
    project: str,
    view: ItemView,
    labels: Labels,
    *,
    record: dict[str, Any] | None = None,
    suggestion: str = "",
    events: Sequence[Event] | None = None,
) -> list[DetailRow]:
    """The sections of a correspondence item. ``record`` (the envelope) adds the record dates and
    the technical envelope rows; a panel passes none and gets the record id instead."""
    history: Sequence[Event] = []
    if events is not None:
        history = events
    elif client is not None:
        history = item_history(client, {}, view.id)
    outgoing, incoming = view.direction == "out", view.direction == "in"
    domain = domain_label(labels, view.domain, view.subtype) if view.domain else EMPTY
    facts = [
        DetailRow("Direction", direction_word(view.direction), section="Key facts", panel=False),
        DetailRow("Domain", domain, section="Key facts"),
    ]
    medium = humanize(view.medium)
    if medium.lower() != domain.lower():  # a letter by letter says Letter once
        facts.append(DetailRow("Medium", medium, section="Key facts"))
    facts += [
        DetailRow(
            "Confidentiality",
            plain_code(labels, "confidentiality", view.confidentiality),
            section="Key facts",
        ),
        DetailRow("Thread", _or_empty(view.thread_number), section="Key facts"),
        DetailRow("Replies to", _or_empty(view.responds_to_number), section="Key facts"),
    ]
    if outgoing:  # from us: the name given, else whoever drafted it
        sender = view.from_name or drafter_of(history, labels) or EMPTY
    else:
        sender = _or_empty(view.from_name)
    people = [DetailRow("From", sender, section="People")]
    if view.to or outgoing:  # a received letter is to us: no row unless it names recipients
        people.append(DetailRow("To", _people(view.to), section="People"))
    if view.cc:
        people.append(DetailRow("Copy", _people(view.cc), section="People"))
    dates: list[DetailRow] = []
    if incoming:
        dates.append(DetailRow("Received", _or_empty(view.received_on), section="Dates"))
    else:
        dates += [
            DetailRow("Issued", _or_empty(view.issued_on), section="Dates"),
            DetailRow("Sent", _or_empty(view.sent_on), section="Dates"),
        ]
    if view.response_required:
        dates += [
            DetailRow("Reply due", _or_empty(view.response_due), section="Dates"),
            DetailRow("Replied on", _or_empty(view.responded_on), section="Dates"),
        ]
    if incoming:
        dates.append(DetailRow("Triaged on", _or_empty(view.triaged_on), section="Dates"))
    rows = [DetailRow("", _or_empty(view.body), section="Message")]
    if suggestion:
        rows.append(DetailRow("", suggestion, section="Suggestion"))
    rows += [*facts, *people, *dates, *clock_rows_of(view.clocks)]
    if client is not None:
        rows += timeline_detail_rows(client, project, history, view.id, labels, clocks=view.clocks)
        rows += file_rows(client, view.id)
        rows += link_rows(client, view.id)
    rows += [
        *(
            technical_rows(record)
            if record is not None
            else [DetailRow("Record id", view.id, True, TECHNICAL_SECTION)]
        ),
        *(
            [DetailRow("Received via", _or_empty(view.received_via), True, TECHNICAL_SECTION)]
            if incoming
            else [DetailRow("Delivery", _or_empty(view.delivery), True, TECHNICAL_SECTION)]
        ),
        DetailRow("External reference", _or_empty(view.external_ref), True, TECHNICAL_SECTION),
    ]
    return rows


@register(ITEM_TYPE)
def item_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_correspondence(project, str(record["key"]))
    events = item_history(client, record, view.id)
    return item_content(client, project, view, labels, record=record, events=events)


def clock_content(
    view: ClockView, labels: Labels, *, record: dict[str, Any] | None = None
) -> list[DetailRow]:
    """The sections of a response clock (the Details tab, and the clocks panel)."""
    # the panel's identity, state line and summary hold the item, state, due date and days left
    facts = [
        DetailRow("Item", view.item_number, section="Key facts", panel=False),
        DetailRow("State", clock_state(view), section="Key facts", panel=False),
        DetailRow("Due", _or_empty(view.due_on), section="Key facts", panel=False),
        DetailRow("Days left", clock_left(view), section="Key facts", panel=False),
    ]
    if humanize(view.kind).lower() != (view.label or "").lower():
        facts.append(DetailRow("Kind", humanize(view.kind), section="Key facts"))
    facts += [
        DetailRow("Started", _or_empty(view.start_on), section="Key facts"),
        DetailRow("Length", f"{view.duration_days} {view.day_type} days", section="Key facts"),
        DetailRow(
            "Warns (days before)",
            ", ".join(str(d) for d in view.warn_days) or EMPTY,
            section="Key facts",
        ),
        DetailRow(
            "Owner", actor_label(labels, view.owner) if view.owner else EMPTY, section="Key facts"
        ),
    ]
    rows = list(facts)
    if view.problem:
        rows.append(DetailRow("", view.problem, section="Problem"))
    rows += [
        DetailRow("Clock key", view.key, True, TECHNICAL_SECTION),
        DetailRow("Calendar", view.calendar, True, TECHNICAL_SECTION),
        DetailRow("Restarts", str(view.restarts), True, TECHNICAL_SECTION),
    ]
    return rows + (technical_rows(record) if record is not None else [])


@register(CLOCK_TYPE)
def clock_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_clock(project, str(record["id"]))
    return clock_content(view, labels, record=record)
