"""Progress rollup on read: IWP to CWP to WBS node to cost code (P2-I5 S3, decision D17).

Nothing is stored and no event is written: the figures are computed from the stored IWP progress
rows each time. The math rules are those of ``engine`` (F9): the IWP figure is the stored,
unfiltered one (rule 1); a null item hour weighs the mean of the set ones, none set weighs 1 each
(rule 2); sums are exact (``Fraction``) and a figure is rounded once, half-up, at its output
(rule 3); the cap of 100 is per IWP only, so earned hours are not capped to the CWP budget.

The spreading over WBS nodes and cost codes is ``tl_mod_awp.rollup.compute``, called with the CWP
earned hours as its ``budgets``. Without a ``viewer`` a budget figure is the stored
``cur_awp_rollup`` row. With a ``viewer`` nothing hidden may show, not even as a note: the roll-up
is computed from the CWPs, IWPs, WBS nodes and cost codes the viewer can open only (the stored
totals add the hidden ones and are not read), so the answer is the one a project without them
would give. Earned hours that reach no cost code (unmapped node, no allocation, a hidden node)
are the one ``Unallocated`` line, last, so the lines add up to the rounded total of the packages.

Reads only: one statement per table, never one per IWP.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Final

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.confidentiality import Viewer

from tl_mod_awp import rollup
from tl_mod_awp.names import (
    CWP,
    CWP_ALLOCATION_TABLE,
    CWP_TABLE,
    IWP,
    IWP_CANCELLED,
    IWP_PROGRESS_TABLE,
    IWP_SPLIT_STATE,
    IWP_TABLE,
    RULE_LINK_SOURCE,
    SCI_VOID,
    SCOPE_ITEM,
    SCOPE_RELATION,
    WBS_NODE_TABLE,
)
from tl_mod_awp.progress.engine import ScopeItemRow, _weights, round_half_up

NOTE_NO_BUDGET: Final = "no budget rollup yet"
UNALLOCATED_CODE: Final = "Unallocated"
_PRECISION: Final = 60

_HEAD_SQL = text("SELECT COALESCE(MAX(seq), 0) FROM events")
_CWPS_SQL = text(
    "SELECT c.id AS id, r.key AS key, c.budget_hours AS budget_hours "
    f"FROM {CWP_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.scope = :scope AND r.type = :type AND r.voided = :voided ORDER BY r.key, r.id"
)
_IWPS_SQL = text(
    f"SELECT i.id AS id, i.cwp_id AS cwp_id, r.status AS status FROM {IWP_TABLE} i "
    "JOIN cur_core_record r ON r.id = i.id "
    "WHERE i.scope = :scope AND r.type = :type AND r.voided = :voided ORDER BY i.id"
)
_ITEMS_SQL = text(
    "SELECT l.to_id AS iwp_id, r.id AS id, r.status AS status, s.est_hours AS est_hours "
    "FROM cur_links l JOIN cur_core_record r ON r.id = l.from_id "
    "JOIN cur_awp_scope_item s ON s.id = r.id "
    f"JOIN {IWP_TABLE} i ON i.id = l.to_id "
    "WHERE i.scope = :scope AND l.relation = :relation AND l.source = :source "
    "AND l.status = 'active' AND r.type = :item_type AND r.voided = :voided "
    "ORDER BY l.to_id, r.key, r.id"
)
_PROGRESS_SQL = text(f"SELECT iwp_id, earned_pct FROM {IWP_PROGRESS_TABLE} WHERE scope = :scope")
_NODES_SQL = text(f"SELECT id, parent_id FROM {WBS_NODE_TABLE} WHERE scope = :scope")
_MAPPING_SQL = text(
    "SELECT node_id, cost_code_id, percent FROM cur_awp_wbs_allocation WHERE scope = :scope"
)
_ALLOC_SQL = text(
    f"SELECT cwp_id, wbs_node_id, percent FROM {CWP_ALLOCATION_TABLE} WHERE scope = :scope"
)
_STORED_SQL = text(
    f"SELECT subject_id, line, cost_code_id, value FROM {rollup.ROLLUP_TABLE} "
    "WHERE scope = :scope AND subject_kind = :kind AND measure = :measure"
)
_CODES_SQL = text("SELECT id, code FROM cur_cost_costcode WHERE scope = :scope")


@dataclass(frozen=True)
class CwpProgress:
    cwp_id: str
    key: str
    iwps: int
    earned_hours: Decimal  # 1 dp, half-up at output
    hours: Decimal  # 1 dp, half-up at output


@dataclass(frozen=True)
class NodeProgress:
    node_id: str
    earned_hours: Decimal
    budget_hours: Decimal | None
    pct: Decimal | None  # earned over budget in percent, 1 dp; None without a budget


@dataclass(frozen=True)
class CostLine:
    cost_code_id: str | None  # None is the unallocated line
    code: str | None
    earned_hours: Decimal
    budget_hours: Decimal | None


@dataclass(frozen=True)
class ProgressRollup:
    scope: str
    as_of_seq: int
    cwps: list[CwpProgress]
    nodes: list[NodeProgress]
    lines: list[CostLine]
    notes: list[str]


def _decimal(value: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return Decimal(value.numerator) / Decimal(value.denominator)


def _item_hours(raw: object) -> Fraction | None:
    return None if raw in (None, "") else Fraction(Decimal(str(raw)))


def _iwp_hours(items: list[ScopeItemRow]) -> Fraction:
    """Rule 2: the hours of an IWP are the weights of its items."""
    return sum(_weights(items), Fraction(0))


def progress_rollup(
    conn: Connection, scope: str, *, viewer: Viewer | None = None
) -> ProgressRollup:
    """Earned hours of ``scope`` by CWP, WBS node and cost code (see the module docstring).

    ``viewer``: records it cannot open are absent, as if they did not exist (no note, no count);
    the figure of an IWP it can open does not change with the items hidden inside it.
    """
    as_of = int(conn.execute(_HEAD_SQL).scalar_one())  # read first: the data is at least this new
    params = {"scope": scope}
    notes: list[str] = []
    cwp_all = [
        (str(r.id), str(r.key or ""), None if r.budget_hours in (None, "") else str(r.budget_hours))
        for r in conn.execute(_CWPS_SQL, {**params, "type": CWP, "voided": False})
    ]
    iwp_rows = [
        r
        for r in conn.execute(_IWPS_SQL, {**params, "type": IWP, "voided": False})
        if r.cwp_id is not None and str(r.status or "") not in (IWP_CANCELLED, IWP_SPLIT_STATE)
    ]
    parents = {str(r.id): r.parent_id for r in conn.execute(_NODES_SQL, params)}
    mapping: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for r in conn.execute(_MAPPING_SQL, params):
        mapping[str(r.node_id)].append((str(r.cost_code_id), Decimal(str(r.percent))))
    allocations = [
        (str(r.cwp_id), str(r.wbs_node_id), Decimal(str(r.percent)))
        for r in conn.execute(_ALLOC_SQL, params)
    ]
    codes = {str(r.id): str(r.code) for r in conn.execute(_CODES_SQL, params)}
    if viewer is not None:
        hidden = confidentiality.hidden_among(
            conn,
            [c for c, _, _ in cwp_all]
            + [str(r.id) for r in iwp_rows]
            + list(parents)
            + list(codes),
            viewer,
        )
        cwp_all = [c for c in cwp_all if c[0] not in hidden]
        iwp_rows = [r for r in iwp_rows if str(r.id) not in hidden]
        parents = {n: (None if p in hidden else p) for n, p in parents.items() if n not in hidden}
        mapping = defaultdict(
            list,
            {
                n: [(c, pc) for c, pc in lines if c not in hidden]
                for n, lines in mapping.items()
                if n not in hidden
            },
        )
        allocations = [a for a in allocations if a[0] not in hidden and a[1] not in hidden]
        codes = {i: c for i, c in codes.items() if i not in hidden}
    cwp_rows = [(c, k) for c, k, _ in cwp_all]
    visible_cwps = {c for c, _ in cwp_rows}
    iwp_cwp = {str(r.id): str(r.cwp_id) for r in iwp_rows if str(r.cwp_id) in visible_cwps}

    items: dict[str, list[ScopeItemRow]] = defaultdict(list)
    for r in conn.execute(
        _ITEMS_SQL,
        {
            **params,
            "relation": SCOPE_RELATION,
            "source": RULE_LINK_SOURCE,
            "item_type": SCOPE_ITEM,
            "voided": False,
        },
    ):
        state = str(r.status or "")
        if state == SCI_VOID or str(r.iwp_id) not in iwp_cwp:
            continue
        hours = _item_hours(r.est_hours)
        items[str(r.iwp_id)].append(
            ScopeItemRow(
                id=str(r.id),
                key="",
                state=state,
                commodity="",
                hours=hours,
                hours_text=None if hours is None else Decimal(str(r.est_hours)),
            )
        )
    stored = {
        str(r.iwp_id): Fraction(Decimal(str(r.earned_pct)))
        for r in conn.execute(_PROGRESS_SQL, params)
    }

    count: dict[str, int] = defaultdict(int)
    earned: dict[str, Fraction] = defaultdict(Fraction)
    cwp_hours: dict[str, Fraction] = defaultdict(Fraction)
    for iwp, cwp in iwp_cwp.items():
        weight = _iwp_hours(items.get(iwp, []))
        count[cwp] += 1
        cwp_hours[cwp] += weight
        earned[cwp] += stored.get(iwp, Fraction(0)) / 100 * weight  # no stored row earns 0
    cwps = [
        CwpProgress(
            cwp_id=c,
            key=k,
            iwps=count[c],
            earned_hours=round_half_up(earned[c]),
            hours=round_half_up(cwp_hours[c]),
        )
        for c, k in cwp_rows
        if count[c]
    ]

    budgets = {c.cwp_id: _decimal(earned[c.cwp_id]) for c in cwps}
    figures = rollup.compute(parents, mapping, budgets, allocations)
    roots = {n for n, p in parents.items() if p is None or p not in parents}
    node_budget: dict[str, Decimal] = {}
    line_budget: dict[rollup.Key, Decimal] = {}
    if viewer is not None:  # computed from what the viewer can open; the stored rows are not read
        cwp_budget = {c: Decimal(b) for c, _, b in cwp_all if b is not None}
        for node, figure in rollup.compute(parents, mapping, cwp_budget, allocations).items():
            node_budget[node] = Decimal(figure.total)
            if node in roots:
                for key, value in figure.lines:
                    line_budget[key] = line_budget.get(key, Decimal(0)) + Decimal(value)
    else:
        for r in conn.execute(
            _STORED_SQL, {**params, "kind": rollup.SUBJECT_KIND, "measure": rollup.MEASURE}
        ):
            value = Decimal(str(r.value))
            if r.line == rollup.LINE_TOTAL:
                node_budget[str(r.subject_id)] = value
            elif str(r.subject_id) in roots:
                key = None if r.line == rollup.LINE_UNALLOCATED else str(r.cost_code_id)
                line_budget[key] = line_budget.get(key, Decimal(0)) + value

    nodes: list[NodeProgress] = []
    line_earned: dict[rollup.Key, Decimal] = defaultdict(Decimal)
    for node in sorted(figures):
        figure = figures[node]
        total = Decimal(figure.total)
        budget = node_budget.get(node)
        pct = None
        if budget:
            pct = round_half_up(Fraction(total) / Fraction(budget) * 100)
        nodes.append(NodeProgress(node, total, budget, pct))
        if node in roots:
            for key, value in figure.lines:
                line_earned[key] += Decimal(value)
    if viewer is None and (
        not node_budget or any(n.budget_hours is None and n.earned_hours for n in nodes)
    ):
        notes.append(NOTE_NO_BUDGET)

    # Rule 3: the lines and the Unallocated line add up to the rounded total of the packages. The
    # coded lines are the rounded figures of ``compute``; Unallocated takes what is left of the
    # rounded total (the unmapped nodes, a package without allocation, a hidden node).
    coded = sorted(
        (k for k in set(line_earned) | set(line_budget) if k is not None), key=rollup.line_order
    )
    lines = [
        CostLine(k, codes.get(k), line_earned.get(k, Decimal("0.0")), line_budget.get(k))
        for k in coded
    ]
    lines.sort(key=lambda ln: (ln.code or "", ln.cost_code_id or ""))
    total = round_half_up(sum(earned[c] for c in budgets) if budgets else Fraction(0))
    rest = total - sum((ln.earned_hours for ln in lines), Decimal("0.0"))
    if rest != 0 or None in line_budget:
        lines.append(CostLine(None, UNALLOCATED_CODE, rest, line_budget.get(None)))
    return ProgressRollup(scope, as_of, cwps, nodes, lines, notes)
