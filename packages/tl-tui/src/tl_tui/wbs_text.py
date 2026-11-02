"""The WBS tree and a WBS node's panel, as pure functions (P2-I1 T05b; spec m3-wbs-cwp §WBS tree,
skill ``tui-layout``).

The values come from ``tl_mod_awp.views.WbsRow`` and nothing else: no client call, no I/O, and no
``textual`` import, so the web client can use the same words. Depth 0 is the top node. A node is a
leaf when no other row names it as its parent; the leaf test always reads the whole tree, so a
depth-limited list still tells a parent from a leaf. Hours use ``awp_text.hours_text``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from tl_tui.awp_text import hours_text
from tl_tui.layout import Page, Section, TableRow, identity_line, join_facts, shown
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_mod_awp.views import WbsRow

WBS_COLUMNS = ("Number", "Subject", "Budget h", "Cost codes")
WBS_RIGHT = ("Budget h",)
INDENT = "  "  # two spaces per depth in the Subject
COST_CODES = "Cost codes"
CWPS = "CWPs"
COST_CODE_COLUMNS = ("Code", "Hours", "%")
CWP_COLUMNS = ("Number", "Subject", "%", "Hours")
NO_CWPS = "No CWPs allocated"
HOURS_UNIT = "h"


def is_leaf(row: WbsRow, rows: Sequence[WbsRow]) -> bool:
    """True when no other row of ``rows`` has ``row`` as its parent."""
    return not any(other is not row and other.parent_code == row.code for other in rows)


def depth_limited(rows: Sequence[WbsRow], n: int) -> list[WbsRow]:
    """The rows at depth below ``n``: ``1`` is the top nodes, ``2`` adds their children. A client
    cut of a tree already loaded; the API's ``depth`` does the same on the server."""
    return [row for row in rows if row.depth < n]


def unallocated_leaves(rows: Sequence[WbsRow]) -> list[WbsRow]:
    """The leaves that carry no cost code, in tree order."""
    parents = {row.parent_code for row in rows}
    return [row for row in rows if row.code not in parents and not row.by_cost_code]


def _share(total: Decimal | None, part: Decimal) -> str:
    """``part`` as a whole percent of ``total``, half-even; ``—`` when there is no total."""
    if total is None or total == 0:
        return EMPTY
    percent = (part * 100 / total).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return f"{percent}%"


def _cost_code_cell(row: WbsRow, rows: Sequence[WbsRow]) -> str:
    """``3 · 100%`` on a leaf with cost codes (the count, and the codes' share of its hours);
    ``—`` on a parent and on a leaf with none."""
    if not row.by_cost_code or not is_leaf(row, rows):
        return EMPTY
    covered = sum(row.by_cost_code.values(), Decimal(0))
    return f"{len(row.by_cost_code)} · {_share(row.total_hours, covered)}"


def wbs_cells(row: WbsRow, rows: Sequence[WbsRow]) -> tuple[str, ...]:
    """The four cells of a tree row, in the order of ``WBS_COLUMNS``."""
    return (
        row.code,
        INDENT * row.depth + shown(row.title),
        hours_text(row.total_hours),
        _cost_code_cell(row, rows),
    )


def _cwp_count(count: int) -> str:
    return "1 CWP" if count == 1 else f"{count} CWPs"


def wbs_summary(row: WbsRow, rows: Sequence[WbsRow]) -> str:
    """``Parent 1.2 · 4 CWPs · 4 200 h``, or ``Leaf · 2 CWPs · 600 h``; no hours fact when the node
    has no rollup."""
    head = "Leaf" if is_leaf(row, rows) else f"Parent {row.code}"
    hours = None if row.total_hours is None else f"{hours_text(row.total_hours)} {HOURS_UNIT}"
    return join_facts(head, _cwp_count(row.cwp_count), hours)


def _cost_code_section(row: WbsRow) -> Section:
    if not row.by_cost_code:
        return Section(COST_CODES, note=EMPTY)
    return Section(
        COST_CODES,
        tuple(
            TableRow(
                COST_CODE_COLUMNS,
                (code, hours_text(hours), _share(row.total_hours, hours)),
            )
            for code, hours in sorted(row.by_cost_code.items())
        ),
    )


def _cwp_section(row: WbsRow) -> Section:
    if not row.cwps:
        return Section(CWPS, note=NO_CWPS)
    return Section(
        CWPS,
        tuple(
            TableRow(
                CWP_COLUMNS,
                (
                    cwp.number,
                    shown(cwp.title),
                    f"{hours_text(cwp.percent)}%",
                    hours_text(cwp.hours),
                ),
            )
            for cwp in row.cwps
        ),
    )


def wbs_page(
    row: WbsRow, rows: Sequence[WbsRow], *, panel: bool = False, technical: bool = False
) -> Page:
    """The node as a page: the identity (``1.2 · Electrical``), the state (``Leaf · active``,
    ``Parent of 4 · active``, ``Leaf · Retired``), then the sections Cost codes and CWPs. A panel
    adds the summary line. ``technical`` is accepted for the shared page signature; a WBS node
    has no technical-only row in I1, and there is no Timeline (no view carries one)."""
    kind = "Leaf" if is_leaf(row, rows) else f"Parent of {_children(row, rows)}"
    status = "Retired" if row.retired else "active"
    return Page(
        identity=identity_line(row.code, shown(row.title)),
        state=f"{kind} · {status}",
        sections=(_cost_code_section(row), _cwp_section(row)),
        summary=wbs_summary(row, rows) if panel else "",
    )


def _children(row: WbsRow, rows: Sequence[WbsRow]) -> int:
    return sum(1 for other in rows if other is not row and other.parent_code == row.code)
