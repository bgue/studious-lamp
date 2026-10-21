"""Details of an RFI (a Technical item), read through ``get_rfi`` (the key is the number). Plain
words; the answer, review and escalation rows appear only when there is one, and the technical
rows follow the mode (P1-UX-T04, SCOPE clause 3)."""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, domain_label, humanize, type_label
from tl_tui.text import EMPTY, timestamp

RFI_TYPE = "correspondence.TechnicalItem"


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _words(value: Any) -> str:
    return EMPTY if value is None or value == "" else humanize(str(value))


@register(RFI_TYPE)
def rfi_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_rfi(project, str(record["key"]))
    rows = [
        DetailRow("Type", type_label(labels, RFI_TYPE)),
        DetailRow("Number", view.number),
        DetailRow("Subject", _or_empty(view.subject)),
        DetailRow(
            "Kind", domain_label(labels, "technical", view.subtype) if view.subtype else EMPTY
        ),
        DetailRow("State", _words(view.state)),
        DetailRow("Confidentiality", code_label(labels, "confidentiality", view.confidentiality)),
        DetailRow("Discipline", _or_empty(view.discipline)),
        DetailRow("Needed by", _or_empty(view.required_by)),
        DetailRow("Issued", _or_empty(view.issued_on)),
        DetailRow("Question", _or_empty(view.question)),
        DetailRow("Proposed solution", _or_empty(view.proposed_solution)),
        DetailRow("Raiser expects cost", _words(view.potential_cost_impact)),
        DetailRow("Raiser expects schedule", _words(view.potential_schedule_impact)),
    ]
    if view.answered_on or view.answer:
        rows += [
            DetailRow("Answer", _or_empty(view.answer)),
            DetailRow("Answered on", _or_empty(view.answered_on)),
            DetailRow("Answerer says cost", _words(view.answer_cost_impact)),
            DetailRow("Answerer says schedule", _words(view.answer_schedule_impact)),
            DetailRow("Answered by item", _or_empty(view.answer_item_number)),
        ]
    if view.review_decision:
        review = humanize(view.review_decision)
        if view.reviewed_on:
            review += f" on {view.reviewed_on}"
        if view.review_note:
            review += f": {view.review_note}"
        rows.append(DetailRow("Review", review))
    if view.escalations:
        escalated = ", ".join(f"{e.number} ({humanize(e.state)})" for e in view.escalations)
        rows.append(DetailRow("Escalated to", escalated))
    rows += [
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    return rows + technical_rows(record)
