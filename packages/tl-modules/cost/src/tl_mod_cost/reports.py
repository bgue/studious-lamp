"""Reports of the cost module: a budget against its forecast, and records with no cost code.

Both only read (no role check: the entry points need ``document.read``). Each takes a project
scope, and every query is bound to it, so a report of one project never shows another's data.

* ``budget_report``: per cost code, for one unit (quantity, hours or amount), the budget, the
  actual and earned figures, the forecast to complete (FTC) and the estimate at completion (EAC)
  of the latest snapshot that stated the code, the variance (budget minus EAC) and how many records
  are linked to the code. Brief 9 M11: execution records link to a cost code, and their count is
  how a comparison with quantities from welds, joints or work orders is made later.
* ``records_without_cost_code``: the records of one type that no active link ``references`` a
  cost code from (brief 9 M11, "any record can carry a cost code").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection, text

from tl_mod_cost import registry
from tl_mod_cost.names import COST_CODE, COST_RELATION, UNITS

#: The most rows a report returns.
MAX_LINES: Final = 1000

# A link lives in the scope of its ``from`` record and can only point into the same scope
# (``tl_core.services.links``), so the links to the codes of a scope all lie in it: ``l.scope`` in
# the first query only lets the database use the scope index, it is not what keeps projects apart
# (no test can tell the query with and without it). A cost code cannot be voided (the module allows
# no generic ``VoidRecord`` on it), so the codes are not checked for it.
_LINKED_SQL = text(
    "SELECT l.to_id AS code_id, COUNT(DISTINCT l.from_id) AS n FROM cur_links l "
    "JOIN cur_core_record r ON r.id = l.from_id AND r.voided = :no "
    "WHERE l.scope = :scope AND l.relation = :relation AND l.status = 'active' "
    "GROUP BY l.to_id"
)
_UNCODED_SQL = text(
    "SELECT r.id, r.key, r.type, r.title FROM cur_core_record r "
    "WHERE r.scope = :scope AND r.type = :type AND r.voided = :no AND NOT EXISTS ("
    "SELECT 1 FROM cur_links l JOIN cur_core_record c ON c.id = l.to_id "
    "WHERE l.from_id = r.id AND l.relation = :relation AND l.status = 'active' "
    "AND c.type = :cost_code) "
    "ORDER BY (r.key IS NULL), r.key, r.id LIMIT :limit"
)


class BudgetLine(BaseModel):
    """One cost code in one unit. A figure the snapshot did not state is ``None``, never zero."""

    code: str
    title: str
    level: int
    uom: str | None
    period: str | None
    as_of: str | None
    budget: float | None
    actual: float | None
    earned: float | None
    ftc: float | None
    eac: float | None
    #: Budget minus EAC: negative means the forecast is over the budget. ``None`` if either is.
    variance: float | None
    #: Actual as a percentage of the budget, one decimal. ``None`` without a budget above zero.
    percent_spent: float | None
    over_budget: bool
    linked_records: int


@dataclass(frozen=True)
class UncodedRecord:
    id: str
    key: str | None
    record_type: str
    title: str


def _measure(figures: dict[str, float | None], unit: str, measure: str) -> float | None:
    return figures.get(f"{unit}_{measure}")


def budget_report(
    conn: Connection,
    scope: str,
    *,
    unit: str = "quantity",
    parent: str | None = None,
    over_only: bool = False,
    limit: int = MAX_LINES,
) -> list[BudgetLine]:
    """The cost codes of ``scope`` for ``unit`` (``quantity``, ``hours`` or ``amount``), by code.

    ``parent`` keeps the direct children of one code. ``over_only`` keeps the codes whose EAC is
    over their budget. At most ``limit`` rows (and ``MAX_LINES``). ``ValueError`` for another
    ``unit``. Inactive codes are listed: a retired code can still hold figures.
    """
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {', '.join(UNITS)}")
    linked = {
        str(r.code_id): int(r.n)
        for r in conn.execute(_LINKED_SQL, {"scope": scope, "relation": COST_RELATION, "no": False})
    }
    lines: list[BudgetLine] = []
    for row in registry.list_cost_codes(conn, scope):
        if parent is not None and row.parent_code != parent:
            continue
        budget, eac = _measure(row.figures, unit, "budget"), _measure(row.figures, unit, "eac")
        actual = _measure(row.figures, unit, "actual")
        over = budget is not None and eac is not None and eac > budget
        if over_only and not over:
            continue
        lines.append(
            BudgetLine(
                code=row.code,
                title=row.title,
                level=row.level,
                uom=row.uom,
                period=row.period,
                as_of=row.as_of,
                budget=budget,
                actual=actual,
                earned=_measure(row.figures, unit, "earned"),
                ftc=_measure(row.figures, unit, "ftc"),
                eac=eac,
                variance=None if budget is None or eac is None else round(budget - eac, 6),
                percent_spent=(
                    round(actual / budget * 100, 1)
                    if budget is not None and actual is not None and budget > 0
                    else None
                ),
                over_budget=over,
                linked_records=linked.get(row.id, 0),
            )
        )
        if len(lines) >= max(1, min(limit, MAX_LINES)):
            break
    return lines


def records_without_cost_code(
    conn: Connection, scope: str, record_type: str, *, limit: int = MAX_LINES
) -> list[UncodedRecord]:
    """The records of ``record_type`` in ``scope`` with no active ``references`` link to a cost
    code, by key. Void records are left out. At most ``limit`` (and ``MAX_LINES``)."""
    found = conn.execute(
        _UNCODED_SQL,
        {
            "scope": scope,
            "type": record_type,
            "relation": COST_RELATION,
            "cost_code": COST_CODE,
            "no": False,
            "limit": max(1, min(limit, MAX_LINES)),
        },
    )
    return [
        UncodedRecord(
            id=str(r.id),
            key=None if r.key is None else str(r.key),
            record_type=str(r.type),
            title=str(r.title),
        )
        for r in found
    ]
