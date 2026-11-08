"""Activity text (P2-INS): table columns and cells of the record's Activity tab.

Pure functions: no client call, no I/O, no ``textual`` import. The signatures are frozen; the
bodies are the plain placeholders T02 (the tab) is built against, and T01 replaces them.
"""

from __future__ import annotations

from tl_core.insights.types import ActivityRow

from tl_tui.display import Labels, actor_label
from tl_tui.record_text import event_label
from tl_tui.text import EMPTY, timestamp


def kind_word(kind: str) -> str:
    return kind.capitalize()


def page_has_why(rows: list[ActivityRow]) -> bool:
    return any(r.why for r in rows)


def activity_columns(rows: list[ActivityRow], *, technical: bool) -> tuple[str, ...]:
    return ("When", "Who", "Kind", "What", "From")


def activity_cells(
    row: ActivityRow, labels: Labels, *, technical: bool, with_why: bool
) -> tuple[str, ...]:
    return (
        timestamp(row.event.recorded_at.isoformat()),
        actor_label(labels, row.event.actor),
        kind_word(row.kind),
        event_label(row.event.event_type),
        f"↳ {row.from_key}" if row.related and row.from_key else EMPTY,
    )


def filter_title(revisions_only: bool, related: bool, text: str) -> str:
    return "Activity"


def row_matches(row: ActivityRow, text: str, labels: Labels) -> bool:
    needle = text.lower()
    return any(
        needle in cell.lower()
        for cell in activity_cells(row, labels, technical=False, with_why=False)
    )
