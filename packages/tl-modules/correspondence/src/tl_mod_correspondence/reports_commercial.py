# ruff: noqa: F401, F841
"""The Commercial register: every notice and claim with its values and its time bar (brief 9, M10).

"Commercial notice/claim register with values (estimated vs assessed)": for each Commercial item
the register shows the clause it is given under, the day the contractor became aware, the time bar
(due date, days left, whether it was met in time), the estimated and the assessed value with the
difference, the schedule impact and the assessment. Totals are per currency: amounts of different
currencies are never added together. Money is exact (``Decimal``), written with two places.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016):
Commercial items are ``restricted``, so a plain user's register is empty. Nothing here writes. The
export to the cost system (``export.py``) builds on these lines.

STUB (P1-I6-T09b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_correspondence import registry, registry_domain, views
from tl_mod_correspondence.handlers.common import today as module_today

_CENT = Decimal("0.01")


class CommercialLine(BaseModel):
    """One Commercial item as the register shows it. Amounts are decimal texts with two places."""

    id: str
    number: str
    subject: str
    subtype: str
    state: str
    direction: str
    confidentiality: str
    clause: str | None  # ``<contract>/<clause number>``
    aware_on: str | None
    issued_on: str | None
    time_bar_due: str | None
    time_bar_days_left: int | None  # in the clock's own day type; negative once overdue
    time_bar_state: str | None  # running, paused, met, cancelled or expired (as of today)
    time_bar_late: bool  # expired, or met after its due date
    currency: str | None
    estimated_value: str | None
    assessed_value: str | None
    variance: str | None  # assessed minus estimated, when both are stated
    schedule_impact_days: int | None
    assessment_status: str | None
    derived_from: str | None  # the number of the RFI it was escalated from, when readable


class CurrencyTotal(BaseModel):
    currency: str
    count: int
    estimated: str
    assessed: str


class CommercialRegister(BaseModel):
    scope: str
    as_of: str
    lines: list[CommercialLine]
    totals: list[CurrencyTotal]  # by currency, in code order
    time_bars_running: int
    time_bars_late: int


def _amount(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT))


def commercial_register(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    only_open: bool = False,
    time_bars_only: bool = False,
    today: str | None = None,
    limit: int = 500,
) -> CommercialRegister:
    """The register of the Commercial items of ``scope`` the viewer may read, newest first.

    ``subtype`` and ``state`` keep the items that have them. ``only_open`` leaves out Closed and
    Void items. ``time_bars_only`` keeps the items whose time bar is still running or paused, or
    was late. ``today`` (an ISO date; the module's today by default) is the day the time bars
    are judged on.
    """
    # STEPS
    # 1. `day = today or module_today()`.
    # 2. `rows = registry_domain.list_commercial(conn, scope, subtype=subtype,
    #    state=state, open_only=only_open, limit=limit)`. The viewer's class filter is
    #    applied inside it (Commercial items are restricted, so a plain user gets no
    #    rows): read the items only this way, never with a query of your own.
    # 3. For each `row`: `item, data = row.item, row.data`. The time bar is the first
    #    clock of the item whose `kind` is `time_bar` among `registry.clocks_of(conn,
    #    item.id)`; make it `bar = views.clock_view(conn, clock, date.fromisoformat(day))`
    #    (it carries `due_on`, `days_left`, `state`, `effective_state` and `closed_on`),
    #    or `bar = None` when there is none.
    # 4. `clause = registry.get_clause(conn, data.contract_clause_id)` when the item names
    #    a clause, else None. `source = registry.get_item(conn, data.derived_from_id)`
    #    when it has a source item (this is None when the viewer may not read it), else
    #    None. `estimated, assessed = _amount(data.estimated_value),
    #    _amount(data.assessed_value)`.
    # 5. `late = bar is not None and (bar.effective_state == "expired" or (bar.state ==
    #    "met" and bar.closed_on is not None and bar.closed_on > bar.due_on))`.
    # 6. Build the `CommercialLine`: `id`, `number`, `subject`, `state`, `direction`,
    #    `confidentiality` from `item`; `subtype=item.subtype or ""`;
    #    `clause=f"{clause.contract}/{clause.clause_number}"` or None; `aware_on` from
    #    `data`; `issued_on=item.issued_on`; `time_bar_due=bar.due_on`,
    #    `time_bar_days_left=bar.days_left`, `time_bar_state=bar.effective_state` (all
    #    None without a bar); `time_bar_late=late`; `currency`, `estimated_value`,
    #    `assessed_value`, `schedule_impact_days`, `assessment_status` from `data`;
    #    `variance=_money(assessed - estimated)` when both are not None, else None;
    #    `derived_from=source.number` or None.
    # 7. With `time_bars_only`, `continue` (skip the line) unless its `time_bar_state` is
    #    `running` or `paused`, or `time_bar_late` is true. Append the others to `lines`.
    # 8. Totals: `counts: dict[str, int]` and `sums: dict[str, list[Decimal]]` (estimated,
    #    assessed). For each kept line that has a `currency`, add 1 to its count, and add
    #    `_amount(line.estimated_value) or Decimal(0)` to the first sum and
    #    `_amount(line.assessed_value) or Decimal(0)` to the second (a currency is never
    #    added to another).
    # 9. Return `CommercialRegister(scope=scope, as_of=day, lines=lines,
    #    totals=[CurrencyTotal(currency=code, count=counts[code], estimated=_money(est),
    #    assessed=_money(ass)) for code, (est, ass) in sorted(sums.items())],
    #    time_bars_running=<lines whose time_bar_state is running or paused>,
    #    time_bars_late=<lines with time_bar_late>)`.
    raise NotImplementedError
