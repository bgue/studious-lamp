"""The Links tab's text, apart from Textual (P2-WEB1-S6; moved from ``widgets/links_tab``).

Rows grouped by relation, a link's status and pin as words, and the expected-but-missing line;
the terminal's ``LinksTab`` and the web record page both use them. No ``textual`` or ``rich`` here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tl_core.links.expected import MissingLink
from tl_core.services.link_queries import LinkView

from tl_tui.text import EMPTY

SUGGESTED = "suggested"


@dataclass(frozen=True)
class TableRow:
    """A table row: a group header (``link_id`` is ``None``) or one link."""

    link_id: str | None
    cells: tuple[str, ...]


def status_text(view: LinkView) -> str:
    """The link's status as text and symbol (never colour alone): ``active``, ``✓ verified``,
    ``! stale``, ``✗ broken``, ``? suggested (0.82)``, ``declined`` or ``retracted``."""
    if view.status == SUGGESTED:
        if view.confidence is None:
            return "? suggested"
        return f"? suggested ({view.confidence:.2f})"
    if view.status == "active":
        return "✓ verified" if view.verified_by else "active"
    if view.status == "stale":
        return "! stale"
    if view.status == "broken":
        return "✗ broken"
    return "declined" if view.declined else "retracted"


def pin_text(view: LinkView) -> str:
    """``floating`` when the link has no pin, else ``▪ <pin>``."""
    return "floating" if view.pin is None else f"▪ {view.pin}"


def group_title(label: str, count: int) -> str:
    """``▾ raised against (2)``."""
    return f"▾ {label} ({count})"


def missing_line(missing: MissingLink, *, technical: bool = True) -> str:
    """``! expected but missing: supporting record (rule: references@Approved)``.

    The rule shows the relation, then ``@<state>`` when the expectation has a ``by_state``, then
    ``, <found> of <needed>`` when more than one link is needed. Plain mode (``technical=False``)
    drops the rule and reads ``! expected but missing: supporting record (1 of 2 needed)``.
    """
    expectation = missing.expectation
    if not technical:
        text = f"! expected but missing: {expectation.display}"
        if missing.needed > 1:
            text += f" ({missing.found} of {missing.needed} needed)"
        return text
    rule = expectation.relation
    if expectation.by_state is not None:
        rule += f"@{expectation.by_state}"
    if missing.needed > 1:
        rule += f", {missing.found} of {missing.needed}"
    return f"! expected but missing: {expectation.display} (rule: {rule})"


def _link_row(view: LinkView, first: str) -> TableRow:
    return TableRow(
        view.link_id,
        (
            first,
            view.other_key or EMPTY,
            view.other_title,
            status_text(view),
            pin_text(view),
            view.note or "",
        ),
    )


def _header_row(title: str) -> TableRow:
    return TableRow(None, (title, "", "", "", "", ""))


def build_rows(views: Sequence[LinkView]) -> list[TableRow]:
    """Group header rows and link rows, in this order.

    Links that are not suggestions are grouped by (direction, relation) in the order given, each
    group headed by ``group_title(label, count)`` with the label of its first link. Suggested links
    form one last group headed ``group_title("suggested", n)``; their first cell is the label so the
    relation stays visible. A link row is ``("", key, title, status_text, pin_text, note)`` with
    ``—`` for a missing key and ``""`` for a missing note.
    """
    groups: dict[tuple[str, str], list[LinkView]] = {}
    suggested: list[LinkView] = []
    for view in views:
        if view.status == SUGGESTED:
            suggested.append(view)
        else:
            groups.setdefault((view.direction, view.relation), []).append(view)

    rows: list[TableRow] = []
    for group in groups.values():
        rows.append(_header_row(group_title(group[0].label, len(group))))
        rows.extend(_link_row(view, "") for view in group)
    if suggested:
        rows.append(_header_row(group_title(SUGGESTED, len(suggested))))
        rows.extend(_link_row(view, view.label) for view in suggested)
    return rows
