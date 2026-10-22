"""Details of an RFI (a Technical item), read through ``get_rfi`` (the key is the number).

In the order a reader expects of a record (P1-UX2-S5, P1-UX3; skill ``tui-layout``): the question,
the proposed solution, the answer with the review, the key facts (discipline, needed by, who with,
the cost and schedule views, the escalation), the response clocks, the status timeline from the
record's events and clocks, and the files. Plain words; the answer section appears only when there
is one, and the technical rows follow the mode (P1-UX-T04). The number, subject and state are the
record screen's header and a panel's identity and state lines, so they are not rows.

``rfi_content`` builds the rows from a view already read; the Details tab and the RFI log's panel
both use it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_core.ledger import Event
from tl_mod_correspondence.names import CORR_DEFINED, TECH_ANSWERED
from tl_mod_correspondence.views import RecipientView
from tl_mod_correspondence.views_domain import TechnicalView

from tl_tui.client import ClientInterface
from tl_tui.details import TECHNICAL_SECTION, DetailRow, file_rows, register
from tl_tui.details.correspondence import (
    clock_rows_of,
    item_history,
    timeline_detail_rows,
)
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, domain_label, humanize
from tl_tui.text import EMPTY, timestamp
from tl_tui.timeline_text import person

RFI_TYPE = "correspondence.TechnicalItem"
FACTS = "Key facts"
ANSWER = "Answer"


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _words(value: Any) -> str:
    return EMPTY if value is None or value == "" else humanize(str(value))


def _answerer(events: Sequence[Event], labels: Labels) -> str:
    """The plain name of whoever gave the latest answer; empty when no answer event is shown."""
    answers = [e for e in events if e.event_type == TECH_ANSWERED]
    return person(answers[-1].actor, labels, technical=False) if answers else ""


def _people(people: Sequence[RecipientView]) -> str:
    return ", ".join(p.name or p.email or EMPTY for p in people) or EMPTY


def _impact(expected: str, answered: str | None) -> str:
    """``Raiser: Unknown · Answer: No``; before an answer only the raiser's view."""
    text = f"Raiser: {_words(expected)}"
    return text + (f" · Answer: {_words(answered)}" if answered else "")


def rfi_content(
    view: TechnicalView,
    labels: Labels,
    *,
    client: ClientInterface | None = None,
    project: str = "",
    record: dict[str, Any] | None = None,
    events: Sequence[Event] | None = None,
) -> list[DetailRow]:
    """The sections of an RFI. Without a ``client`` there is no timeline and no files list;
    ``record`` (the envelope) adds the record dates and technical envelope rows, otherwise the
    record id is the one technical row."""
    history = events
    if history is None:
        history = item_history(client, {}, view.id) if client is not None else []
    rows = [
        DetailRow("", _or_empty(view.question), section="Question"),
        DetailRow("", _or_empty(view.proposed_solution), section="Proposed solution"),
    ]
    if view.answered_on or view.answer:
        who = _answerer(history, labels)
        rows.append(DetailRow("", _or_empty(view.answer), section=ANSWER))
        if view.answered_on:
            on = view.answered_on
            rows.append(
                DetailRow("Answered by", f"{who} on {on}", section=ANSWER)
                if who
                else DetailRow("Answered on", on, section=ANSWER)
            )
        if view.answer_item_number:
            rows.append(DetailRow("Answered in item", view.answer_item_number, section=ANSWER))
        if view.review_decision:
            review = humanize(view.review_decision)
            if view.reviewed_on:
                review += f" on {view.reviewed_on}"
            if view.review_note:
                review += f": {view.review_note}"
            rows.append(DetailRow("Review", review, section=ANSWER))
    rows += [
        DetailRow("Discipline", code_label(labels, "discipline", view.discipline), section=FACTS),
        DetailRow(
            "Kind",
            domain_label(labels, "technical", view.subtype) if view.subtype else EMPTY,
            section=FACTS,
        ),
        DetailRow("Needed by", _or_empty(view.required_by), section=FACTS),
        DetailRow("Issued", _or_empty(view.issued_on), section=FACTS),
        DetailRow("From", _or_empty(view.from_name), section=FACTS),
        DetailRow("To", _people(view.to), section=FACTS),
        DetailRow(
            "Cost impact",
            _impact(view.potential_cost_impact, view.answer_cost_impact),
            section=FACTS,
        ),
        DetailRow(
            "Schedule impact",
            _impact(view.potential_schedule_impact, view.answer_schedule_impact),
            section=FACTS,
        ),
        DetailRow(
            "Confidentiality",
            code_label(labels, "confidentiality", view.confidentiality),
            section=FACTS,
        ),
    ]
    if view.escalations:
        escalated = ", ".join(f"{e.number} ({humanize(e.state)})" for e in view.escalations)
        rows.append(DetailRow("Escalated to", escalated, section=FACTS))
    if record is not None:
        rows += [
            DetailRow("Created", timestamp(record.get("created_at")), section=FACTS, panel=False),
            DetailRow("Updated", timestamp(record.get("updated_at")), section=FACTS, panel=False),
        ]
    rows += clock_rows_of(view.clocks)
    if client is not None:
        derived = [
            defined
            for e in view.escalations
            for defined in client.history(e.id)
            if defined.event_type == CORR_DEFINED
        ]
        rows += timeline_detail_rows(client, project, history, view.id, labels, escalations=derived)
        rows += file_rows(client, view.id)
    rows += (
        technical_rows(record)
        if record is not None
        else [DetailRow("Record id", view.id, True, TECHNICAL_SECTION)]
    )
    return rows


@register(RFI_TYPE)
def rfi_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_rfi(project, str(record["key"]))
    events = item_history(client, record, view.id)
    return rfi_content(view, labels, client=client, project=project, record=record, events=events)
