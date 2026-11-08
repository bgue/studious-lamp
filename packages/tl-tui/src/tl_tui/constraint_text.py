"""The text of the constraint review and of a constraint's page, as pure functions (P2-I2 T04b;
spec §8, skill ``tui-layout``; the model is ``tl_tui.awp_text``).

The values come from ``tl_api.routes.constraints.ConstraintRow`` and nothing else: no client call,
no I/O, and no ``textual`` import, so the web client's constraint pages (TW2) use the same words.
The review groups (owner, type, age) are ordered here by ``order_by_group``; the band words and
the group order come from ``tl_core.constraints.review``. Owner and need-by show ``-`` when there
is none (the words of the constraint review, not the ``—`` of the fixed sections).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from tl_core.constraints.review import AGE_BANDS, BY_WORDS

from tl_tui.display import Labels, humanize
from tl_tui.layout import Page, Prop, Section, cut_text, identity_line, join_facts, state_line

if TYPE_CHECKING:
    from tl_api.routes.constraints import ConstraintRow

CONSTRAINT_COLUMNS = ("Constraint", "Subject", "Type", "State", "Owner", "Need by", "Age", "Source")
CONSTRAINT_DROP = ("Source", "Need by")  # dropped first at narrow width
CONSTRAINT_RIGHT = ("Age",)
NONE = "-"  # the words' mark for a value that is absent
AGING_MARK = " !"  # after the age of a constraint that is aging
PANEL_DESCRIPTION = 200  # characters of the description a panel shows; the page shows all
TRUNCATED_NOTE = "(first 500 only)"  # a grouped list whose groups cover only the first 500
GROUPED_BY = "grouped by"


def _count(n: int) -> str:
    return "1 constraint" if n == 1 else f"{n} constraints"


def _day(value: str | None) -> str:
    """The day of an ISO date-time (``2026-11-03T08:00:00``); ``-`` for none."""
    return value[:10] if value else NONE


def _band_index(age_days: int) -> int:
    """The index in ``AGE_BANDS`` of the band that holds ``age_days``."""
    for index, (_label, _low, high) in enumerate(AGE_BANDS):
        if high is None or age_days <= high:
            return index
    raise AssertionError("AGE_BANDS covers every age")  # pragma: no cover


def _group_rank(row: ConstraintRow, by: str) -> tuple[int, str]:
    """The place of a row's group: owners by name with ``-`` last, types by name, ages in band
    order."""
    if by == "owner":
        owner = row.owner or NONE
        return (int(owner == NONE), owner)
    if by == "category":
        return (0, row.category)
    return (_band_index(row.age_days), "")


def constraint_cells(row: ConstraintRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a review row, in the order of ``CONSTRAINT_COLUMNS``. ``labels`` is
    accepted for the same signature as ``cwp_cells``; the words are humanized, there is no code
    list for them yet."""
    age = f"{row.age_days} d" + (AGING_MARK if row.aging else "")
    return (
        row.key,
        row.subject_key,
        humanize(row.category),
        humanize(row.state),
        row.owner or NONE,
        _day(row.due_at),
        age,
        humanize(row.source),
    )


def constraint_summary(
    total: int,
    shown: int,
    *,
    by: str | None = None,
    blocking: int = 0,
    aging: int = 0,
    truncated: bool = False,
) -> str:
    """``12 constraints, 4 blocking, 3 aging``; ``5 of 12 constraints, ...`` when fewer are shown;
    ``, grouped by owner`` when grouped; ``(first 500 only)`` when the groups stop there."""
    if by is not None and by not in BY_WORDS:
        raise ValueError(f"by must be one of {', '.join(BY_WORDS)}")
    head = _count(shown) if shown == total else f"{shown} of {_count(total)}"
    parts = [f"{head}, {blocking} blocking, {aging} aging"]
    if by is not None:
        parts[0] += f", {GROUPED_BY} {by}"
    if truncated:
        parts.append(TRUNCATED_NOTE)
    return " ".join(parts)


def order_by_group(rows: Sequence[ConstraintRow], by: str) -> list[ConstraintRow]:
    """The rows in group order (``by`` owner, category or age), then by key within a group."""
    if by not in BY_WORDS:
        raise ValueError(f"by must be one of {', '.join(BY_WORDS)}")
    return sorted(rows, key=lambda row: (_group_rank(row, by), row.key))


def constraint_page(
    row: ConstraintRow,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The page of one constraint: identity (``<key> · <subject_key>``), state, the summary (a
    panel only), the facts, the description (cut in a panel), and the technical rows when
    ``technical``. No ids appear on the page."""
    due = _day(row.due_at)
    description = (row.description or "").strip()
    if panel:
        description = cut_text(description, PANEL_DESCRIPTION) if description else ""
    facts = Section(
        "Facts",
        (
            Prop("Type", humanize(row.category)),
            Prop("Severity", humanize(row.severity)),
            Prop("Phase", humanize(row.phase)),
            Prop("Owner", row.owner or NONE),
            Prop("Need by", due),
            Prop("Source", humanize(row.source)),
        ),
    )
    sections = [facts, Section("Description", (description,) if description else (), NONE)]
    if technical:
        sections.append(
            Section(
                "Technical",
                (Prop("Subject type", row.subject_type), Prop("Raised on", row.raised_on)),
            )
        )
    summary = ""
    if panel:
        summary = join_facts(
            humanize(row.category),
            row.owner,
            f"Need by {due}" if row.due_at else None,
            f"{row.age_days} d old",
        )
    return Page(
        identity=identity_line(row.key, row.subject_key),
        state=state_line(humanize(row.state)),
        sections=tuple(sections),
        summary=summary,
    )
