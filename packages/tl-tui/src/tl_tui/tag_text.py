"""What the tag register shows, as pure functions (P1-I1-T09d; brief 9 M2; P1-UX-T02).

The rows, the detail panel and the summary line are text built from ``TagView`` values and nothing
else, so the tests check them without a terminal. None of it decides anything: a number that
breaks the pattern, a class that lacks a property set and a tag in the wrong state are the
module's findings, shown here as they come.

The panel is a ``layout.Page`` built from the rows of ``details.tags.tag_content`` (P1-UX3), the
same rows as the tag's Details tab. Plain mode speaks in words: the class as ``Control valve``,
the properties as labels (``Valve data / Body material``), the number parts one per line.
Technical mode adds the raw class code and the ``area=47 mnemonic=FV seq=1001`` segments.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_engineering.views import TagView

from tl_tui.client import ClientInterface
from tl_tui.details import rows_page
from tl_tui.details.tags import class_text, number_fits, tag_content
from tl_tui.display import Labels, code_label, humanize
from tl_tui.layout import Page, identity_line, join_facts, plain_lines
from tl_tui.text import EMPTY, conformance_mark

COLUMNS = ("Number", "Title", "Class", "Status", "Number check", "Conformance")
DROP = ("Number check", "Class")  # left out, least needed first, when the log would not fit
ALL_CLASSES = "all classes"


def row_cells(view: TagView, labels: Labels | None = None) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS`` (the number and title first)."""
    number_check = "ok" if number_fits(view) else "does not fit"
    return (
        view.number,
        view.title,
        class_text(view),
        humanize(view.status) if view.status else EMPTY,
        number_check,
        conformance_mark(view.conformance),
    )


CONFORMANCE_STATE = {
    "ok": "✓ Conforms",
    "warning": "! Has warnings",
    "nonconformant": "✗ Does not conform",
    "waived": "Waived",
}


def tag_page(
    view: TagView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    client: ClientInterface | None = None,
) -> Page:
    """The panel under the table (skill ``tui-layout``): the identity line, the conformance as the
    state, the summary (class, area, status), the key facts, the number in its parts and what the
    tag lacks. ``technical`` keeps the class code and shows the number's segments as stored."""
    lab = labels if labels is not None else Labels()
    area = view.segments.get("area") or view.area
    return rows_page(
        tag_content(view, lab, client=client),
        identity=identity_line(view.number, view.title),
        state=CONFORMANCE_STATE.get(view.conformance, conformance_mark(view.conformance)),
        summary=join_facts(
            class_text(view) if view.class_code else "",
            f"area {code_label(lab, 'area', area)}" if area else "",
            humanize(view.status) if view.status else "",
        ),
        technical=technical,
        panel=True,
    )


def detail_lines(
    view: TagView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel as plain lines."""
    return plain_lines(tag_page(view, labels, technical=technical))


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
