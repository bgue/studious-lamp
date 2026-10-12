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
    # STEPS
    # 1. Number, class (``-`` when none), status (``-`` when none), the number check (``ok`` when
    #    ``number_status`` is ``ok``, else ``BAD``), the conformance level as stored, the title.
    # IMPL
    return (
        view.number,
        view.class_code or "-",
        view.status or "-",
        "ok" if view.number_status == "ok" else "BAD",
        view.conformance,
        view.title,
    )
    # END


def detail_lines(view: TagView) -> list[str]:
    """The panel under the table for the highlighted tag."""
    # STEPS
    # 1. ``<number>  <title>``.
    # 2. ``class <class or -> | status <status or -> | conformance <level>`` (one line; the three
    #    parts joined by ``  |  ``).
    # 3. ``number <number_status>: <segments>`` where the segments are ``name=value`` pairs in the
    #    order of ``view.segments`` joined by a space, or ``-`` when there are none.
    # 4. One line per entry of ``view.violations``: ``  ! <segment or "number">: <message>
    #    (<level>)``.
    # 5. With ``view.issues``: the line ``lacks:`` and then one line per issue: ``  <level>  <path>
    #    <message>`` (two spaces after the level, one after the path). Without: ``nothing lacking``
    #    when ``view.conformance`` is ``ok``, else ``no detail loaded`` (a listing has no issues).
    # IMPL
    lines = [
        f"{view.number}  {view.title}",
        "  |  ".join(
            (
                f"class {view.class_code or '-'}",
                f"status {view.status or '-'}",
                f"conformance {view.conformance}",
            )
        ),
    ]
    segments = " ".join(f"{k}={v}" for k, v in view.segments.items()) or "-"
    lines.append(f"number {view.number_status}: {segments}")
    for violation in view.violations:
        where = violation.get("segment") or "number"
        lines.append(f"  ! {where}: {violation['message']} ({violation['level']})")
    if view.issues:
        lines.append("lacks:")
        lines += [f"  {i.level}  {i.path} {i.message}" for i in view.issues]
    else:
        lines.append("nothing lacking" if view.conformance == "ok" else "no detail loaded")
    return lines
    # END


def next_class(current: str | None, classes: Sequence[str]) -> str | None:
    """The class filter after ``current``: ``None`` (all), then each class, then ``None``."""
    # STEPS
    # 1. The cycle is ``[None, *sorted(set(classes))]``.
    # 2. ``current`` is in the cycle: the next one, wrapping to ``None`` after the last. ``current``
    #    is not in it (the class has no tag any more): ``None``.
    # IMPL
    cycle: list[str | None] = [None, *sorted(set(classes))]
    if current not in cycle:
        return None
    return cycle[(cycle.index(current) + 1) % len(cycle)]
    # END


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
    # STEPS
    # 1. ``<shown> of <total> tags`` (``1 of 1 tags`` too).
    # 2. Then, each preceded by two spaces and only when it applies, in this order:
    #    ``class <code>``, ``violations only``, ``incl. ended``, ``filter "<text>"`` (text
    #    stripped; none when it is blank).
    # IMPL
    parts = [f"{shown} of {total} tags"]
    if class_code is not None:
        parts.append(f"class {class_code}")
    if violations_only:
        parts.append("violations only")
    if include_ended:
        parts.append("incl. ended")
    if text.strip():
        parts.append(f'filter "{text.strip()}"')
    return "  ".join(parts)
    # END
