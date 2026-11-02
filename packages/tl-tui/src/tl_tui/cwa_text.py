"""The text of the CWA register and of a CWA's panel, as pure functions (P2-I1 T05e; spec §8 "CWA
register", skill ``tui-layout``).

The values come from ``tl_mod_awp.views`` (``CwaRow``, ``CwpRow``, ``PathView``) and nothing else:
no client call, no I/O, and no ``textual`` import, so the web client can use the same words. A
CWA's position is the place of the first path step that names its code; its CWPs are the rows of
the CWP register whose ``cwa`` is its code. Hours are shown in space-grouped digits, as in
``tl_tui.awp_text``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from tl_tui.awp_text import HOURS_UNIT, hours_text
from tl_tui.details import TECHNICAL_SECTION
from tl_tui.display import humanize
from tl_tui.layout import (
    Page,
    Section,
    TableRow,
    identity_line,
    join_facts,
    prop,
    shown,
    state_line,
)
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_mod_awp.views import CwaRow, CwpRow, PathView

CWA_COLUMNS = ("Number", "Subject", "Position", "CWPs", "Budget h")
CWA_RIGHT = ("Position", "CWPs", "Budget h")
CWA_DROP = ("Budget h", "CWPs")  # left out first at narrow width; Number, Subject and Position stay
CWP_PANEL_COLUMNS = ("Number", "Subject", "State", "Budget h")
ACTIVE = "Active"
RETIRED = "Retired"
LOCATION = "Location"
CWPS = "CWPs"
PATH_POSITION = "Path position"
NO_CWPS = "No CWPs in this area"
NO_CWA = "No CWA matches."


@dataclass(frozen=True)
class CwaLine:
    row: CwaRow
    position: int | None  # the place of the area's code in the path; None when not on the path
    cwps: tuple[CwpRow, ...]  # the register's CWPs whose ``cwa`` is this area's code, by number
    steps: int  # steps = len(path.steps), 0 without a path


def _positions(path: PathView | None) -> dict[str, int]:
    """The position of each code: the first step (in position order) that names it."""
    found: dict[str, int] = {}
    if path is None:
        return found
    for step in sorted(path.steps, key=lambda step: step.position):
        if step.cwa and step.cwa not in found:
            found[step.cwa] = step.position
    return found


def cwa_lines(
    cwas: Sequence[CwaRow], path: PathView | None, cwps: Sequence[CwpRow]
) -> list[CwaLine]:
    """One line per area, ordered by position, the areas off the path last, then by code."""
    positions = _positions(path)
    steps = 0 if path is None else len(path.steps)
    lines = [
        CwaLine(
            row=cwa,
            position=positions.get(cwa.code),
            cwps=tuple(sorted((c for c in cwps if c.cwa == cwa.code), key=lambda c: c.number)),
            steps=steps,
        )
        for cwa in cwas
    ]
    return sorted(
        lines, key=lambda line: (line.position is None, line.position or 0, line.row.code)
    )


def visible_lines(lines: Sequence[CwaLine], show_retired: bool) -> list[CwaLine]:
    """The lines as the register shows them: the retired areas only when ``show_retired``."""
    return [line for line in lines if show_retired or not line.row.retired]


def _budget(cwps: Sequence[CwpRow]) -> Decimal | None:
    """The CWPs' budget hours added up; None when no CWP has a budget."""
    values = [c.budget_hours for c in cwps if c.budget_hours is not None]
    return sum(values, Decimal(0)) if values else None


def _position_text(line: CwaLine) -> str | None:
    return None if line.position is None else f"{line.position} of {line.steps}"


def cwa_cells(line: CwaLine) -> tuple[str, ...]:
    """The five cells of a register row, in the order of ``CWA_COLUMNS``. A position that is not
    on the path and a budget that no CWP has read ``—``."""
    budget = _budget(line.cwps)
    return (
        line.row.code,
        shown(line.row.title),
        EMPTY if line.position is None else str(line.position),
        str(len(line.cwps)),
        EMPTY if budget is None else hours_text(budget),
    )


def cwa_summary(line: CwaLine) -> str:
    """``Position 3 of 12 · 4 CWPs · 11 300 h``; the facts that are absent are left out."""
    budget = _budget(line.cwps)
    count = len(line.cwps)
    return join_facts(
        "" if line.position is None else f"Position {line.position} of {line.steps}",
        f"{count} CWP" + ("" if count == 1 else "s"),
        "" if budget is None else f"{hours_text(budget)} {HOURS_UNIT}",
    )


def _cwp_items(cwps: Sequence[CwpRow]) -> tuple[TableRow, ...]:
    return tuple(
        TableRow(
            CWP_PANEL_COLUMNS,
            (c.number, shown(c.title), humanize(c.state), hours_text(c.budget_hours)),
        )
        for c in cwps
    )


def cwa_page(line: CwaLine, *, panel: bool = False, technical: bool = False) -> Page:
    """The area as a page: the identity and state lines, the Location section (the location text
    and the path position), the CWPs as a table. A panel adds the summary line. ``technical`` adds
    the record id. Files and Links are not shown: no view carries their counts yet."""
    row = line.row
    sections = [
        Section(
            LOCATION,
            (prop("Place", row.location_text), prop(PATH_POSITION, _position_text(line))),
        ),
        Section(CWPS, _cwp_items(line.cwps), note=NO_CWPS),
    ]
    if technical:
        sections.append(Section(TECHNICAL_SECTION, (prop("Id", row.id),)))
    return Page(
        identity=identity_line(row.code, row.title),
        state=state_line(RETIRED if row.retired else ACTIVE),
        sections=tuple(sections),
        summary=cwa_summary(line) if panel else "",
    )
