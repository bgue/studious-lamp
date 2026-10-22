"""Details of a Commercial item (an early warning, a change notice, a claim), read through
``get_commercial`` (the key is the number). Plain words; the technical rows follow the mode.

Sections (P1-UX3; skill ``tui-layout``): the basis of the claim, the key facts, the money and
schedule figures, the assessment, the response clocks and the files. ``commercial_content`` builds
them from a view already read; the Details tab and the Commercial register's panel both use it.
"""

from __future__ import annotations

from typing import Any

from tl_mod_correspondence.views_domain import CommercialView

from tl_tui.client import ClientInterface
from tl_tui.details import (
    TECHNICAL_SECTION,
    DetailRow,
    file_rows,
    link_rows,
    plain_code,
    record_rows,
    register,
)
from tl_tui.details.correspondence import clock_rows_of
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, domain_label, humanize
from tl_tui.text import EMPTY


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def _money(currency: str | None, value: str | None) -> str:
    return EMPTY if not value else f"{value} {currency or ''}".strip()


FACTS = "Key facts"
MONEY = "Cost and schedule"
ASSESSMENT = "Assessment"


def commercial_content(
    view: CommercialView,
    labels: Labels,
    *,
    client: ClientInterface | None = None,
    record: dict[str, Any] | None = None,
) -> list[DetailRow]:
    """The sections of a Commercial item; ``client`` adds its files, ``record`` the record dates
    and the technical envelope rows (otherwise the record id is the one technical row)."""
    days = EMPTY if view.schedule_impact_days is None else f"{view.schedule_impact_days} days"
    rows = []
    if view.entitlement_basis:
        rows.append(DetailRow("", view.entitlement_basis, section="Basis"))
    rows += [
        DetailRow(
            "Kind",
            domain_label(labels, "commercial", view.subtype) if view.subtype else EMPTY,
            section=FACTS,
        ),
        DetailRow("Clause", _or_empty(view.clause), section=FACTS),
        DetailRow("Aware on", _or_empty(view.aware_on), section=FACTS),
        DetailRow("Issued", _or_empty(view.issued_on), section=FACTS),
        DetailRow(
            "Confidentiality",
            plain_code(labels, "confidentiality", view.confidentiality),
            section=FACTS,
        ),
    ]
    if view.derived_from_number:
        rows.append(DetailRow("Escalated from", view.derived_from_number, section=FACTS))
    rows += [
        DetailRow("Estimated", _money(view.currency, view.estimated_value), section=MONEY),
        DetailRow("Estimated hours", _or_empty(view.estimated_hours), section=MONEY),
        DetailRow("Schedule impact", days, section=MONEY),
    ]
    if view.cost_code_impacts:
        codes = ", ".join(
            f"{i['cost_code']}={i.get('amount') or i.get('hours') or EMPTY}"
            for i in view.cost_code_impacts
        )
        rows.append(DetailRow("Cost codes", codes, section=MONEY))
    rows += [
        DetailRow(
            "Status",
            humanize(view.assessment_status) if view.assessment_status else EMPTY,
            section=ASSESSMENT,
        ),
        DetailRow("Assessed on", _or_empty(view.assessed_on), section=ASSESSMENT),
        DetailRow("Assessed value", _money(view.currency, view.assessed_value), section=ASSESSMENT),
    ]
    if view.assessment_note:
        rows.append(DetailRow("Note", view.assessment_note, section=ASSESSMENT))
    rows += clock_rows_of(view.clocks)
    if client is not None:
        rows += file_rows(client, view.id)
        rows += link_rows(client, view.id)
    rows += record_rows(record) if record is not None else []
    rows += (
        technical_rows(record)
        if record is not None
        else [DetailRow("Record id", view.id, True, TECHNICAL_SECTION)]
    )
    return rows


@register("correspondence.CommercialItem")
def commercial_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_commercial(project, str(record["key"]))
    return commercial_content(view, labels, client=client, record=record)
