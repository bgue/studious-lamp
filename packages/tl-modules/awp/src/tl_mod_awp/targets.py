"""Load targets of the awp module (spec m3-wbs-cwp section 6, ticket P2-I1-T02).

Two targets are found by the entry-point group ``throughline.load_targets``; each entry point names
a zero-argument callable that returns a ``tl_mod_legacy.targets.Target`` with scope ``project``:

* ``awp_wbs`` creates nodes (``code``, ``title``, ``parent``, optional ``cost_codes`` as
  ``CODE:PCT;CODE:PCT``) parents first, and plans a row invalid with a fixed reason when its parent
  is unknown, its depth is over 8 or its percentages do not sum to 100;
* ``awp_cwa`` creates areas (``code``, ``title``) and, with a ``sequence`` column, the version-1
  path of construction.

Both are create-only: a code the project holds (read through ``common.resolve_code``, so a record
the viewer may not read counts as absent) is left alone and counted. Rows are written with the
module's own commands and handlers, never with ``create_module_record``. A problem is a line number
and fixed words (an amount that was computed is not a cell); no cell text is put in one. The path
of construction cannot be taken back: ``reversals`` reports it as irreversible and ``reverse``
leaves it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text
from tl_core.text import clean_text
from tl_core.uow import UnitOfWork
from tl_mod_legacy.errors import LoadRefusedError, MappingProblemError
from tl_mod_legacy.model import Grid, LoaderDef
from tl_mod_legacy.targets import (
    Comparison,
    Created,
    Plan,
    PlannedRow,
    Reversal,
    Target,
    TargetScope,
)

from tl_mod_awp.commands import (
    CostCodeLine,
    DefineCwa,
    DefinePathOfConstruction,
    DefineWbsNode,
    MapWbsToCostCodes,
    PathStepIn,
    ReinstateWbsNode,
    RetireCwa,
    RetireWbsNode,
)
from tl_mod_awp.common import (
    HUNDRED,
    cwp_allocates_to,
    cwp_names_cwa,
    get_cwa,
    parse_percent,
    percent_text,
    resolve_code,
)
from tl_mod_awp.errors import AllocationError, DuplicateCodeError
from tl_mod_awp.handlers.cwa import handle_define_cwa, handle_retire_cwa
from tl_mod_awp.handlers.path import handle_define_path_of_construction, path_key
from tl_mod_awp.handlers.wbs import (
    handle_define_wbs_node,
    handle_map_wbs_to_cost_codes,
    handle_reinstate_wbs_node,
    handle_retire_wbs_node,
    load_tree,
)
from tl_mod_awp.limits import (
    CODE_PATTERN,
    MAX_ALLOCATIONS,
    MAX_COST_CODE,
    MAX_PATH_STEPS,
    MAX_REASON,
    MAX_TITLE,
    MAX_WBS_DEPTH,
)
from tl_mod_awp.names import (
    COST_CODE,
    CWA,
    CWA_TABLE,
    PATH_TABLE,
    WBS_ALLOCATION_TABLE,
    WBS_NODE,
)

_CODE = re.compile(CODE_PATTERN)
_SEQUENCE = re.compile(r"[0-9]{1,6}", re.ASCII)  # ASCII digits only
_COLUMNS = ("code", "title", "parent", "cost_codes", "sequence")

R_NO_CODE = "code is missing"
R_CODE = "code is not valid"
R_REPEAT = "code repeated"
R_TITLE = "title is not valid"
R_NO_PARENT = "parent is unknown"
R_BAD_PARENT = "parent is not valid"
R_PARENT_FULL = "parent takes no child"
R_DEPTH = f"depth is over {MAX_WBS_DEPTH} levels"
R_LEAF = "a node with children takes no allocation"
R_LINES = "cost_codes lines are CODE:PCT"
R_PERCENT = "a percent is not a number from 0.01 to 100.00"
R_TWICE = "a cost code appears twice"
R_ROWS = f"an allocation holds 1 to {MAX_ALLOCATIONS} lines"
R_NO_COST = "a cost code does not exist in the project"
R_SEQ = "sequence is not a whole number"
R_SEQ_REPEAT = "sequence repeated"
R_PATH_LONG = f"the path holds at most {MAX_PATH_STEPS} areas"
R_PATH_RETIRED = "a retired area cannot join the path"
P_GONE = "a record the load made is not there"
P_CHANGED = "it was changed after the load"
P_PACKAGE_NODE = "a package that is not void allocates to the node"
P_PACKAGE_CWA = "a package that is not void names the area"
P_CHILD = "a node the load did not make hangs under it"
P_PATH = "the path of construction cannot be taken back"
M_TAKEN = "a code of the file is used by another record in the project; plan the run again"

_FOREIGN_SQL = text("SELECT count(*) FROM events WHERE stream_id = :id AND correlation_id <> :c")
_LINES_SQL = text(f"SELECT cost_code_id, percent FROM {WBS_ALLOCATION_TABLE} WHERE node_id = :node")
_HAS_LINES_SQL = text(f"SELECT 1 FROM {WBS_ALLOCATION_TABLE} WHERE node_id = :node LIMIT 1")
_PATH_SQL = text(f"SELECT id FROM {PATH_TABLE} WHERE scope = :scope")
_PATH_ID_SQL = text(f"SELECT 1 FROM {PATH_TABLE} WHERE id = :id AND scope = :scope")
_CWA_SQL = text(f"SELECT code, retired FROM {CWA_TABLE} WHERE id = :id AND scope = :scope")
_TITLE_SQL = text("SELECT title FROM cur_core_record WHERE id = :id")


class _Bad(Exception):
    """A row reason (fixed words) found while reading a cell."""


@dataclass(frozen=True)
class _Node:
    """The planned WBS node (``PlannedRow.native``): ``lines`` are (cost code, percent text)."""

    code: str
    title: str
    parent: str | None
    depth: int
    lines: tuple[tuple[str, str], ...]
    reinstate: str | None = None  # the id of the retired node this row brings back


@dataclass(frozen=True)
class _PathSpec:
    codes: tuple[str, ...]


def _names(grid: Grid) -> list[str]:
    return [c.strip().lower() for c in grid.columns]


def _cells(grid: Grid, required: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
    """``(file line, cells by column name)`` per data row; names are lower-cased and trimmed."""
    names = _names(grid)
    for name in required:
        if name not in names:
            raise MappingProblemError(f"the file has no column {name!r}")
    wanted = {n: i for i, n in reversed(list(enumerate(names))) if n in _COLUMNS}
    return [
        (index + 2, {n: (row[i] or "").strip() if i < len(row) else "" for n, i in wanted.items()})
        for index, row in enumerate(grid.rows)
    ]


def _code_problem(code: str) -> str | None:
    if not code:
        return R_NO_CODE
    return None if _CODE.fullmatch(code) else R_CODE


def _title_problem(title: str) -> str | None:
    try:
        clean_text(title)
    except ValueError:
        return R_TITLE
    return None if 1 <= len(title) <= MAX_TITLE else R_TITLE


def _lines(cell: str) -> list[tuple[str, Decimal]]:
    """The ``CODE:PCT;CODE:PCT`` cell as lines, or ``_Bad`` with a fixed reason (the sum too)."""
    out: list[tuple[str, Decimal]] = []
    seen: set[str] = set()
    for part in cell.split(";"):
        code, sep, pct = part.strip().rpartition(":")
        code = code.strip()
        if not sep or not code or len(code) > MAX_COST_CODE:
            raise _Bad(R_LINES)
        try:
            percent = parse_percent(pct.strip())
        except AllocationError as exc:
            raise _Bad(R_PERCENT) from exc
        if code in seen:
            raise _Bad(R_TWICE)
        seen.add(code)
        out.append((code, percent))
    if len(out) > MAX_ALLOCATIONS:
        raise _Bad(R_ROWS)
    total = sum((p for _, p in out), Decimal("0.00"))
    if total != HUNDRED:
        raise _Bad(f"allocation sums to {total}, not 100.00")
    return out


def _foreign(conn: Connection, record_id: str, correlation_id: str) -> bool:
    return int(conn.execute(_FOREIGN_SQL, {"id": record_id, "c": correlation_id}).scalar_one()) > 0


def _base(scope: str, source: str, actor: str, correlation_id: str) -> dict[str, Any]:
    return {"actor": actor, "source": source, "scope": scope, "correlation_id": correlation_id}


def _gone(record_id: str) -> Reversal:
    return Reversal(record_id, None, None, False, P_GONE)


def _retired(conn: Connection, cwa_id: str) -> bool:
    area = get_cwa(conn, cwa_id)
    return area is None or area.retired


class WbsTarget:
    kind = "awp_wbs"
    module = "awp"
    scope: TargetScope = "project"

    # --- plan --------------------------------------------------------------------------------

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        tree = load_tree(conn, scope)
        existing: list[str] = []
        invalid: list[tuple[int, str]] = []
        pending: dict[str, tuple[int, dict[str, str], list[tuple[str, Decimal]]]] = {}
        revived: dict[str, str] = {}
        bad: set[str] = set()
        seen: set[str] = set()
        for line, raw in _cells(grid, ("code", "title")):
            code = raw["code"]
            reason = _code_problem(code) or (R_REPEAT if code in seen else None)
            if reason:
                invalid.append((line, reason))
                continue
            seen.add(code)
            held = resolve_code(conn, scope, WBS_NODE, code)
            revive: str | None = None
            if held is not None:
                old = tree.by_id[held]
                held_parent = None if old.parent_id is None else tree.by_id[old.parent_id].code
                if old.retired and held_parent == (raw.get("parent") or None):
                    revive = held  # a retired node of the same parent: the reload brings it back
                else:
                    existing.append(code)
                    continue
            lines: list[tuple[str, Decimal]] = []
            reason = _title_problem(raw["title"])
            parent = raw.get("parent", "")
            if reason is None and parent and not _CODE.fullmatch(parent):
                reason = R_NO_PARENT
            if reason is None and raw.get("cost_codes"):
                try:
                    lines = _lines(raw["cost_codes"])
                    if any(resolve_code(conn, scope, COST_CODE, c) is None for c, _ in lines):
                        reason = R_NO_COST
                except _Bad as exc:
                    reason = str(exc)
            if reason:
                invalid.append((line, reason))
                bad.add(code)
            else:
                pending[code] = (line, raw, lines)
                if revive is not None:
                    revived[code] = revive
        parents = {raw.get("parent") for _, raw, _ in pending.values()}
        for code in [c for c, (_, _, lines) in pending.items() if lines and c in parents]:
            invalid.append((pending.pop(code)[0], R_LEAF))
            bad.add(code)

        memo: dict[str, int | str] = {}

        def outside(parent: str) -> int | str:
            """The depth of a parent that is not a new row of the file, or a fixed reason."""
            if parent in bad:
                return R_BAD_PARENT
            found = resolve_code(conn, scope, WBS_NODE, parent)
            if found is None:
                return R_NO_PARENT
            if conn.execute(_HAS_LINES_SQL, {"node": found}).first() or cwp_allocates_to(
                conn, found
            ):
                return R_PARENT_FULL
            return tree.by_id[found].depth

        def settle(code: str) -> None:
            """Give ``code`` and the new rows above it a depth, or the reason they have none."""
            path: list[str] = []
            cur = code
            while True:
                path.append(cur)
                parent = pending[cur][1].get("parent", "")
                if not parent:
                    base: int | str = -1
                elif parent not in pending:
                    base = outside(parent)
                elif parent in memo:
                    base = memo[parent]
                elif parent in path:
                    base = R_NO_PARENT  # the parents form a loop
                else:
                    cur = parent
                    continue
                break
            for name in reversed(path):
                if isinstance(base, str):
                    memo[name] = base
                    base = R_BAD_PARENT
                elif base + 1 >= MAX_WBS_DEPTH:
                    memo[name] = R_DEPTH
                    base = R_BAD_PARENT
                else:
                    base += 1
                    memo[name] = base

        rows: list[PlannedRow] = []
        for code, (line, raw, lines) in pending.items():
            if code not in memo:
                settle(code)
            depth = memo[code]
            if isinstance(depth, str):
                invalid.append((line, depth))
                continue
            node = _Node(
                code,
                raw["title"],
                raw.get("parent") or None,
                depth,
                tuple((c, percent_text(p)) for c, p in lines),
                revived.get(code),
            )
            rows.append(PlannedRow(line, code, dict(raw), node))
        return Plan(rows=rows, existing=existing, invalid=sorted(invalid))

    # --- apply -------------------------------------------------------------------------------

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]:
        base = _base(scope, source, actor, correlation_id)
        made: list[Created] = []
        for planned in sorted(plan.rows, key=lambda r: (r.native.depth, r.line)):  # parents first
            node: _Node = planned.native
            if node.reinstate is not None:
                result = handle_reinstate_wbs_node(
                    uow,
                    ReinstateWbsNode(
                        **base, node=node.reinstate, reason="Reloaded after a compensated load"
                    ),
                )
                if self._lines_differ(
                    uow.conn(), scope, node.reinstate, planned.raw.get("cost_codes", "")
                ):
                    handle_map_wbs_to_cost_codes(
                        uow,
                        MapWbsToCostCodes(
                            **base,
                            node=result.stream_id,
                            allocations=[
                                CostCodeLine(cost_code=c, percent=p) for c, p in node.lines
                            ],
                        ),
                    )
                made.append(Created(result.stream_id, node.code, planned.line, planned.raw))
                continue
            try:
                result = handle_define_wbs_node(
                    uow,
                    DefineWbsNode(
                        **base, code=node.code, title=node.title, parent_code=node.parent
                    ),
                )
            except DuplicateCodeError as exc:
                raise LoadRefusedError(M_TAKEN) from exc
            if node.lines:
                handle_map_wbs_to_cost_codes(
                    uow,
                    MapWbsToCostCodes(
                        **base,
                        node=result.stream_id,
                        allocations=[CostCodeLine(cost_code=c, percent=p) for c, p in node.lines],
                    ),
                )
            made.append(Created(result.stream_id, node.code, planned.line, planned.raw))
        return made

    # --- compare -----------------------------------------------------------------------------

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        cells = _cells(grid, ("code", "title"))
        bad = {line for line, _ in self.plan(conn, scope, loader, grid).invalid}
        tree = load_tree(conn, scope)
        named = set(_names(grid))
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        for line, raw in cells:
            code = raw["code"]
            if line in bad or not code or code in seen:
                invalid += 1
                continue
            seen.add(code)
            valid += 1
            found = resolve_code(conn, scope, WBS_NODE, code)
            node = None if found is None else tree.by_id[found]
            if node is None or node.retired:
                missing.append(line)
                continue
            fields = ["title"] if raw["title"] != node.title else []
            if "parent" in named:
                held = "" if node.parent_id is None else tree.by_id[node.parent_id].code
                if raw["parent"] != held:
                    fields.append("parent")
            if "cost_codes" in named and self._lines_differ(
                conn, scope, node.id, raw["cost_codes"]
            ):
                fields.append("cost_codes")
            if not fields:
                matched += 1
            elif code in created_keys:
                differs.extend((line, name) for name in fields)
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    @staticmethod
    def _lines_differ(conn: Connection, scope: str, node_id: str, cell: str) -> bool:
        held = {
            str(r.cost_code_id): str(r.percent) for r in conn.execute(_LINES_SQL, {"node": node_id})
        }
        if not cell:
            return bool(held)
        try:
            wanted = {
                resolve_code(conn, scope, COST_CODE, c): percent_text(p) for c, p in _lines(cell)
            }
        except _Bad:
            return True
        return wanted != held

    # --- reversal ----------------------------------------------------------------------------

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        tree = load_tree(conn, scope)
        ids = set(record_ids)
        found: list[Reversal] = []
        for record_id in record_ids:
            node = tree.by_id.get(record_id)
            if node is None:
                found.append(_gone(record_id))
                continue
            problem = None
            if _foreign(conn, record_id, correlation_id):
                problem = P_CHANGED
            elif not node.retired and cwp_allocates_to(conn, record_id):
                problem = P_PACKAGE_NODE
            elif any(not c.retired and c.id not in ids for c in tree.children(record_id)):
                problem = P_CHILD
            state = "Retired" if node.retired else "Active"
            found.append(Reversal(record_id, node.code, state, problem is None, problem))
        return found

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int:
        tree = load_tree(uow.conn(), scope)
        nodes = [tree.by_id[i] for i in record_ids if i in tree.by_id]
        base = _base(scope, source, actor, correlation_id)
        count = 0
        for node in sorted(nodes, key=lambda n: (-n.depth, n.code)):  # children before parents
            if node.retired:
                continue
            command = RetireWbsNode(**base, node=node.id, reason=reason[:MAX_REASON])
            handle_retire_wbs_node(uow, command)
            count += 1
        return count


class CwaTarget:
    kind = "awp_cwa"
    module = "awp"
    scope: TargetScope = "project"

    # --- plan --------------------------------------------------------------------------------

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        cells = _cells(grid, ("code", "title"))
        sequenced = "sequence" in _names(grid)
        rows: list[PlannedRow] = []
        existing: list[str] = []
        invalid: list[tuple[int, str]] = []
        steps: list[tuple[int, str, int, str | None]] = []  # (sequence, code, line, existing id)
        seen: set[str] = set()
        taken: set[int] = set()
        spoiled = False  # a row with a sequence is invalid: the path waits for a fixed file
        for line, raw in cells:
            code = raw["code"]
            seq = raw.get("sequence", "") if sequenced else ""
            reason = _code_problem(code) or (R_REPEAT if code in seen else None)
            if reason is None:
                seen.add(code)
                if seq and not _SEQUENCE.fullmatch(seq):
                    reason = R_SEQ
                elif seq and int(seq) in taken:
                    reason = R_SEQ_REPEAT
            found = None if reason else resolve_code(conn, scope, CWA, code)
            if reason is None and found is None:
                reason = _title_problem(raw["title"])
            if reason:
                invalid.append((line, reason))
                spoiled = spoiled or bool(seq)
                continue
            if seq:
                taken.add(int(seq))
                steps.append((int(seq), code, line, found))
            if found is None:
                rows.append(PlannedRow(line, code, dict(raw)))
            else:
                existing.append(code)
        if steps and not spoiled:
            self._plan_path(conn, scope, sorted(steps), rows, existing, invalid)
        return Plan(rows=rows, existing=existing, invalid=sorted(invalid))

    @staticmethod
    def _plan_path(
        conn: Connection,
        scope: str,
        steps: list[tuple[int, str, int, str | None]],
        rows: list[PlannedRow],
        existing: list[str],
        invalid: list[tuple[int, str]],
    ) -> None:
        """The version-1 path, once: a project that has one keeps it (counted as existing)."""
        if conn.execute(_PATH_SQL, {"scope": scope}).first() is not None:
            existing.append(path_key(scope))
            return
        if len(steps) > MAX_PATH_STEPS:
            invalid.append((steps[MAX_PATH_STEPS][2], R_PATH_LONG))
            return
        retired = [s for s in steps if s[3] is not None and _retired(conn, s[3])]
        if retired:
            invalid.append((retired[0][2], R_PATH_RETIRED))
            return
        spec = _PathSpec(tuple(s[1] for s in steps))
        rows.append(PlannedRow(steps[0][2], path_key(scope), {}, spec))

    # --- apply -------------------------------------------------------------------------------

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]:
        base = _base(scope, source, actor, correlation_id)
        made: list[Created] = []
        for planned in (r for r in plan.rows if not isinstance(r.native, _PathSpec)):
            try:
                result = handle_define_cwa(
                    uow, DefineCwa(**base, code=planned.key, title=planned.raw["title"])
                )
            except DuplicateCodeError as exc:
                raise LoadRefusedError(M_TAKEN) from exc
            made.append(Created(result.stream_id, planned.key, planned.line, planned.raw))
        for planned in (r for r in plan.rows if isinstance(r.native, _PathSpec)):
            steps = [PathStepIn(cwa_code=c) for c in planned.native.codes]
            path = handle_define_path_of_construction(
                uow, DefinePathOfConstruction(**base, steps=steps)
            )
            made.append(Created(path.stream_id, planned.key, planned.line, planned.raw))
        return made

    # --- compare -----------------------------------------------------------------------------

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        cells = _cells(grid, ("code", "title"))
        bad = {line for line, _ in self.plan(conn, scope, loader, grid).invalid}
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        for line, raw in cells:
            code = raw["code"]
            if line in bad or not code or code in seen:
                invalid += 1
                continue
            seen.add(code)
            valid += 1
            found = resolve_code(conn, scope, CWA, code)
            if found is None or _retired(conn, found):
                missing.append(line)
            elif conn.execute(_TITLE_SQL, {"id": found}).scalar_one() == raw["title"]:
                matched += 1
            elif code in created_keys:
                differs.append((line, "title"))
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    # --- reversal ----------------------------------------------------------------------------

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        found: list[Reversal] = []
        for record_id in record_ids:
            if conn.execute(_PATH_ID_SQL, {"id": record_id, "scope": scope}).first() is not None:
                found.append(Reversal(record_id, path_key(scope), "Defined", False, P_PATH))
                continue
            row = conn.execute(_CWA_SQL, {"id": record_id, "scope": scope}).first()
            if row is None:
                found.append(_gone(record_id))
                continue
            retired = bool(row.retired)
            problem = None
            if _foreign(conn, record_id, correlation_id):
                problem = P_CHANGED
            elif not retired and cwp_names_cwa(conn, record_id):
                problem = P_PACKAGE_CWA
            state = "Retired" if retired else "Active"
            found.append(Reversal(record_id, str(row.code), state, problem is None, problem))
        return found

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int:
        base = _base(scope, source, actor, correlation_id)
        count = 0
        for record_id in reversed(record_ids):
            area = get_cwa(uow.conn(), record_id)  # the path is not an area: it is left
            if area is None or area.retired:
                continue
            handle_retire_cwa(uow, RetireCwa(**base, cwa=record_id, reason=reason[:MAX_REASON]))
            count += 1
        return count


def wbs_target() -> Target:
    """The ``awp_wbs`` load target."""
    return WbsTarget()


def cwa_target() -> Target:
    """The ``awp_cwa`` load target."""
    return CwaTarget()
