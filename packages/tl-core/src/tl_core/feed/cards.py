"""Event-card aggregation rules (brief 21.1, FANOUT decision D1). Pure: no database, no clock.

A card is the feed rendering of a burst of ledger events. The rules below are what
``projection.feed.FeedProjector`` applies to each event, in ``seq`` order, per scope. They use only
the event's own fields (``recorded_at``, ``seq`` order, actor, type, scope), never wall-clock time,
so a rebuild gives the same cards as the live run.

Each scope has at most one *open* card. For every event the projector asks ``disposition``:

* ``ignore``: plumbing that must not split a burst. ``Numbering.Allocated`` is written just before
  every ``Record.Created`` that takes a number, and ``Link.Suggested`` is written when a post tags a
  record; both would otherwise cut every burst in two. ``Webhook.*`` are operations events. These
  events become no card and leave the open card as it is.
* ``close``: a ``Feed.*`` event. It never becomes a card (contract in ``feed.types``) and, as any
  other event in the scope that is not part of the burst, it closes the open card, so posts and
  cards stay in the order things happened.
* ``extend``: the event has the open card's actor and event type and its ``recorded_at`` is at most
  ``CARD_WINDOW_SECONDS`` after the card's first event (inclusive).
* ``start``: anything else. The open card, if any, is closed and the event opens a new one.

The card id is ``card:<event id of its first event>``. Its ``occurred_at`` and ``seq`` follow its
latest event, so an extended card moves to the top of the feed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from tl_core.feed.types import CARD_WINDOW_SECONDS
from tl_core.ledger import Event

Disposition = Literal["ignore", "close", "extend", "start"]

TRANSPARENT_EVENT_TYPES: frozenset[str] = frozenset({"Numbering.Allocated", "Link.Suggested"})
TRANSPARENT_PREFIXES: tuple[str, ...] = ("Webhook.",)

# Event types whose stream is the subject record (the card is about that record).
_STREAM_SUBJECT_PREFIXES: tuple[str, ...] = ("Record.", "Pset.", "Workflow.")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# event type -> (verb, singular noun, plural noun)
_PHRASES: dict[str, tuple[str, str, str]] = {
    "Record.Created": ("created", "record", "records"),
    "Record.Updated": ("updated", "record", "records"),
    "Record.Voided": ("voided", "record", "records"),
    "Record.Corrected": ("corrected", "record", "records"),
    "Pset.ValuesSet": ("set properties on", "record", "records"),
    "Workflow.Transitioned": ("moved", "record", "records"),
    "Link.Added": ("added", "link", "links"),
    "Link.Accepted": ("accepted", "link", "links"),
    "Link.Declined": ("declined", "link", "links"),
    "Link.Repinned": ("repinned", "link", "links"),
    "Link.Verified": ("verified", "link", "links"),
    "Link.Flagged": ("flagged", "link", "links"),
    "Link.Retracted": ("retracted", "link", "links"),
    "File.Uploaded": ("uploaded", "file", "files"),
    "File.Processed": ("processed", "file", "files"),
    "File.Rejected": ("rejected", "file", "files"),
}


@dataclass(frozen=True)
class OpenCard:
    """The part of a scope's open card the rules look at."""

    item_id: str
    actor: str
    event_type: str
    first_us: int  # recorded_at of the first event, microseconds since the Unix epoch
    event_count: int


def is_feed_event(event_type: str) -> bool:
    return event_type.startswith("Feed.")


def is_transparent(event_type: str) -> bool:
    return event_type in TRANSPARENT_EVENT_TYPES or event_type.startswith(TRANSPARENT_PREFIXES)


def to_us(moment: datetime) -> int:
    """Microseconds since the Unix epoch, exactly (integer arithmetic). Naive means UTC."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return (aware - _EPOCH) // timedelta(microseconds=1)


def card_id_for(first_event_id: str) -> str:
    return f"card:{first_event_id}"


def disposition(open_card: OpenCard | None, event: Event) -> Disposition:
    """What ``event`` does to its scope's open card. See the module docstring."""
    event_type = event.event_type
    if is_transparent(event_type):
        return "ignore"
    if is_feed_event(event_type):
        return "close"
    if (
        open_card is not None
        and open_card.actor == event.actor
        and open_card.event_type == event_type
        and 0 <= to_us(event.recorded_at) - open_card.first_us <= CARD_WINDOW_SECONDS * 1_000_000
    ):
        return "extend"
    return "start"


def subjects_of(event: Event) -> list[str]:
    """Ids of the records ``event`` is about, without repeats.

    ``Record.*``, ``Pset.*`` and ``Workflow.*`` are about their stream's record. ``Link.*`` are
    about both ends (``from_ref``, ``to_ref``). ``File.*`` are about ``record_id`` when the payload
    has one. Anything else is about no record.
    """
    event_type = event.event_type
    found: list[str] = []
    if event_type.startswith(_STREAM_SUBJECT_PREFIXES):
        found = [event.stream_id]
    elif event_type.startswith("Link."):
        found = [str(event.payload[k]) for k in ("from_ref", "to_ref") if event.payload.get(k)]
    elif event_type.startswith("File.") and event.payload.get("record_id"):
        found = [str(event.payload["record_id"])]
    return list(dict.fromkeys(found))


def display_actor(actor: str) -> str:
    """``user:jsmith`` reads ``jsmith``; other actors (``agent:x``, ``svc:y``) read as they are."""
    return actor.removeprefix("user:")


def render_card_summary(actor: str, event_type: str, count: int) -> str:
    """One line for a card: ``jsmith created 14 records`` or ``jsmith created a record``.

    Event types without a phrase read ``<actor> <verb> <count> <noun>`` from their own name, for
    example ``svc:x published 2 schemapackage``; they are rare and plural-agnostic.
    """
    who = display_actor(actor)
    phrase = _PHRASES.get(event_type)
    if phrase is None:
        noun, _, verb = event_type.partition(".")
        phrase = (verb.lower() or "did", noun.lower(), noun.lower())
    verb, singular, plural = phrase
    if count == 1:
        article = "an" if singular[0] in "aeiou" else "a"
        return f"{who} {verb} {article} {singular}"
    return f"{who} {verb} {count} {plural}"


def fold_cards(events: Sequence[Event]) -> list[tuple[str, str, str, int, int]]:
    """The cards the rules make of ``events`` (all in one scope, in ``seq`` order).

    Returns ``(card_id, actor, event_type, event_count, last_seq)`` per card, oldest first. It is
    the rules without a database, used by tests as the oracle for the projector and by anyone who
    wants to explain a card.
    """
    cards: list[tuple[str, str, str, int, int]] = []
    open_card: OpenCard | None = None
    for event in events:
        action = disposition(open_card, event)
        if action == "ignore":
            continue
        if action == "close":
            open_card = None
        elif action == "extend" and open_card is not None:
            count = open_card.event_count + 1
            open_card = OpenCard(
                open_card.item_id, open_card.actor, open_card.event_type, open_card.first_us, count
            )
            cards[-1] = (open_card.item_id, event.actor, event.event_type, count, event.seq)
        else:
            card_id = card_id_for(event.event_id)
            open_card = OpenCard(
                card_id, event.actor, event.event_type, to_us(event.recorded_at), 1
            )
            cards.append((card_id, event.actor, event.event_type, 1, event.seq))
    return cards
