"""What the tag register shows, as pure functions (P1-I1-T09d; brief 9 M2).

The rows, the detail panel and the summary line are text built from ``TagView`` values and nothing
else, so the tests check them without a terminal. None of it decides anything: a number that
breaks the pattern, a class that lacks a property set and a tag in the wrong state are the
module's findings, shown here as they come.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_engineering.views import TagView

COLUMNS = ("Number", "Class", "Status", "No.", "Conf", "Title")
ALL_CLASSES = "all classes"


def row_cells(view: TagView) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``."""
    number_check = "ok" if view.number_status == "ok" else "BAD"
    return (
        view.number,
        view.class_code or "-",
        view.status or "-",
        number_check,
        view.conformance,
        view.title,
    )


def detail_lines(view: TagView) -> list[str]:
    """The panel under the table for the highlighted tag."""
    segments = " ".join(f"{name}={value}" for name, value in view.segments.items())
    lines = [
        f"{view.number}  {view.title}",
        f"class {view.class_code or '-'}  |  status {view.status or '-'}  |  "
        f"conformance {view.conformance}",
        f"number {view.number_status}: {segments or '-'}",
    ]
    for violation in view.violations:
        lines.append(
            f"  ! {violation['segment'] or 'number'}: {violation['message']} ({violation['level']})"
        )
    if view.issues:
        lines.append("lacks:")
        lines.extend(f"  {issue.level}  {issue.path} {issue.message}" for issue in view.issues)
    elif view.conformance == "ok":
        lines.append("nothing lacking")
    else:
        lines.append("no detail loaded")
    return lines


def next_class(current: str | None, classes: Sequence[str]) -> str | None:
    """The class filter after ``current``: ``None`` (all), then each class, then ``None``."""
    cycle: list[str | None] = [None, *sorted(set(classes))]
    if current not in cycle:
        return None
    return cycle[(cycle.index(current) + 1) % len(cycle)]


def summary_line(
    shown: int,
    total: int,
    *,
    class_code: str | None,
    violations_only: bool,
    include_ended: bool,
    text: str,
) -> str:
    """The status line under the table."""
    parts = [f"{shown} of {total} tags"]
    if class_code is not None:
        parts.append(f"class {class_code}")
    if violations_only:
        parts.append("violations only")
    if include_ended:
        parts.append("incl. ended")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)
