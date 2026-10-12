"""What the tag register shows, as pure functions (P1-I1-T09d; brief 9 M2).

The rows, the detail panel and the summary line are text built from ``TagView`` values and nothing
else, so the tests check them without a terminal. None of it decides anything: a number that
breaks the pattern, a class that lacks a property set and a tag in the wrong state are the
module's findings, shown here as they come.

STUB (P1-I1-T09d): the bodies of the functions raise NotImplementedError; their signatures,
docstrings and the column names, `ALL_CLASSES` and the imports are final. Each body has a STEPS
comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
    raise NotImplementedError


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
    raise NotImplementedError


def next_class(current: str | None, classes: Sequence[str]) -> str | None:
    """The class filter after ``current``: ``None`` (all), then each class, then ``None``."""
    # STEPS
    # 1. The cycle is ``[None, *sorted(set(classes))]``.
    # 2. ``current`` is in the cycle: the next one, wrapping to ``None`` after the last. ``current``
    #    is not in it (the class has no tag any more): ``None``.
    raise NotImplementedError


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
    raise NotImplementedError
