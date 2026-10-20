"""What the API, the CLI, the TUI and MCP show of one Technical or Commercial item (P1-I6).

An item of these domains is a correspondence item (``views.ItemView``: number, parties, dates,
class, thread, clocks) plus the data of its domain. The models extend ``ItemView``, so a screen
that shows an item shows these. Every function takes a connection and the scope, reads through
``registry_domain`` (the viewer's confidentiality, ADR-0016) and raises ``ItemNotFoundError`` for
an unknown number and for an item the viewer may not read, with the same message. The lists of
items are the reports: ``reports_technical.rfi_log`` and ``reports_commercial.commercial_register``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core import confidentiality

from tl_mod_correspondence import registry, registry_domain, views
from tl_mod_correspondence.errors import ItemNotFoundError


class EscalationView(BaseModel):
    """A Commercial item raised from an RFI, as the reader of the RFI sees it: only if readable."""

    id: str
    number: str
    subtype: str
    state: str


class TechnicalView(views.ItemView):
    question: str
    proposed_solution: str | None
    discipline: str | None
    required_by: str | None
    potential_cost_impact: str
    potential_schedule_impact: str
    answer: str | None
    answered_on: str | None
    answer_cost_impact: str | None
    answer_schedule_impact: str | None
    answer_item_id: str | None
    answer_item_number: str | None
    answering_revision_id: str | None
    review_decision: str | None
    reviewed_on: str | None
    review_note: str | None
    escalations: list[EscalationView] = []


class CommercialView(views.ItemView):
    contract_clause_id: str | None
    clause: str | None  # ``<contract>/<clause number>``
    aware_on: str | None
    derived_from_id: str | None
    derived_from_number: str | None
    currency: str | None
    estimated_value: str | None
    estimated_hours: str | None
    cost_code_impacts: list[dict[str, Any]]
    schedule_impact_days: int | None
    schedule_impact_note: str | None
    entitlement_basis: str | None
    assessed_value: str | None
    assessed_on: str | None
    assessment_status: str | None
    assessment_note: str | None


def _base(conn: Connection, item: registry.ItemRow) -> dict[str, Any]:
    return views.item_model(conn, item).model_dump()


def technical_view(conn: Connection, scope: str, number: str) -> TechnicalView:
    """One RFI, technical query or deviation request, with its clocks and its escalations."""
    row = registry_domain.find_technical(conn, scope, number)
    if row is None:
        raise ItemNotFoundError(f"no technical item {number!r} in scope {scope!r}")
    d = row.data
    answer = registry.get_item(conn, d.answer_item_id) if d.answer_item_id else None
    revision = d.answering_revision_id  # a record of another module: shown only if readable
    if revision is not None and confidentiality.is_hidden(conn, revision):
        revision = None
    return TechnicalView(
        **_base(conn, row.item),
        question=d.question,
        proposed_solution=d.proposed_solution,
        discipline=d.discipline,
        required_by=d.required_by,
        potential_cost_impact=d.potential_cost_impact,
        potential_schedule_impact=d.potential_schedule_impact,
        answer=d.answer,
        answered_on=d.answered_on,
        answer_cost_impact=d.answer_cost_impact,
        answer_schedule_impact=d.answer_schedule_impact,
        answer_item_id=d.answer_item_id if answer else None,
        answer_item_number=answer.number if answer else None,
        answering_revision_id=revision,
        review_decision=d.review_decision,
        reviewed_on=d.reviewed_on,
        review_note=d.review_note,
        escalations=[
            EscalationView(
                id=e.item.id, number=e.item.number, subtype=e.item.subtype or "", state=e.item.state
            )
            for e in registry_domain.derived_from_commercial(conn, row.item.id)
        ],
    )


def commercial_view(conn: Connection, scope: str, number: str) -> CommercialView:
    """One Commercial item, with its clocks."""
    row = registry_domain.find_commercial(conn, scope, number)
    if row is None:
        raise ItemNotFoundError(f"no commercial item {number!r} in scope {scope!r}")
    d = row.data
    clause = registry.get_clause(conn, d.contract_clause_id) if d.contract_clause_id else None
    source = registry.get_item(conn, d.derived_from_id) if d.derived_from_id else None
    return CommercialView(
        **_base(conn, row.item),
        contract_clause_id=d.contract_clause_id,
        clause=f"{clause.contract}/{clause.clause_number}" if clause else None,
        aware_on=d.aware_on,
        derived_from_id=d.derived_from_id if source else None,
        derived_from_number=source.number if source else None,
        currency=d.currency,
        estimated_value=d.estimated_value,
        estimated_hours=d.estimated_hours,
        cost_code_impacts=d.cost_code_impacts,
        schedule_impact_days=d.schedule_impact_days,
        schedule_impact_note=d.schedule_impact_note,
        entitlement_basis=d.entitlement_basis,
        assessed_value=d.assessed_value,
        assessed_on=d.assessed_on,
        assessment_status=d.assessment_status,
        assessment_note=d.assessment_note,
    )
