# ruff: noqa: F401, F841
"""The RFI log: every Technical item with its response time and its impact flags (brief 9, M10).

"RFI log with response times and impact flags": for each RFI, technical query or deviation request
the log shows when it was raised, issued, needed and answered, how many days the answer took,
whether it came in time, whether it is overdue, and what the raiser expected and the answerer said
about cost and schedule. It is also the register of the Technical domain: the API, the CLI and the
TUI list these lines.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016): an
item the viewer may not read is not a line and is not counted. Nothing here writes. Time comes in
as ``today`` (an ISO date), so a report is a pure function of the ledger and a day.

STUB (P1-I6-T09a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
    # STEPS
    # 1. `day = today or module_today()` (ISO dates compare as text, so every date test
    #    below is a string comparison).
    # 2. `rows = registry_domain.list_technical(conn, scope, subtype=subtype, state=state,
    #    discipline=discipline, limit=limit)`. The viewer's class filter is applied inside
    #    it: read the items only this way, never with a query of your own, and a row the
    #    viewer may not read is simply not there.
    # 3. For each `row`: `item, data = row.item, row.data`; `answered = data.answered_on
    #    is not None`; `waiting = item.state == ST_AWAITING_RESPONSE`; `late = waiting and
    #    data.required_by is not None and data.required_by < day`.
    # 4. Build the `RfiLogLine`: `id`, `number`, `subject` from `item`;
    #    `subtype=item.subtype or ""`; `discipline` from `data`; `state=item.state`;
    #    `raised_on=item.created_at[:10]`; `issued_on=item.issued_on`; `required_by` and
    #    `answered_on` from `data`; `response_days=_days_between(item.issued_on,
    #    data.answered_on)` when both are not None, else None; `on_time=data.answered_on
    #    <= data.required_by` when both are not None, else None; `overdue=late`;
    #    `days_overdue=_days_between(data.required_by, day)` when `late`, else None;
    #    `potential_cost_impact`, `potential_schedule_impact` from `data`;
    #    `cost_impact=data.answer_cost_impact`,
    #    `schedule_impact=data.answer_schedule_impact`;
    #    `review_decision=data.review_decision`; `confidentiality=item.confidentiality`.
    # 5. Filters, applied to the built line in this order, each with `continue`:
    #    `only_open` skips a line that is `answered` or whose `item.state` is `Closed`;
    #    `only_overdue` skips a line whose `overdue` is false; `only_impact` skips a line
    #    when `"yes"` is neither its `cost_impact` nor its `schedule_impact`. Keep the
    #    others in `lines`, in the order `list_technical` gave them.
    # 6. `times` is the `response_days` of the kept lines that have one. Return
    #    `RfiLog(scope=scope, as_of=day, lines=lines, total=len(lines), answered=<kept
    #    lines with an answered_on>, open=<kept lines with no answered_on whose state is
    #    neither Closed nor Void>, overdue=<kept lines with overdue>, impact_yes=<kept
    #    lines with "yes" as cost_impact or schedule_impact>,
    #    average_response_days=round(sum(times) / len(times), 1) if times else None)`.
    raise NotImplementedError
