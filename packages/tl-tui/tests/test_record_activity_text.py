"""The Activity tab's text: columns, cells, the filter title and the text filter (P2-INS-T01)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tl_core.insights.types import ActivityRow
from tl_core.ledger import Event
from tl_tui.display import Labels, find_technical
from tl_tui.record_activity_text import (
    activity_cells,
    activity_columns,
    filter_title,
    kind_word,
    page_has_why,
    row_matches,
)
from tl_tui.record_text import history_cells

WHEN = datetime(2026, 11, 7, 14, 2, tzinfo=UTC)
LABELS = Labels()
PLAIN = {"technical": False, "with_why": False}


def event(event_type: str, actor: str, payload: dict | None = None) -> Event:
    return Event(
        event_type=event_type,
        payload=payload or {},
        seq=41,
        event_id="01JDEVENT0000000000000000A",
        stream_id="rec-1",
        stream_type="Record",
        stream_version=3,
        scope="project:P123",
        actor=actor,
        recorded_at=WHEN,
        effective_at=WHEN,
        correlation_id="corr-1",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="h",
    )


def row(
    event_type: str = "Record.Updated", actor: str = "user:Maria Lee", **kw: object
) -> ActivityRow:
    kind = kw.pop("kind", "change")
    payload = kw.pop("payload", None)
    return ActivityRow(event=event(event_type, actor, payload), kind=kind, **kw)  # type: ignore[arg-type]


def plain(item: ActivityRow) -> tuple[str, ...]:
    return activity_cells(item, LABELS, **PLAIN)


def test_kind_word_is_one_word_per_kind() -> None:
    words = {kind: kind_word(kind) for kind in ("change", "move", "link", "file", "post")}
    assert words == {
        "change": "Change",
        "move": "Move",
        "link": "Link",
        "file": "File",
        "post": "Post",
    }
    assert kind_word("proposal") == "Proposal"
    assert kind_word("constraint") == "Constraint"
    assert kind_word("check") == "Check run"


def test_a_move_row_reads_its_kind_and_its_label() -> None:
    item = row("Workflow.Transitioned", kind="move")
    cells = plain(item)
    assert cells[2] == "Move"
    assert cells[3] == "Transitioned"


def test_a_proposal_accepted_by_a_person_reads_by_name() -> None:
    item = row(
        "Proposal.Accepted",
        "user:Maria Lee",
        kind="proposal",
        decided_by="user:Maria Lee",
    )
    cells = plain(item)
    assert cells[1] == "accepted by Maria Lee"
    assert cells[3] == "Proposal accepted"


def test_a_proposal_filed_by_an_agent_names_the_agent() -> None:
    item = row("Proposal.Created", "agent:planner", kind="proposal")
    cells = plain(item)
    assert cells[1] == "Agent: planner"
    assert cells[2] == "Proposal"
    assert cells[3] == "Proposal filed"


def test_a_rejected_proposal_reads_rejected() -> None:
    item = row("Proposal.Rejected", "user:Maria Lee", kind="proposal", decided_by="user:Maria Lee")
    assert plain(item)[1] == "rejected by Maria Lee"
    assert plain(item)[3] == "Proposal rejected"


def test_a_summary_that_starts_with_the_label_word_stands_alone() -> None:
    item = row(payload={"changes": {"size_in": {"from": 4, "to": 6}}})
    assert plain(item)[3] == "changed: Size in"


def test_a_readiness_row_reads_its_note() -> None:
    item = row("IWP.ReadinessEvaluated", "svc:checker", kind="check", note="5 of 7 ready")
    cells = plain(item)
    assert cells[2] == "Check run"
    assert cells[3] == "Readiness checked: 5 of 7 ready"


def test_a_related_row_shows_its_from_key_and_an_own_row_a_dash() -> None:
    related = row(related=True, from_key="P123-RFI-0328")
    own = row()
    assert plain(related)[4] == "↳ P123-RFI-0328"
    assert plain(own)[4] == "—"


def test_a_related_row_reads_its_label_without_a_summary() -> None:
    item = row("Record.Updated", related=True, from_key="P123-RFI-0328")
    assert plain(item)[3] == "Changed"


def test_the_why_column_appears_only_when_a_row_has_a_why() -> None:
    bare = row()
    with_why = row(why="Schedule slipped")
    assert not page_has_why([bare])
    assert page_has_why([bare, with_why])
    assert activity_columns([bare], technical=False)[-1] == "From"
    assert activity_columns([bare, with_why], technical=False)[-1] == "Why"
    cells = activity_cells(with_why, LABELS, technical=False, with_why=True)
    assert cells[-1] == "Schedule slipped"
    assert activity_cells(bare, LABELS, technical=False, with_why=False)[-1] == "—"


def test_plain_columns_and_cells_line_up() -> None:
    rows = [row(), row("Proposal.Created", "agent:planner", kind="proposal", why="x")]
    columns = activity_columns(rows, technical=False)
    assert columns == ("When", "Who", "Kind", "What", "From", "Why")
    for item in rows:
        cells = activity_cells(item, LABELS, technical=False, with_why=True)
        assert len(cells) == len(columns)
    no_why = activity_cells(rows[0], LABELS, technical=False, with_why=False)
    assert len(no_why) == len(activity_columns([rows[0]], technical=False))


def test_technical_columns_match_the_history_cells_plus_from() -> None:
    item = row(related=True, from_key="P123-RFI-0328")
    columns = activity_columns([item], technical=True)
    assert columns == ("#", "When", "Event", "Actor", "Summary", "From")
    cells = activity_cells(item, LABELS, technical=True, with_why=False)
    assert cells[:5] == history_cells(item.event, LABELS, technical=True)
    assert cells[5] == "↳ P123-RFI-0328"
    assert cells[0] == "3"


def test_the_filter_title_has_four_states() -> None:
    assert filter_title(False, True, "") == "Activity"
    assert filter_title(True, True, "") == "Activity · Revisions only"
    assert filter_title(False, False, "") == "Activity · Related off"
    assert filter_title(False, True, "pump") == 'Activity · "pump"'
    assert filter_title(True, False, "pump") == 'Activity · Revisions only · Related off · "pump"'


def test_the_text_filter_matches_what_who_and_from() -> None:
    item = row("Record.Updated", "user:Maria Lee", related=True, from_key="P123-RFI-0328")
    assert row_matches(item, "MARIA", LABELS)
    assert row_matches(item, "changed", LABELS)
    assert row_matches(item, "rfi-0328", LABELS)
    assert not row_matches(item, "pump", LABELS)


@pytest.mark.parametrize(
    "item",
    [
        row(),
        row("Proposal.Created", "agent:planner", kind="proposal", why="why text"),
        row("Proposal.Accepted", "user:Maria Lee", kind="proposal", decided_by="user:Maria Lee"),
        row("IWP.ReadinessEvaluated", "svc:checker", kind="check", note="5 of 7 ready"),
        row("Record.Updated", related=True, from_key="P123-RFI-0328"),
    ],
)
def test_plain_cells_hold_no_technical_token(item: ActivityRow) -> None:
    assert find_technical(" ".join(plain(item))) == []


def test_an_unknown_event_type_falls_back_to_humanize() -> None:
    item = row("Stock.Renamed", "user:Maria Lee")
    assert plain(item)[3] == "Renamed"
    assert plain(row("Quantity.Reserved", "user:Maria Lee"))[3] == "Reserved"
