"""The plan of a cost snapshot import: what it would create and change, and what it would refuse.

``plan_import`` reads the ledger (the codes of the scope) and the rows, and writes nothing. The
command runs the same plan before it appends anything, so the preview a person reads and the apply
cannot disagree about what is new, what is revised, or why a file is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from tl_mod_cost.imports.model import CostRow
from tl_mod_cost.limits import MAX_DEPTH, MAX_ROWS
from tl_mod_cost.names import COST_CODE_TABLE

_CODES_SQL = text(
    f"SELECT c.id, c.code, c.parent_code, c.level, c.uom, r.title FROM {COST_CODE_TABLE} c "
    "JOIN cur_core_record r ON r.id = c.id WHERE c.scope = :scope"
)
MAX_ISSUES = 100


@dataclass(frozen=True)
class Existing:
    id: str
    code: str
    parent_code: str | None
    level: int
    uom: str | None
    title: str


@dataclass(frozen=True)
class PlannedCode:
    """A code of the file with what the import does to it."""

    row: CostRow
    level: int
    existing: Existing | None
    changes: dict[str, list[object]]  # field -> [old, new] for title and uom

    @property
    def is_new(self) -> bool:
        return self.existing is None


@dataclass(frozen=True)
class CostPlan:
    #: Parents before children, so a new code's parent exists when it is created.
    codes: tuple[PlannedCode, ...]
    issues: tuple[str, ...] = field(default_factory=tuple)
    truncated: bool = False

    @property
    def new(self) -> tuple[PlannedCode, ...]:
        return tuple(c for c in self.codes if c.is_new)

    @property
    def revised(self) -> tuple[PlannedCode, ...]:
        return tuple(c for c in self.codes if not c.is_new and c.changes)

    @property
    def unchanged(self) -> int:
        return sum(1 for c in self.codes if not c.is_new and not c.changes)


def existing_codes(conn: Connection, scope: str) -> dict[str, Existing]:
    """The cost codes of a scope by code."""
    found = conn.execute(_CODES_SQL, {"scope": scope})
    return {
        str(r.code): Existing(
            id=str(r.id),
            code=str(r.code),
            parent_code=None if r.parent_code is None else str(r.parent_code),
            level=int(r.level),
            uom=None if r.uom is None else str(r.uom),
            title=str(r.title),
        )
        for r in found
    }


def plan_import(
    conn: Connection, scope: str, rows: list[CostRow] | tuple[CostRow, ...]
) -> CostPlan:
    """What importing ``rows`` into ``scope`` would do. Issues are reasons to refuse the file."""
    issues: list[str] = []

    def issue(message: str) -> None:
        if len(issues) < MAX_ISSUES:
            issues.append(message)

    if not rows:
        return CostPlan((), ("the file has no cost codes",))
    if len(rows) > MAX_ROWS:
        return CostPlan((), (f"the file has more than {MAX_ROWS} cost codes",))
    known = existing_codes(conn, scope)
    in_file: dict[str, CostRow] = {}
    for row in rows:
        if row.code in in_file:
            issue(f"{row.code}: the code appears twice")
        in_file.setdefault(row.code, row)
    # the parent each code will have after the import: a mirrored code keeps its parent
    parent_of: dict[str, str | None] = {c: e.parent_code for c, e in known.items()}
    for code, row in in_file.items():
        old = known.get(code)
        if old is None:
            parent_of[code] = row.parent_code
        elif row.parent_code is not None and row.parent_code != old.parent_code:
            issue(
                f"{code}: the parent changes from {old.parent_code or 'none'} to "
                f"{row.parent_code}; moving a mirrored code is not supported"
            )
    for code in in_file:
        parent = parent_of.get(code)
        if parent is None:
            continue
        if parent == code:
            issue(f"{code}: a code cannot be its own parent")
        elif parent not in parent_of:
            issue(f"{code}: the parent {parent} is neither in the file nor a known code")
    level_of: dict[str, int] = {}

    def level(code: str) -> int | None:
        chain: list[str] = []
        cursor: str | None = code
        while cursor is not None and cursor not in level_of:
            if cursor in chain or len(chain) > MAX_DEPTH:
                return None
            chain.append(cursor)
            cursor = parent_of.get(cursor)
        base = level_of[cursor] if cursor is not None else 0
        for node in reversed(chain):
            base += 1
            if base > MAX_DEPTH:
                return None
            level_of[node] = base
        return level_of[code]

    planned: list[PlannedCode] = []
    for code, row in in_file.items():
        found = level(code)
        if found is None:
            issue(f"{code}: the hierarchy loops or is deeper than {MAX_DEPTH} levels")
            continue
        old = known.get(code)
        changes: dict[str, list[object]] = {}
        if old is not None:
            if row.description is not None and row.description != old.title:
                changes["title"] = [old.title, row.description]
            if row.uom is not None and row.uom != old.uom:
                changes["uom"] = [old.uom, row.uom]
        planned.append(PlannedCode(row, found, old, changes))
    planned.sort(key=lambda c: c.level)  # parents first; stable, so the file's order within a level
    return CostPlan(tuple(planned), tuple(issues), truncated=len(issues) >= MAX_ISSUES)
