"""What the tag register shows, as pure functions (P1-I1-T09d; brief 9 M2; P1-UX-T02).

The rows, the detail panel and the summary line are text built from ``TagView`` values and nothing
else, so the tests check them without a terminal. None of it decides anything: a number that
breaks the pattern, a class that lacks a property set and a tag in the wrong state are the
module's findings, shown here as they come.

Plain mode speaks in words: the class as ``Control valve``, the properties as labels
(``Valve data / Body material``), the number parts as ``Area 47, Mnemonic FV, Seq 1001``. Technical
mode shows the raw class code, the property paths and the ``area=47 mnemonic=FV seq=1001`` segments.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_engineering.views import TagView

from tl_tui.display import Labels, humanize
from tl_tui.text import conformance_mark

COLUMNS = ("Number", "Class", "Status", "Number check", "Conformance", "Title")
ALL_CLASSES = "all classes"


def number_fits(view: TagView) -> bool:
    """True when the number keeps the registry pattern."""
    return view.number_status == "ok"


def class_text(view: TagView) -> str:
    """The class in words (``Control valve``), ``-`` when the tag has none."""
    return humanize(view.class_code) if view.class_code else "-"


def label_path(path: str) -> str:
    """A property path as its labels: a leading ``psets`` is dropped, the rest humanized.

    ``psets.valve_data.body_material`` reads ``Valve data / Body material``.
    """
    parts = path.split(".")
    if parts and parts[0] == "psets":
        parts = parts[1:]
    return " / ".join(humanize(part) for part in parts)


def row_cells(view: TagView, labels: Labels | None = None) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``."""
    number_check = "ok" if number_fits(view) else "does not fit"
    return (
        view.number,
        class_text(view),
        view.status or "-",
        number_check,
        conformance_mark(view.conformance),
        view.title,
    )


def detail_lines(
    view: TagView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the table for the highlighted tag."""
    if technical:
        segments = " ".join(f"{name}={value}" for name, value in view.segments.items())
        number_line = f"number {view.number_status}: {segments or '-'}"
        class_word = view.class_code or "-"
    else:
        words = ", ".join(f"{humanize(name)} {value}" for name, value in view.segments.items())
        check = "ok" if number_fits(view) else "does not fit the pattern"
        number_line = f"number {check}" + (f": {words}" if words else "")
        class_word = class_text(view)
    lines = [
        f"{view.number}  {view.title}",
        f"class {class_word}  |  status {view.status or '-'}  |  conformance {view.conformance}",
        number_line,
    ]
    for violation in view.violations:
        lines.append(
            f"  ! {violation['segment'] or 'number'}: {violation['message']} ({violation['level']})"
        )
    if view.issues:
        lines.append("lacks:")
        for issue in view.issues:
            path = issue.path if technical else label_path(issue.path)
            lines.append(f"  {issue.level}  {path} {issue.message}")
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
    labels: Labels | None = None,
) -> str:
    """The status line under the table."""
    parts = [f"{shown} of {total} tags"]
    if class_code is not None:
        parts.append(f"class {humanize(class_code)}")
    if violations_only:
        parts.append("violations only")
    if include_ended:
        parts.append("incl. ended")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)
