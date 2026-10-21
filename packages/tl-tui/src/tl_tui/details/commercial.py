"""Details of a Commercial item (an early warning, a change notice, a claim), read through
``get_commercial`` (the key is the number). Plain words; the technical rows follow the mode."""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, domain_label, humanize, type_label
from tl_tui.text import EMPTY, timestamp


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _money(currency: str | None, value: str | None) -> str:
    return EMPTY if not value else f"{currency or ''} {value}".strip()


@register("correspondence.CommercialItem")
def commercial_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_commercial(project, str(record["key"]))
    days = EMPTY if view.schedule_impact_days is None else f"{view.schedule_impact_days} days"
    rows = [
        DetailRow("Type", type_label(labels, "correspondence.CommercialItem")),
        DetailRow("Number", view.number),
        DetailRow("Subject", view.subject),
        DetailRow(
            "Kind", domain_label(labels, "commercial", view.subtype) if view.subtype else EMPTY
        ),
        DetailRow("State", humanize(view.state)),
        DetailRow("Confidentiality", code_label(labels, "confidentiality", view.confidentiality)),
        DetailRow("Clause", _or_empty(view.clause)),
        DetailRow("Aware on", _or_empty(view.aware_on)),
        DetailRow("Issued", _or_empty(view.issued_on)),
        DetailRow("Estimated", _money(view.currency, view.estimated_value)),
        DetailRow("Estimated hours", _or_empty(view.estimated_hours)),
        DetailRow("Schedule impact", days),
    ]
    if view.cost_code_impacts:
        codes = ", ".join(
            f"{i['cost_code']}={i.get('amount') or i.get('hours') or '-'}"
            for i in view.cost_code_impacts
        )
        rows.append(DetailRow("Cost codes", codes))
    if view.entitlement_basis:
        rows.append(DetailRow("Basis", view.entitlement_basis))
    if view.derived_from_number:
        rows.append(DetailRow("Escalated from", view.derived_from_number))
    if view.assessment_status:
        rows.append(DetailRow("Assessment", humanize(view.assessment_status)))
    rows += [
        DetailRow("Assessed on", _or_empty(view.assessed_on)),
        DetailRow("Assessed value", _money(view.currency, view.assessed_value)),
    ]
    if view.assessment_note:
        rows.append(DetailRow("Assessment note", view.assessment_note))
    rows += [
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    return rows + technical_rows(record)
