"""The Commercial register: every notice and claim with its values and its time bar (brief 9, M10).

"Commercial notice/claim register with values (estimated vs assessed)": for each Commercial item
the register shows the clause it is given under, the day the contractor became aware, the time bar
(due date, days left, whether it was met in time), the estimated and the assessed value with the
difference, the schedule impact and the assessment. Totals are per currency: amounts of different
currencies are never added together. Money is exact (``Decimal``), written with two places.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016):
Commercial items are ``restricted``, so a plain user's register is empty. Nothing here writes. The
export to the cost system (``export.py``) builds on these lines.
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
    day = today or module_today()
    rows = registry_domain.list_commercial(
        conn, scope, subtype=subtype, state=state, open_only=only_open, limit=limit
    )
    lines: list[CommercialLine] = []
    for row in rows:
        item, data = row.item, row.data
        bar_clock = next(
            (c for c in registry.clocks_of(conn, item.id) if c.kind == "time_bar"), None
        )
        bar = (
            None
            if bar_clock is None
            else views.clock_view(conn, bar_clock, date.fromisoformat(day))
        )
        clause = (
            registry.get_clause(conn, data.contract_clause_id) if data.contract_clause_id else None
        )
        source = registry.get_item(conn, data.derived_from_id) if data.derived_from_id else None
        estimated, assessed = _amount(data.estimated_value), _amount(data.assessed_value)
        late = bar is not None and (
            bar.effective_state == "expired"
            or (bar.state == "met" and bar.closed_on is not None and bar.closed_on > bar.due_on)
        )
        line = CommercialLine(
            id=item.id,
            number=item.number,
            subject=item.subject,
            subtype=item.subtype or "",
            state=item.state,
            direction=item.direction,
            confidentiality=item.confidentiality,
            clause=f"{clause.contract}/{clause.clause_number}" if clause is not None else None,
            aware_on=data.aware_on,
            issued_on=item.issued_on,
            time_bar_due=bar.due_on if bar is not None else None,
            time_bar_days_left=bar.days_left if bar is not None else None,
            time_bar_state=bar.effective_state if bar is not None else None,
            time_bar_late=late,
            currency=data.currency,
            estimated_value=data.estimated_value,
            assessed_value=data.assessed_value,
            variance=(
                _money(assessed - estimated)
                if assessed is not None and estimated is not None
                else None
            ),
            schedule_impact_days=data.schedule_impact_days,
            assessment_status=data.assessment_status,
            derived_from=source.number if source is not None else None,
        )
        if time_bars_only and not (
            line.time_bar_state in ("running", "paused") or line.time_bar_late
        ):
            continue
        lines.append(line)

    counts: dict[str, int] = {}
    sums: dict[str, list[Decimal]] = {}
    for line in lines:
        if line.currency is None:
            continue
        counts[line.currency] = counts.get(line.currency, 0) + 1
        est_sum, ass_sum = sums.setdefault(line.currency, [Decimal(0), Decimal(0)])
        sums[line.currency] = [
            est_sum + (_amount(line.estimated_value) or Decimal(0)),
            ass_sum + (_amount(line.assessed_value) or Decimal(0)),
        ]

    return CommercialRegister(
        scope=scope,
        as_of=day,
        lines=lines,
        totals=[
            CurrencyTotal(
                currency=code,
                count=counts[code],
                estimated=_money(est),
                assessed=_money(ass),
            )
            for code, (est, ass) in sorted(sums.items())
        ],
        time_bars_running=sum(1 for ln in lines if ln.time_bar_state in ("running", "paused")),
        time_bars_late=sum(1 for ln in lines if ln.time_bar_late),
    )
