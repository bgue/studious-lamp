"""The path of construction as text: its steps, the comparison of two versions and the page of one
version (P2-I1 T05c; spec §8 "Path of construction", skill ``tui-layout``).

The values come from ``tl_mod_awp.views`` (a ``PathView`` and its ``PathVersion`` rows, the CWAs and
the CWPs) and nothing else: no client call, no I/O, and no ``textual`` import, so the web client can
use the same words. Steps are keyed by their CWA code; a step with no CWA is left out of a
comparison.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from tl_tui.awp_text import hours_text
from tl_tui.details import PANEL_LIST_LIMITS
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import Page, Section, TableRow, limited, shown, state_line
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_mod_awp.views import CwaRow, CwpRow, PathStep, PathVersion, PathView

PATH_COLUMNS = ("Number", "Subject", "Reason", "CWPs", "Budget h")
PATH_RIGHT = ("Number", "CWPs", "Budget h")  # Number = position
COMPARE_COLUMNS = ("CWA", "Before", "After", "Change")
CWP_COLUMNS = ("Number", "Subject", "Budget h")
VERSION_COLUMNS = ("Version", "Date", "Who", "Reason", "Current")  # the last holds ``current``
REASON_LIST = "PathReason"  # the code list the re-sequencing reasons are labelled from
CURRENT = "current"
NO_CWPS = "No CWPs in this area"
NO_CHANGES = "No steps changed"
NO_VERSIONS = "No versions recorded"


@dataclass(frozen=True)
class PathLine:
    """One step of a version, with its CWA's name (None when the area is not readable) and the
    CWPs of that area."""

    step: PathStep
    title: str | None
    cwps: tuple[CwpRow, ...]


@dataclass(frozen=True)
class Moved:
    """One CWA's place in two versions: its position before and after (None when absent)."""

    cwa: str | None
    before: int | None
    after: int | None


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def _day(value: str | None) -> str:
    """The day of an ISO date-time (``2026-10-01T09:00:00+00:00``); ``—`` for none."""
    return EMPTY if not value else value[:10]


def _reason(labels: Labels | None, code: str | None) -> str:
    """The re-sequencing reason's label from the code list; a code with no label reads humanized."""
    if not code:
        return EMPTY
    return _labels(labels).code_labels.get(REASON_LIST, {}).get(code) or humanize(code)


def path_lines(view: PathView, cwas: Sequence[CwaRow], cwps: Sequence[CwpRow]) -> list[PathLine]:
    """The steps of ``view`` in position order, each with its CWA's name and its CWPs."""
    names = {area.code: area.title or None for area in cwas}
    lines: list[PathLine] = []
    for step in sorted(view.steps, key=lambda step: step.position):
        if step.cwa is None:
            lines.append(PathLine(step, None, ()))
            continue
        members = sorted((cwp for cwp in cwps if cwp.cwa == step.cwa), key=lambda c: c.number)
        lines.append(PathLine(step, names.get(step.cwa), tuple(members)))
    return lines


def _subject(line: PathLine) -> str:
    code = line.step.cwa
    if code is None:
        return EMPTY
    return f"{code} · {line.title}" if line.title else code


def path_cells(line: PathLine, labels: Labels | None = None) -> tuple[str, ...]:
    """The five cells of a step, in the order of ``PATH_COLUMNS``. Budget h is the sum of the
    CWPs' budgets, ``—`` when none of them has a budget."""
    budgets = [cwp.budget_hours for cwp in line.cwps if cwp.budget_hours is not None]
    budget = hours_text(sum(budgets, Decimal(0))) if budgets else EMPTY
    return (
        str(line.step.position),
        _subject(line),
        _reason(labels, line.step.reason_code),
        str(len(line.cwps)),
        budget,
    )


