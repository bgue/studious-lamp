"""Details of an RFI (a Technical item), read through ``get_rfi`` (the key is the number).

In the order a reader expects of a record (P1-UX2-S5, SCOPE clause 3): the narrative (subject,
question, proposed solution, the answer with who gave it and when, the cost and schedule views,
the review and the escalation), then the status timeline from the record's events and clocks, then
the register metadata. Plain words; the answer, review and escalation rows appear only when there
is one, and the technical rows follow the mode (P1-UX-T04).
"""

from __future__ import annotations

from typing import Any

from tl_core.ledger import Event
from tl_mod_correspondence.names import CORR_DEFINED, TECH_ANSWERED

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.correspondence import item_history, timeline_detail_rows
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, domain_label, humanize, type_label
from tl_tui.text import EMPTY, timestamp
from tl_tui.timeline_text import person

RFI_TYPE = "correspondence.TechnicalItem"


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _words(value: Any) -> str:
    return EMPTY if value is None or value == "" else humanize(str(value))


def _answerer(events: list[Event], labels: Labels) -> str:
    """The plain name of whoever gave the latest answer; empty when no answer event is shown."""
    answers = [e for e in events if e.event_type == TECH_ANSWERED]
    return person(answers[-1].actor, labels, technical=False) if answers else ""


@register(RFI_TYPE)
def rfi_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_rfi(project, str(record["key"]))
    events = item_history(client, record, view.id)
    narrative = [
        DetailRow("Subject", _or_empty(view.subject)),
        DetailRow("Question", _or_empty(view.question)),
        DetailRow("Proposed solution", _or_empty(view.proposed_solution)),
    ]
    if view.answered_on or view.answer:
        who = _answerer(events, labels)
        narrative += [DetailRow("Answer", _or_empty(view.answer))]
        if view.answered_on:
            on = view.answered_on
            narrative.append(
                DetailRow("Answered by", f"{who} on {on}") if who else DetailRow("Answered on", on)
            )
        narrative += [
            DetailRow("Answerer says cost", _words(view.answer_cost_impact)),
            DetailRow("Answerer says schedule", _words(view.answer_schedule_impact)),
            DetailRow("Answered in item", _or_empty(view.answer_item_number)),
        ]
    narrative += [
        DetailRow("Raiser expects cost", _words(view.potential_cost_impact)),
        DetailRow("Raiser expects schedule", _words(view.potential_schedule_impact)),
    ]
    if view.review_decision:
        review = humanize(view.review_decision)
        if view.reviewed_on:
            review += f" on {view.reviewed_on}"
        if view.review_note:
            review += f": {view.review_note}"
        narrative.append(DetailRow("Review", review))
    if view.escalations:
        escalated = ", ".join(f"{e.number} ({humanize(e.state)})" for e in view.escalations)
        narrative.append(DetailRow("Escalated to", escalated))
    derived = [
        defined
        for e in view.escalations
        for defined in client.history(e.id)
        if defined.event_type == CORR_DEFINED
    ]
    timeline = timeline_detail_rows(client, project, events, view.id, labels, escalations=derived)
    metadata = [
        DetailRow("Type", type_label(labels, RFI_TYPE)),
        DetailRow("Number", view.number),
        DetailRow(
            "Kind", domain_label(labels, "technical", view.subtype) if view.subtype else EMPTY
        ),
        DetailRow("State", _words(view.state)),
        DetailRow("Confidentiality", code_label(labels, "confidentiality", view.confidentiality)),
        DetailRow("Discipline", _or_empty(view.discipline)),
        DetailRow("Needed by", _or_empty(view.required_by)),
        DetailRow("Issued", _or_empty(view.issued_on)),
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    return [*narrative, *timeline, *metadata, *technical_rows(record)]
