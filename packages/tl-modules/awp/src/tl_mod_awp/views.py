"""Reads of the awp module (spec m3-wbs-cwp section 5): the views the API, the CLI and the MCP tools
return. Filled by ticket T10.

Every function takes a connection and a project scope and reads through the viewer's class filter
(ADR-0016): a record the viewer may not read is absent, never counted and never named. A reference
inside a view (the area of a CWP, the node of an allocation, the area of a path step) is named only
when the record it points to is readable; otherwise the reference is left out. Nothing here writes
and nothing checks an access word: the entry points do.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Final

from pydantic import BaseModel, Field
from sqlalchemy import Connection, bindparam, text
from tl_core.confidentiality import hidden_among, not_hidden
from tl_mod_schedule.resolver import ActivityLink, links_to_activities

from tl_mod_awp.common import resolve_code
from tl_mod_awp.names import (
    CWA,
    CWA_TABLE,
    CWP,
    CWP_ALLOCATION_TABLE,
    CWP_TABLE,
    EWP,
    PACKAGE_TABLE,
    PATH,
    PATH_STEP_TABLE,
    PATH_TABLE,
    PWP,
    ST_PLANNED,
    WBS_NODE,
    WBS_NODE_TABLE,
)

#: The rollup table (``cur_awp_rollup``): one row per subject, line and cost code.
ROLLUP_TABLE: Final = "cur_awp_rollup"
ROLLUP_MEASURE: Final = "budget_hours"
ROLLUP_TOTAL: Final = "total"
ROLLUP_COST_CODE: Final = "cost_code"
ROLLUP_UNALLOCATED: Final = "unallocated"
#: The package kind words a view takes and returns, and the record type of each.
KIND_TYPES: Final = {"EWP": EWP, "PWP": PWP}
KIND_WORDS: Final = {EWP: "EWP", PWP: "PWP"}
CONSTRAINT_RELATION: Final = "requires"


# --- models ---------------------------------------------------------------------------------------


class PackageRow(BaseModel):
    """An EWP or PWP reference: the package its project keeps, with the status it reports."""

    id: str
    kind: str  # "EWP" or "PWP"
    package_no: str
    status_text: str | None
    forecast_date: str | None
    actual_date: str | None
    constraint_source: bool
    source_system: str | None
    title: str = ""  # the package record's title
    # the numbers of the readable, non-void CWPs with a live `requires` link to it, sorted
    cwps: list[str] = Field(default_factory=list)


class CwpRow(BaseModel):
    """A construction work package (CWP) as the list shows it."""

    id: str
    number: str  # the CWP number (the record key)
    title: str
    state: str  # NULL reads as Planned
    discipline: str | None
    cwa: str | None  # the code of its construction work area, when the viewer may read it
    planned_start: str | None
    planned_finish: str | None
    budget_hours: Decimal | None
    allocated: bool = False  # the CWP has >= 1 allocation to a readable, non-void WBS node


class CwpAllocation(BaseModel):
    wbs_code: str
    percent: Decimal


class CwpDetail(CwpRow):
    """A CWP with its fields, its WBS allocation, the packages it requires and its activities."""

    contractor_text: str | None
    quantities: Any
    allocations: list[CwpAllocation]
    packages: list[PackageRow]
    activities: list[ActivityLink]


class CwaRow(BaseModel):
    """A construction work area (CWA)."""

    id: str
    code: str
    title: str
    location_text: str | None
    retired: bool


class WbsCwp(BaseModel):
    """A CWP allocated to a leaf node: its number, subject, percent and the hours it takes there."""

    number: str
    title: str
    percent: Decimal
    hours: Decimal | None  # budget_hours * percent / 100, 2 places, half-even; None without budget


class WbsRow(BaseModel):
    """A WBS node with its rollup: ``total_hours`` is None when the node has no rollup rows."""

    id: str
    code: str
    title: str
    parent_code: str | None
    depth: int
    position: int
    retired: bool
    total_hours: Decimal | None
    by_cost_code: dict[str, Decimal]  # the cost code's code to its budget hours
    cwp_count: int = 0  # distinct readable, non-void CWPs allocated to the node or any descendant
    # the CWPs allocated to a leaf, filled by wbs_detail only; [] in wbs_tree and for a parent
    cwps: list[WbsCwp] = Field(default_factory=list)


class PathStep(BaseModel):
    position: int
    cwa: str | None  # the area's code, when the viewer may read the area
    reason_code: str | None
    actor: str
    recorded_at: str


class PathView(BaseModel):
    """The path of construction (one per project): the steps of one version, in position order."""

    id: str
    key: str
    title: str
    version: int
    current_version: int
    steps: list[PathStep]


class PathVersion(BaseModel):
    version: int
    recorded_at: str
    actor: str
    step_count: int
    is_current: bool


# --- row helpers ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Node:
    parent_id: str | None
    row: WbsRow


@dataclass(frozen=True)
class _PathHead:
    id: str
    key: str
    title: str
    current_version: int


@dataclass(frozen=True)
class _Allocation:
    """One CWP allocation to a readable, non-void WBS node, of a readable, non-void CWP."""

    cwp_id: str
    number: str
    title: str
    budget_hours: Decimal | None
    node_id: str
    percent: Decimal


@dataclass(frozen=True)
class _CwpIndex:
    counted: dict[str, set[str]]  # node id: the CWP ids allocated to it or to a descendant
    own: dict[str, list[_Allocation]]  # node id: the allocations to it
    parents: set[str]  # the node ids that are the parent of some node (a node not in it is a leaf)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _hidden(conn: Connection, ids: set[str]) -> set[str]:
    """The ids the viewer must not read (a reference is named only when its record is readable)."""
    return hidden_among(conn, sorted(ids)) if ids else set()


# --- work packages --------------------------------------------------------------------------------

_CWP_SQL = (
    "SELECT r.id, r.key, r.title, COALESCE(r.status, :planned) AS state, c.discipline, "
    "c.cwa_id, a.code AS cwa_code, c.planned_start, c.planned_finish, c.budget_hours, "
    "c.quantities_json, c.contractor_text "
    f"FROM {CWP_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    f"LEFT JOIN {CWA_TABLE} a ON a.id = c.cwa_id "
)


def _cwp_rows(
    conn: Connection, scope: str, where: str, params: dict[str, Any]
) -> list[tuple[Any, CwpRow]]:
    """The live CWPs of ``scope`` the viewer may read, by number, as ``(row, CwpRow)`` pairs (the
    row keeps the fields a detail needs). ``where`` is a condition written here, never user
    input."""
    visible, extra = not_hidden("r.id")
    rows = list(
        conn.execute(
            text(
                f"{_CWP_SQL} WHERE r.scope = :scope AND r.type = :type AND r.voided = :voided "
                f"AND {visible}{where} ORDER BY r.key"
            ),
            {
                "planned": ST_PLANNED,
                "scope": scope,
                "type": CWP,
                "voided": False,
                **params,
                **extra,
            },
        ).mappings()
    )
    hidden_cwa = _hidden(conn, {str(r["cwa_id"]) for r in rows if r["cwa_id"] is not None})
    pairs: list[tuple[Any, CwpRow]] = []
    for r in rows:
        cwa_id = None if r["cwa_id"] is None else str(r["cwa_id"])
        cwa = None if cwa_id is None or cwa_id in hidden_cwa else _text(r["cwa_code"])
        pairs.append(
            (
                r,
                CwpRow(
                    id=str(r["id"]),
                    number=str(r["key"]),
                    title=str(r["title"]),
                    state=str(r["state"]),
                    discipline=_text(r["discipline"]),
                    cwa=cwa,
                    planned_start=_text(r["planned_start"]),
                    planned_finish=_text(r["planned_finish"]),
                    budget_hours=_dec(r["budget_hours"]),
                ),
            )
        )
    return pairs


def _cwp_allocations(conn: Connection, scope: str, cwp_id: str) -> list[CwpAllocation]:
    rows = list(
        conn.execute(
            text(
                f"SELECT n.id, n.code, a.percent FROM {CWP_ALLOCATION_TABLE} a "
                f"JOIN {WBS_NODE_TABLE} n ON n.id = a.wbs_node_id "
                "JOIN cur_core_record r ON r.id = n.id "
                "WHERE a.scope = :scope AND a.cwp_id = :cwp AND r.voided = :voided "
                "ORDER BY n.code"
            ),
            {"scope": scope, "cwp": cwp_id, "voided": False},
        ).mappings()
    )
    hidden = _hidden(conn, {str(r["id"]) for r in rows})
    return [
        CwpAllocation(wbs_code=str(r["code"]), percent=Decimal(str(r["percent"])))
        for r in rows
        if str(r["id"]) not in hidden
    ]


def _live_allocations(conn: Connection, scope: str) -> list[_Allocation]:
    """The allocations of ``scope`` to a non-void WBS node and of a non-void CWP, both the viewer
    may read (one query; one hidden check over the node ids and one over the CWP ids)."""
    rows = list(
        conn.execute(
            text(
                "SELECT a.cwp_id, cr.key, cr.title, c.budget_hours, a.wbs_node_id, a.percent "
                f"FROM {CWP_ALLOCATION_TABLE} a "
                f"JOIN {CWP_TABLE} c ON c.id = a.cwp_id "
                "JOIN cur_core_record cr ON cr.id = c.id "
                f"JOIN {WBS_NODE_TABLE} n ON n.id = a.wbs_node_id "
                "JOIN cur_core_record nr ON nr.id = n.id "
                "WHERE a.scope = :scope AND cr.voided = :voided AND nr.voided = :voided"
            ),
            {"scope": scope, "voided": False},
        ).mappings()
    )
    hidden_nodes = _hidden(conn, {str(r["wbs_node_id"]) for r in rows})
    hidden_cwps = _hidden(conn, {str(r["cwp_id"]) for r in rows})
    return [
        _Allocation(
            cwp_id=str(r["cwp_id"]),
            number=str(r["key"]),
            title=str(r["title"]),
            budget_hours=_dec(r["budget_hours"]),
            node_id=str(r["wbs_node_id"]),
            percent=Decimal(str(r["percent"])),
        )
        for r in rows
        if str(r["wbs_node_id"]) not in hidden_nodes and str(r["cwp_id"]) not in hidden_cwps
    ]


def _package_rows(
    conn: Connection, scope: str, kinds: tuple[str, ...], where: str, params: dict[str, Any]
) -> list[PackageRow]:
    """The EWP and PWP references of ``kinds`` in ``scope`` the viewer may read, by package number.
    ``where`` is a condition written here, never user input."""
    fetched: list[tuple[str, Any]] = []
    for record_type in kinds:
        visible, extra = not_hidden("p.id")
        rows = conn.execute(
            text(
                "SELECT p.id, r.title, p.package_no, p.status_text, p.forecast_date, "
                "p.actual_date, p.constraint_source, p.source_system "
                f"FROM {PACKAGE_TABLE[record_type]} p JOIN cur_core_record r ON r.id = p.id "
                f"WHERE p.scope = :scope AND r.voided = :voided AND {visible}{where}"
            ),
            {"scope": scope, "voided": False, **params, **extra},
        ).mappings()
        fetched.extend((record_type, r) for r in rows)
    requiring = _package_cwps(conn, scope, [str(r["id"]) for _, r in fetched])
    found = [
        PackageRow(
            id=str(r["id"]),
            kind=KIND_WORDS[record_type],
            title=str(r["title"]),
            package_no=str(r["package_no"]),
            status_text=_text(r["status_text"]),
            forecast_date=_text(r["forecast_date"]),
            actual_date=_text(r["actual_date"]),
            constraint_source=bool(r["constraint_source"]),
            source_system=_text(r["source_system"]),
            cwps=requiring.get(str(r["id"]), []),
        )
        for record_type, r in fetched
    ]
    found.sort(key=lambda p: (p.package_no, p.kind))
    return found


def _package_cwps(conn: Connection, scope: str, package_ids: list[str]) -> dict[str, list[str]]:
    """The numbers of the readable, non-void CWPs with a live ``requires`` link to each package,
    sorted (one query for all packages)."""
    if not package_ids:
        return {}
    rows = list(
        conn.execute(
            text(
                "SELECT l.to_id, cr.id AS cwp_id, cr.key FROM cur_links l "
                f"JOIN {CWP_TABLE} c ON c.id = l.from_id "
                "JOIN cur_core_record cr ON cr.id = c.id "
                "WHERE l.scope = :scope AND l.relation = :relation AND l.status <> 'retracted' "
                "AND cr.voided = :voided AND l.to_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {
                "scope": scope,
                "relation": CONSTRAINT_RELATION,
                "voided": False,
                "ids": sorted(set(package_ids)),
            },
        ).mappings()
    )
    hidden = _hidden(conn, {str(r["cwp_id"]) for r in rows})
    numbers: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if str(r["cwp_id"]) not in hidden:
            numbers[str(r["to_id"])].add(str(r["key"]))
    return {package: sorted(found) for package, found in numbers.items()}


def _kinds(kind: str | None) -> tuple[str, ...]:
    if kind is None:
        return (EWP, PWP)
    if kind not in KIND_TYPES:
        raise ValueError(f"unknown package kind {kind!r}; the kinds are EWP and PWP")
    return (KIND_TYPES[kind],)


def cwp_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    discipline: str | None = None,
    cwa: str | None = None,
) -> list[CwpRow]:
    """The CWPs of ``scope`` by number, void ones left out. ``state`` compares the state as shown
    (NULL is Planned), ``discipline`` the discipline, ``cwa`` the area's code. An area the viewer
    may not read, or none, answers ``[]``."""
    where = ""
    params: dict[str, Any] = {}
    if state is not None:
        where += " AND COALESCE(r.status, :planned) = :state"
        params["state"] = state
    if discipline is not None:
        where += " AND c.discipline = :discipline"
        params["discipline"] = discipline
    if cwa is not None:
        area = resolve_code(conn, scope, CWA, cwa)
        if area is None:
            return []
        where += " AND c.cwa_id = :cwa_id"
        params["cwa_id"] = area
    rows = [row for _, row in _cwp_rows(conn, scope, where, params)]
    allocated = {alloc.cwp_id for alloc in _live_allocations(conn, scope)}
    for row in rows:
        row.allocated = row.id in allocated
    return rows


def cwp_detail(conn: Connection, scope: str, number: str) -> CwpDetail | None:
    """One CWP by number with its fields, allocation, required packages and activity links.
    ``None`` for a missing, hidden, voided or other-project CWP (the same answer for each)."""
    pairs = _cwp_rows(conn, scope, " AND r.key = :number", {"number": number})
    if not pairs:
        return None
    raw, base = pairs[0]
    cwp_id = base.id
    allocations = _cwp_allocations(conn, scope, cwp_id)
    base.allocated = bool(allocations)
    return CwpDetail(
        **base.model_dump(),
        contractor_text=_text(raw["contractor_text"]),
        quantities=None
        if raw["quantities_json"] is None
        else json.loads(str(raw["quantities_json"])),
        allocations=allocations,
        packages=_package_rows(
            conn,
            scope,
            (EWP, PWP),
            " AND p.id IN (SELECT l.to_id FROM cur_links l WHERE l.scope = :scope "
            "AND l.from_id = :cwp AND l.relation = :relation AND l.status <> 'retracted')",
            {"cwp": cwp_id, "relation": CONSTRAINT_RELATION},
        ),
        activities=links_to_activities(conn, cwp_id, scope=scope),
    )


def package_list(conn: Connection, scope: str, *, kind: str | None = None) -> list[PackageRow]:
    """The EWP and PWP references of ``scope`` by package number. ``kind`` is ``EWP`` or ``PWP``;
    any other word is a ``ValueError``."""
    return _package_rows(conn, scope, _kinds(kind), "", {})


# --- construction work areas ----------------------------------------------------------------------


def cwa_list(conn: Connection, scope: str) -> list[CwaRow]:
    """The construction work areas of ``scope`` by code, retired ones included (flagged)."""
    visible, extra = not_hidden("c.id")
    rows = conn.execute(
        text(
            "SELECT c.id, c.code, r.title, c.location_text, c.retired "
            f"FROM {CWA_TABLE} c JOIN cur_core_record r ON r.id = c.id "
            f"WHERE c.scope = :scope AND r.type = :type AND r.voided = :voided AND {visible} "
            "ORDER BY c.code"
        ),
        {"scope": scope, "type": CWA, "voided": False, **extra},
    ).mappings()
    return [
        CwaRow(
            id=str(r["id"]),
            code=str(r["code"]),
            title=str(r["title"]),
            location_text=_text(r["location_text"]),
            retired=bool(r["retired"]),
        )
        for r in rows
    ]


# --- WBS ------------------------------------------------------------------------------------------


def _cwp_index(conn: Connection, scope: str) -> _CwpIndex:
    """The CWPs allocated to each WBS node of ``scope``, counted up the ``parent_id`` chain. Two
    queries for the whole scope (the allocations, the node chain), so the tree and one node read
    the same counts."""
    parent_of = {
        str(r["id"]): None if r["parent_id"] is None else str(r["parent_id"])
        for r in conn.execute(
            text(f"SELECT n.id, n.parent_id FROM {WBS_NODE_TABLE} n WHERE n.scope = :scope"),
            {"scope": scope},
        ).mappings()
    }
    counted: dict[str, set[str]] = defaultdict(set)
    own: dict[str, list[_Allocation]] = defaultdict(list)
    for alloc in _live_allocations(conn, scope):
        own[alloc.node_id].append(alloc)
        node: str | None = alloc.node_id
        seen: set[str] = set()
        while node is not None and node not in seen:
            seen.add(node)
            counted[node].add(alloc.cwp_id)
            node = parent_of.get(node)
    parents = {p for p in parent_of.values() if p is not None}
    return _CwpIndex(counted=dict(counted), own=dict(own), parents=parents)


def _wbs_nodes(
    conn: Connection, scope: str, where: str, params: dict[str, Any], index: _CwpIndex
) -> list[_Node]:
    """The live WBS nodes of ``scope`` the viewer may read, with their rollup and CWP count, in
    table order. ``where`` is a condition written here, never user input."""
    visible, extra = not_hidden("n.id")
    rows = list(
        conn.execute(
            text(
                "SELECT n.id, n.code, r.title, n.parent_id, n.depth, n.position, n.retired "
                f"FROM {WBS_NODE_TABLE} n JOIN cur_core_record r ON r.id = n.id "
                "WHERE n.scope = :scope AND r.type = :type AND r.voided = :voided "
                f"AND {visible}{where}"
            ),
            {"scope": scope, "type": WBS_NODE, "voided": False, **params, **extra},
        ).mappings()
    )
    ids = {str(r["id"]) for r in rows}
    totals, by_code = _rollup(conn, scope, ids)
    parent_ids = {str(r["parent_id"]) for r in rows if r["parent_id"] is not None}
    parents = _parent_codes(conn, scope, parent_ids)
    nodes: list[_Node] = []
    for r in rows:
        node_id = str(r["id"])
        parent_id = None if r["parent_id"] is None else str(r["parent_id"])
        nodes.append(
            _Node(
                parent_id=parent_id,
                row=WbsRow(
                    id=node_id,
                    code=str(r["code"]),
                    title=str(r["title"]),
                    parent_code=None if parent_id is None else parents.get(parent_id),
                    depth=int(r["depth"]),
                    position=int(r["position"]),
                    retired=bool(r["retired"]),
                    total_hours=totals.get(node_id),
                    by_cost_code=by_code.get(node_id, {}),
                    cwp_count=len(index.counted.get(node_id, ())),
                ),
            )
        )
    return nodes


def _parent_codes(conn: Connection, scope: str, parent_ids: set[str]) -> dict[str, str]:
    """The codes of the parents a node names, only for parents the viewer may read."""
    readable = sorted(parent_ids - _hidden(conn, parent_ids))
    if not readable:
        return {}
    statement = text(
        f"SELECT id, code FROM {WBS_NODE_TABLE} WHERE scope = :scope AND id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = conn.execute(statement, {"scope": scope, "ids": readable})
    return {str(r[0]): str(r[1]) for r in rows}


def _rollup(
    conn: Connection, scope: str, node_ids: set[str]
) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]]]:
    """Budget hours per node: the total, and the lines per cost code (one query for all nodes).
    A later rollup row (higher ``as_of_seq``) replaces an earlier one of the same line.

    A node with a cost-code line the viewer may not read gets, as its total, the visible
    cost-code lines plus its unallocated line; the stored total would reveal the hidden hours.
    """
    if not node_ids:
        return {}, {}
    statement = text(
        "SELECT u.subject_id, u.line, u.cost_code_id, u.value, c.key AS cost_code "
        f"FROM {ROLLUP_TABLE} u LEFT JOIN cur_core_record c ON c.id = u.cost_code_id "
        "WHERE u.scope = :scope AND u.measure = :measure AND u.subject_id IN :ids "
        "ORDER BY u.as_of_seq"
    ).bindparams(bindparam("ids", expanding=True))
    rows = list(
        conn.execute(
            statement,
            {"scope": scope, "measure": ROLLUP_MEASURE, "ids": sorted(node_ids)},
        ).mappings()
    )
    hidden_cost = _hidden(conn, {str(r["cost_code_id"]) for r in rows if r["cost_code_id"]})
    totals: dict[str, Decimal] = {}
    unallocated: dict[str, Decimal] = {}
    by_code: dict[str, dict[str, Decimal]] = defaultdict(dict)
    partly_hidden: set[str] = set()
    for r in rows:
        subject = str(r["subject_id"])
        if r["line"] == ROLLUP_TOTAL:
            totals[subject] = Decimal(str(r["value"]))
        elif r["line"] == ROLLUP_UNALLOCATED:
            unallocated[subject] = Decimal(str(r["value"]))
        elif r["line"] == ROLLUP_COST_CODE and r["cost_code_id"] is not None:
            cost_id = str(r["cost_code_id"])
            if cost_id in hidden_cost:
                partly_hidden.add(subject)
            else:
                by_code[subject][_text(r["cost_code"]) or cost_id] = Decimal(str(r["value"]))
    for subject in partly_hidden:
        visible = sum(by_code.get(subject, {}).values(), Decimal(0))
        totals[subject] = visible + unallocated.get(subject, Decimal(0))
    return totals, dict(by_code)


def _depth_first(nodes: list[_Node]) -> list[WbsRow]:
    """The nodes depth-first, siblings by position. A node whose parent the viewer may not read
    is started at the top (its own depth and position are kept)."""
    readable = {n.row.id for n in nodes}
    children: dict[str, list[_Node]] = defaultdict(list)
    tops: list[_Node] = []
    for node in sorted(nodes, key=lambda n: (n.row.depth, n.row.position, n.row.code)):
        if node.parent_id is not None and node.parent_id in readable:
            children[node.parent_id].append(node)
        else:
            tops.append(node)
    out: list[WbsRow] = []
    stack = list(reversed(tops))
    while stack:
        node = stack.pop()
        out.append(node.row)
        stack.extend(reversed(children.get(node.row.id, [])))
    return out


def _wbs_cwp(alloc: _Allocation) -> WbsCwp:
    hours = (
        None
        if alloc.budget_hours is None
        else (alloc.budget_hours * alloc.percent / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
    )
    return WbsCwp(number=alloc.number, title=alloc.title, percent=alloc.percent, hours=hours)


def wbs_tree(conn: Connection, scope: str, *, depth: int | None = None) -> list[WbsRow]:
    """The WBS nodes of ``scope`` depth-first, each with its rollup and CWP count (``cwps`` is
    empty here). ``depth=n`` keeps the nodes whose depth is below ``n`` (``depth=1`` is the top
    node alone); the counts do not depend on ``depth``."""
    rows = _depth_first(_wbs_nodes(conn, scope, "", {}, _cwp_index(conn, scope)))
    if depth is None:
        return rows
    return [row for row in rows if row.depth < depth]


def wbs_detail(conn: Connection, scope: str, code: str) -> WbsRow | None:
    """One WBS node by its code, with its rollup and CWP count. A leaf also lists its own CWP
    allocations, by number (``cwps``). ``None`` for a missing or hidden node."""
    node_id = resolve_code(conn, scope, WBS_NODE, code)
    if node_id is None:
        return None
    index = _cwp_index(conn, scope)
    nodes = _wbs_nodes(conn, scope, " AND n.id = :node", {"node": node_id}, index)
    if not nodes:
        return None
    row = nodes[0].row
    if row.id in index.parents:
        return row
    own = sorted(index.own.get(row.id, []), key=lambda alloc: alloc.number)
    return row.model_copy(update={"cwps": [_wbs_cwp(alloc) for alloc in own]})


# --- path of construction -------------------------------------------------------------------------


def _path_head(conn: Connection, scope: str) -> _PathHead | None:
    """The path of ``scope`` (one per project) the viewer may read; ``None`` when there is none."""
    visible, extra = not_hidden("p.id")
    row = (
        conn.execute(
            text(
                "SELECT p.id, r.key, r.title, p.current_version "
                f"FROM {PATH_TABLE} p JOIN cur_core_record r ON r.id = p.id "
                "WHERE p.scope = :scope AND r.type = :type AND r.voided = :voided "
                f"AND {visible} ORDER BY r.key"
            ),
            {"scope": scope, "type": PATH, "voided": False, **extra},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _PathHead(
        id=str(row["id"]),
        key=str(row["key"]),
        title=str(row["title"]),
        current_version=int(row["current_version"]),
    )


def _steps(conn: Connection, scope: str, path_id: str, version: int | None) -> list[dict[str, Any]]:
    """The steps of a path the viewer may read (a step whose area it may not read is left out),
    by version and position. ``version=None`` gives every version."""
    where = "" if version is None else " AND s.version = :version"
    params: dict[str, Any] = {"scope": scope, "path": path_id}
    if version is not None:
        params["version"] = version
    rows = list(
        conn.execute(
            text(
                "SELECT s.version, s.position, s.cwa_id, a.code AS cwa_code, s.reason_code, "
                "s.actor, s.recorded_at "
                f"FROM {PATH_STEP_TABLE} s LEFT JOIN {CWA_TABLE} a ON a.id = s.cwa_id "
                f"WHERE s.scope = :scope AND s.path_id = :path{where} "
                "ORDER BY s.version, s.position"
            ),
            params,
        ).mappings()
    )
    hidden = _hidden(conn, {str(r["cwa_id"]) for r in rows if r["cwa_id"] is not None})
    return [dict(r) for r in rows if r["cwa_id"] is None or str(r["cwa_id"]) not in hidden]


def path(conn: Connection, scope: str, version: int | None = None) -> PathView | None:
    """The path of ``scope`` at ``version`` (its current version when None), steps in position
    order. ``None`` when there is no such path, no such version or no readable step of it."""
    head = _path_head(conn, scope)
    if head is None:
        return None
    wanted = head.current_version if version is None else version
    steps = _steps(conn, scope, head.id, wanted)
    if not steps:
        return None
    return PathView(
        id=head.id,
        key=head.key,
        title=head.title,
        version=wanted,
        current_version=head.current_version,
        steps=[
            PathStep(
                position=int(s["position"]),
                cwa=_text(s["cwa_code"]),
                reason_code=_text(s["reason_code"]),
                actor=str(s["actor"]),
                recorded_at=str(s["recorded_at"]),
            )
            for s in steps
        ],
    )


def path_versions(conn: Connection, scope: str) -> list[PathVersion]:
    """The versions of the path of ``scope``, newest first, counting the readable steps only."""
    head = _path_head(conn, scope)
    if head is None:
        return []
    by_version: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for step in _steps(conn, scope, head.id, None):
        by_version[int(step["version"])].append(step)
    return [
        PathVersion(
            version=version,
            recorded_at=str(steps[0]["recorded_at"]),
            actor=str(steps[0]["actor"]),
            step_count=len(steps),
            is_current=version == head.current_version,
        )
        for version, steps in sorted(by_version.items(), reverse=True)
    ]
