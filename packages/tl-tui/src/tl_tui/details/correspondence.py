"""Details of a correspondence item and of a response clock (P1-UX-T03).

An item is read by its number (``get_correspondence``, the key is the number); a clock by its
record id (``get_clock``), because the clock key is not the number. Plain rows carry domain labels
and actor names; the clock key, the calendar, the received-via and external-reference rows, and the
envelope rows are technical and show only in technical mode.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_mod_correspondence.views import RecipientView

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import (
    Labels,
    actor_label,
    code_label,
    domain_label,
    humanize,
    type_label,
)
from tl_tui.text import EMPTY, timestamp

ITEM_TYPE = "correspondence.Correspondence"
CLOCK_TYPE = "correspondence.ResponseClock"


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _people(people: Sequence[RecipientView]) -> str:
    """Names, else email addresses, comma-separated."""
    return ", ".join(p.name or p.email or EMPTY for p in people) or EMPTY


@register(ITEM_TYPE)
def item_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_correspondence(project, str(record["key"]))
    rows = [
        DetailRow("Type", type_label(labels, ITEM_TYPE)),
        DetailRow("Number", view.number),
        DetailRow("Subject", _or_empty(view.subject)),
        DetailRow("Domain", domain_label(labels, view.domain, view.subtype)),
        DetailRow("State", humanize(view.state)),
        DetailRow("Direction", humanize(view.direction)),
        DetailRow("Medium", humanize(view.medium)),
        DetailRow("From", _or_empty(view.from_name)),
        DetailRow("To", _people(view.to)),
    ]
    if view.cc:
        rows.append(DetailRow("Copy", _people(view.cc)))
    rows += [
        DetailRow("Received", _or_empty(view.received_on)),
        DetailRow("Sent", _or_empty(view.sent_on)),
        DetailRow("Issued", _or_empty(view.issued_on)),
        DetailRow("Confidentiality", code_label(labels, "confidentiality", view.confidentiality)),
    ]
    if view.response_required:
        rows += [
            DetailRow("Answer expected by", _or_empty(view.response_due)),
            DetailRow("Answered on", _or_empty(view.responded_on)),
        ]
    rows += [
        DetailRow("Thread", _or_empty(view.thread_number)),
        DetailRow("Replies to", _or_empty(view.responds_to_number)),
        DetailRow("Triaged on", _or_empty(view.triaged_on)),
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    return [
        *rows,
        *technical_rows(record),
        DetailRow("Received via", _or_empty(view.received_via), technical=True),
        DetailRow("External reference", _or_empty(view.external_ref), technical=True),
    ]


@register(CLOCK_TYPE)
def clock_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_clock(project, str(record["id"]))
    rows = [
        DetailRow("Type", type_label(labels, CLOCK_TYPE)),
        DetailRow("Item", view.item_number),
        DetailRow("Label", _or_empty(view.label)),
        DetailRow("Kind", humanize(view.kind)),
        DetailRow("State", humanize(view.effective_state)),
        DetailRow("Started", _or_empty(view.start_on)),
        DetailRow("Due", _or_empty(view.due_on)),
        DetailRow("Days left", EMPTY if view.days_left is None else str(view.days_left)),
        DetailRow("Length", f"{view.duration_days} {view.day_type} days"),
        DetailRow("Warns (days before)", ", ".join(str(d) for d in view.warn_days) or EMPTY),
        DetailRow("Owner", actor_label(labels, view.owner) if view.owner else EMPTY),
    ]
    if view.problem:
        rows.append(DetailRow("Problem", view.problem))
    rows += [
        DetailRow("Clock key", view.key, technical=True),
        DetailRow("Calendar", view.calendar, technical=True),
        DetailRow("Restarts", str(view.restarts), technical=True),
    ]
    return rows + technical_rows(record)
