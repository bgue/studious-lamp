"""The clocks source of the Checks read: response clocks of one item that are past due."""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_core.insights.types import CheckFinding, RecordFacts

from tl_mod_correspondence.views import clock_views


def findings(conn: Connection, facts: RecordFacts, viewer: Viewer | None) -> list[CheckFinding]:
    """Each open clock of the record whose effective state is expired or whose days left is
    negative. The view reads as the current viewer (the caller has set it)."""
    out: list[CheckFinding] = []
    for clock in clock_views(conn, facts.scope, open_only=True):
        if clock.item_id != facts.record_id:
            continue
        if clock.effective_state != "expired" and not (
            clock.days_left is not None and clock.days_left < 0
        ):
            continue
        late = f", {-clock.days_left} days late" if clock.days_left and clock.days_left < 0 else ""
        out.append(
            CheckFinding(
                source="clocks",
                subject_id=facts.record_id,
                state="overdue",
                text=f"{clock.label} was due {clock.due_on}{late}",
                since=clock.due_on,
                severity="blocking",
            )
        )
    return out