def compare_versions(old: PathView, new: PathView) -> list[Moved]:
    """Where each CWA of ``new`` stands against ``old``: the rows in the new order, then the CWAs
    that are gone, in their old order. Steps with no CWA are left out of both sides."""
    before = _positions(old)
    after = _positions(new)
    moved = [Moved(code, before.get(code), position) for code, position in after.items()]
    gone = [Moved(code, position, None) for code, position in before.items() if code not in after]
    return [*moved, *gone]


def _positions(view: PathView) -> dict[str, int]:
    """The CWA codes of a version in position order, with their positions."""
    found: dict[str, int] = {}
    for step in sorted(view.steps, key=lambda step: step.position):
        if step.cwa is not None and step.cwa not in found:
            found[step.cwa] = step.position
    return found


def mark(m: Moved) -> str:
    """``↑2`` moved two places earlier, ``↓1`` one place later, ``new``, ``gone``, or ``""``."""
    if m.before is None:
        return "new"
    if m.after is None:
        return "gone"
    if m.after < m.before:
        return f"↑{m.before - m.after}"
    if m.after > m.before:
        return f"↓{m.after - m.before}"
    return ""


def compare_cells(m: Moved) -> tuple[str, ...]:
    """The four cells of a comparison row, in the order of ``COMPARE_COLUMNS``."""
    return (
        shown(m.cwa),
        EMPTY if m.before is None else str(m.before),
        EMPTY if m.after is None else str(m.after),
        mark(m),
    )


def version_heading(view: PathView) -> str:
    """``Path of construction · version 4``."""
    return f"Path of construction · version {view.version}"


def _state(view: PathView, versions: Sequence[PathVersion], labels: Labels | None) -> str:
    """``Defined 2026-10-01 by sue`` for version 1, ``Re-sequenced 2026-10-15 by sue · reason
    Access`` for a later one; ``""`` when the version has no row."""
    row = next((v for v in versions if v.version == view.version), None)
    if row is None:
        return ""
    who = actor_label(_labels(labels), row.actor)
    if view.version == 1:
        return f"Defined {_day(row.recorded_at)} by {who}"
    text = f"Re-sequenced {_day(row.recorded_at)} by {who}"
    if row.reason_code:
        text += f" · reason {_reason(labels, row.reason_code)}"
    return text


def path_page(
    view: PathView,
    versions: Sequence[PathVersion],
    line: PathLine | None,
    *,
    previous: PathView | None = None,
    labels: Labels | None = None,
    panel: bool = False,
) -> Page:
    """The page of one version: the identity and state lines, then the sections CWPs (the CWPs
    of ``line``), Steps changed (against ``previous``) and Versions, newest first."""
    lab = _labels(labels)
    sections: list[Section] = []
    if line is not None:
        cwp_rows = tuple(
            TableRow(CWP_COLUMNS, (cwp.number, shown(cwp.title), hours_text(cwp.budget_hours)))
            for cwp in line.cwps
        )
        sections.append(Section("CWPs", cwp_rows, NO_CWPS))
    if previous is not None:
        changed = tuple(
            TableRow(COMPARE_COLUMNS, compare_cells(m))
            for m in compare_versions(previous, view)
            if mark(m)
        )
        sections.append(Section("Steps changed", changed, NO_CHANGES))
    version_rows = tuple(
        TableRow(
            VERSION_COLUMNS,
            (
                str(v.version),
                _day(v.recorded_at),
                actor_label(lab, v.actor),
                _reason(lab, v.reason_code),
                CURRENT if v.is_current else "",
            ),
        )
        for v in sorted(versions, key=lambda v: v.version, reverse=True)
    )
    sections.append(Section("Versions", version_rows, NO_VERSIONS))
    if panel:
        sections = [
            Section(s.heading, limited(s.items, PANEL_LIST_LIMITS.get(s.heading)), s.note)
            for s in sections
        ]
    state = _state(view, versions, lab)
    return Page(
        identity=version_heading(view),
        state=state_line(state) if state else "",
        sections=tuple(sections),
    )
