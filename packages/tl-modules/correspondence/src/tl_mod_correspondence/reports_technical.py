"""The RFI log: every Technical item with its response time and its impact flags (brief 9, M10).

"RFI log with response times and impact flags": for each RFI, technical query or deviation request
the log shows when it was raised, issued, needed and answered, how many days the answer took,
whether it came in time, whether it is overdue, and what the raiser expected and the answerer said
about cost and schedule. It is also the register of the Technical domain: the API, the CLI and the
TUI list these lines.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016): an
item the viewer may not read is not a line and is not counted. Nothing here writes. Time comes in
as ``today`` (an ISO date), so a report is a pure function of the ledger and a day.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_correspondence import registry_domain
from tl_mod_correspondence.handlers.common import today as module_today
from tl_mod_correspondence.names import ST_AWAITING_RESPONSE


class RfiLogLine(BaseModel):
    """One Technical item as the log shows it. Dates are ISO days; ``None`` means not yet."""

    id: str
    number: str
    subject: str
    subtype: str
    discipline: str | None
    state: str
    raised_on: str  # the day the record was made
    issued_on: str | None
    required_by: str | None
    answered_on: str | None
    response_days: int | None  # calendar days from the latest issue to the answer
    on_time: bool | None  # answered on or before required_by; None until answered or no date
    overdue: bool  # still awaiting a response and required_by is before today
    days_overdue: int | None
    potential_cost_impact: str
    potential_schedule_impact: str
    cost_impact: str | None  # the answerer's statement
    schedule_impact: str | None
    review_decision: str | None
    confidentiality: str


class RfiLog(BaseModel):
    """The lines and the counts over them (the counts follow the filters, not the whole scope)."""

    scope: str
    as_of: str
    lines: list[RfiLogLine]
    total: int
    answered: int
    open: int  # not answered, and neither Closed nor Void
    overdue: int
    impact_yes: int  # the answerer said yes to cost or to schedule
    average_response_days: float | None  # over the answered lines, one decimal place


def _days_between(first: str, last: str) -> int:
    return (date.fromisoformat(last) - date.fromisoformat(first)).days


def rfi_log(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    discipline: str | None = None,
    only_open: bool = False,
    only_overdue: bool = False,
    only_impact: bool = False,
    today: str | None = None,
    limit: int = 500,
) -> RfiLog:
    """The log of the Technical items of ``scope`` that the viewer may read, newest number first.

    ``subtype``, ``state`` and ``discipline`` keep the items that have them. ``only_open`` keeps
    the items that are not answered and not Closed or Void. ``only_overdue`` keeps those still
    awaiting a response whose ``required_by`` is before ``today`` (the module's today by default).
    ``only_impact`` keeps those whose answer said yes to cost or to schedule.
    """
    day = today or module_today()
    rows = registry_domain.list_technical(
        conn, scope, subtype=subtype, state=state, discipline=discipline, limit=limit
    )
    lines: list[RfiLogLine] = []
    for row in rows:
        item, data = row.item, row.data
        answered = data.answered_on is not None
        waiting = item.state == ST_AWAITING_RESPONSE
        late = waiting and data.required_by is not None and data.required_by < day
        line = RfiLogLine(
            id=item.id,
            number=item.number,
            subject=item.subject,
            subtype=item.subtype or "",
            discipline=data.discipline,
            state=item.state,
            raised_on=item.created_at[:10],
            issued_on=item.issued_on,
            required_by=data.required_by,
            answered_on=data.answered_on,
            response_days=(
                _days_between(item.issued_on, data.answered_on)
                if item.issued_on is not None and data.answered_on is not None
                else None
            ),
            on_time=(
                data.answered_on <= data.required_by
                if data.answered_on is not None and data.required_by is not None
                else None
            ),
            overdue=late,
            days_overdue=(
                _days_between(data.required_by, day)
                if late and data.required_by is not None
                else None
            ),
            potential_cost_impact=data.potential_cost_impact,
            potential_schedule_impact=data.potential_schedule_impact,
            cost_impact=data.answer_cost_impact,
            schedule_impact=data.answer_schedule_impact,
            review_decision=data.review_decision,
            confidentiality=item.confidentiality,
        )
        if only_open and (answered or item.state == "Closed"):
            continue
        if only_overdue and not line.overdue:
            continue
        if only_impact and "yes" not in (line.cost_impact, line.schedule_impact):
            continue
        lines.append(line)
    times = [ln.response_days for ln in lines if ln.response_days is not None]
    return RfiLog(
        scope=scope,
        as_of=day,
        lines=lines,
        total=len(lines),
        answered=sum(1 for ln in lines if ln.answered_on is not None),
        open=sum(
            1 for ln in lines if ln.answered_on is None and ln.state not in ("Closed", "Void")
        ),
        overdue=sum(1 for ln in lines if ln.overdue),
        impact_yes=sum(1 for ln in lines if "yes" in (ln.cost_impact, ln.schedule_impact)),
        average_response_days=round(sum(times) / len(times), 1) if times else None,
    )
