"""The RFI record: narrative first, then the status timeline, then the register (P1-UX2-S5).

A fake client gives the order and the plain words; a real ledger gives an RFI taken through every
step, as a plain reader and as a document controller (who alone reads the escalation).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes_rfi_record import ITEM_ID, LONG_QUESTION, PROJECT, RFI_ID, rfi_world
from tl_adapters.db import as_target, open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, frozen_today
from tl_mod_documents.derivation import store
from tl_tui.details import DetailRow, details_for
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.record_view import details_lines

RFI = "correspondence.TechnicalItem"
ITEM = "correspondence.Correspondence"
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
TECHNICAL = DisplayMode()
TECHNICAL.technical = True
NARRATIVE = ["Subject", "Question", "Proposed solution", "Answer"]
METADATA = ["Type", "Number", "Kind", "State", "Confidentiality", "Discipline", "Needed by"]


def rows_of(client: Any, record_type: str, key: str, mode: DisplayMode | None = None) -> list[Any]:
    record = {"type": record_type, "key": key, "scope": f"project:{PROJECT}", "version": 1}
    return details_for(client, PROJECT, record, Labels(), mode or DisplayMode())


def labels_of(rows: list[DetailRow]) -> list[str]:
    return [row.label for row in rows]


def timeline_of(rows: list[DetailRow]) -> list[DetailRow]:
    """The rows between the ``Timeline`` heading and the metadata (the technical row aside)."""
    labels = labels_of(rows)
    if "Timeline" not in labels:
        return []
    start = labels.index("Timeline") + 1
    stop = labels.index("Type")
    return [r for r in rows[start:stop] if r.label != "Timeline times"]


# --- the fake RFI -------------------------------------------------------------------------------


def test_the_details_start_with_the_narrative() -> None:
    rows = rows_of(rfi_world(), RFI, "P123-RFI-0001")
    assert labels_of(rows)[:4] == NARRATIVE


def test_a_question_of_three_thousand_characters_is_shown_whole() -> None:
    assert len(LONG_QUESTION) == 3000
    rows = {r.label: r.value for r in rows_of(rfi_world(), RFI, "P123-RFI-0001")}
    assert rows["Question"] == LONG_QUESTION
    text = details_lines(rows_of(rfi_world(), RFI, "P123-RFI-0001"))
    assert LONG_QUESTION in text and "…" not in text


def test_the_answer_row_names_who_answered_and_when() -> None:
    rows = {r.label: r.value for r in rows_of(rfi_world(), RFI, "P123-RFI-0001")}
    assert rows["Answer"] == "Re-route above the beam."
    assert rows["Answered by"] == "cy on 2026-10-12"  # the latest answer's author and its day
    assert "Answered on" not in rows
    assert rows["Answerer says cost"] == "Yes" and rows["Answerer says schedule"] == "No"
    assert rows["Raiser expects cost"] == "Unknown"
    assert rows["Review"] == "Accepted on 2026-10-13"


def test_an_answer_without_its_event_still_gives_the_day() -> None:
    client = rfi_world()
    client._events[RFI_ID] = []  # pyright: ignore[reportPrivateUsage]
    rows = {r.label: r.value for r in rows_of(client, RFI, "P123-RFI-0001")}
    assert rows["Answered on"] == "2026-10-12" and "Answered by" not in rows
    assert [r.value for r in timeline_of(rows_of(client, RFI, "P123-RFI-0001"))] == [
        "System: Answer required clock met - Answered"
    ] * 2


def test_the_timeline_follows_the_narrative_and_leads_the_metadata() -> None:
    labels = labels_of(rows_of(rfi_world(), RFI, "P123-RFI-0001"))
    heading = labels.index("Timeline")
    assert labels.index("Review") < heading < labels.index("Type")
    assert labels.index("Answer") < labels.index("Raiser expects cost") < heading
    assert labels[labels.index("Type") :][:7] == METADATA


def test_the_timeline_rows_are_dated_oldest_first_with_who_and_note() -> None:
    timeline = timeline_of(rows_of(rfi_world(), RFI, "P123-RFI-0001"))
    assert [r.label for r in timeline] == sorted(r.label for r in timeline)
    assert [r.value for r in timeline][:3] == [
        "amy: Raised",
        "amy: Submitted",
        "ben: Issued",
    ]
    values = [r.value for r in timeline]
    assert "amy: Answer rejected - does not answer the clash" in values
    assert "amy: Reissued - names both beams" in values
    assert values[-1] == "amy: Answer accepted"
    assert values.index("System: Answer required clock met - Answered") > values.index(
        "cy: Answered"
    )
    assert not any("edited" in v or "Technical" in v or "Workflow" in v for v in values)


def test_a_draft_rfi_has_no_answer_and_a_one_row_timeline() -> None:
    rows = rows_of(rfi_world(), RFI, "P123-RFI-0003")
    assert not {"Answer", "Answered by", "Answered on", "Review"} & set(labels_of(rows))
    assert [(r.label, r.value) for r in timeline_of(rows)] == [("2026-10-05", "amy: Raised")]


def test_plain_mode_shows_no_time_no_stored_actor_and_nothing_technical() -> None:
    client = rfi_world()
    plain = rows_of(client, RFI, "P123-RFI-0001")
    text = details_lines(plain)
    assert "Timeline times" not in text and "user:" not in text
    assert find_technical(text, Labels(domains={"technical": "Technical"})) == []
    assert not any(r.technical for r in plain)


def test_technical_mode_adds_the_times_in_one_hanging_block() -> None:
    rows = rows_of(rfi_world(), RFI, "P123-RFI-0001", TECHNICAL)
    [times] = [r for r in rows if r.label == "Timeline times"]
    first = times.value.splitlines()[0]
    assert first.startswith("2026-10-05 09:00  user:amy  Raised")
    lines = details_lines(rows).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Timeline times"))
    indent = lines[start].index("2026-10-05")  # the value column
    assert indent > len("Timeline times")
    assert lines[start + 1] == " " * indent + times.value.splitlines()[1]
    assert {"Key", "Version", "Scope", "Schema hash"} <= set(labels_of(rows))


def test_a_heading_row_has_no_trailing_space() -> None:
    lines = details_lines([DetailRow("Timeline", ""), DetailRow("2026-10-05", "amy: Raised")])
    assert lines.splitlines()[0] == "Timeline"


# --- a correspondence item ----------------------------------------------------------------------


def test_an_item_with_only_a_body_shows_the_narrative_and_one_row() -> None:
    rows = rows_of(rfi_world(), ITEM, "P123-COR-0001")
    assert labels_of(rows)[:2] == ["Subject", "Message"]
    assert [r.value for r in rows if r.label == "Message"] == [
        "Please find the revised programme attached."
    ]
    assert [(r.label, r.value) for r in timeline_of(rows)] == [("2026-10-05", "amy: Received")]


def test_an_item_with_no_body_or_history_has_no_message_and_no_timeline() -> None:
    client = rfi_world()
    client._events[ITEM_ID] = []  # pyright: ignore[reportPrivateUsage]
    item = client._items[PROJECT]["P123-COR-0001"]  # pyright: ignore[reportPrivateUsage]
    client._items[PROJECT]["P123-COR-0001"] = item.model_copy(update={"body": None})  # pyright: ignore[reportPrivateUsage]
    rows = rows_of(client, ITEM, "P123-COR-0001")
    assert "Message" not in labels_of(rows) and "Timeline" not in labels_of(rows)
    assert labels_of(rows)[0] == "Subject" and "Number" in labels_of(rows)


# --- a real RFI, taken through every step -------------------------------------------------------

GOOD = "correct horse battery"


class Walk:
    def __init__(self, path: Path, rfi_id: str) -> None:
        self.path = path
        self.rfi_id = rfi_id

    def client(self, actor: str) -> EmbeddedClient:
        return EmbeddedClient(SqliteUowFactory(self.path), actor=actor)


@pytest.fixture
def walk(tmp_path: Path) -> Iterator[Walk]:
    path = tmp_path / "tl.db"
    create_schema(path)
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        world = CorrWorld(as_target(str(path)), tmp_path / "objects")
        with store.use_files(world.files):
            with open_uow(path) as uow:
                for name, roles in (("dora", ["user", "document_controller"]), ("kim", ["user"])):
                    accounts.create_account(
                        uow, username=name, display_name=name, kind="person", roles=roles,
                        password=prepare_password(GOOD, username=name), by="svc:test",
                    )  # fmt: skip
            yield Walk(path, _walk_rfi(world))


def _walk_rfi(world: CorrWorld) -> str:
    """Raise, submit, issue, answer, reject, re-issue, issue, answer, accept, escalate, close."""
    with frozen_today("2026-10-19"):
        made = world.raise_technical(required_by="2026-11-02", actor="user:amy")
        rfi_id = made.stream_id
        world.submit_technical(rfi_id, actor="user:amy")
        world.update_technical(rfi_id, proposed_solution="Move the beam.", actor="user:amy")
    with frozen_today("2026-10-19"), cf.use_viewer(CONTROLLER):
        world.issue_technical(rfi_id, actor="user:ben")
    with frozen_today("2026-10-22"):
        world.answer_technical(rfi_id, answer="Not sure.", cost_impact="yes", actor="user:cy")
        world.review_technical(rfi_id, "rejected", note="no", actor="user:amy")
        world.reissue_technical(rfi_id, reason="names both beams", actor="user:amy")
    with frozen_today("2026-10-23"), cf.use_viewer(CONTROLLER):
        world.issue_technical(rfi_id, actor="user:ben")
    with frozen_today("2026-10-26"):
        world.answer_technical(rfi_id, answer="Re-route.", cost_impact="yes", actor="user:cy")
        world.review_technical(rfi_id, "accepted", actor="user:amy")
    with frozen_today("2026-10-27"), cf.use_viewer(CONTROLLER):
        world.escalate(rfi_id, actor="user:ben")
    with frozen_today("2026-10-28"):
        world.close_technical(rfi_id, actor="user:amy")
    return rfi_id


def real_rows(walk: Walk, actor: str, mode: DisplayMode | None = None) -> list[DetailRow]:
    client = walk.client(actor)
    return rows_of(client, RFI, "P123-RFI-0001", mode)


def test_the_real_walk_reads_as_its_steps_oldest_first(walk: Walk) -> None:
    rows = real_rows(walk, "user:kim")
    assert labels_of(rows)[:4] == NARRATIVE
    values = [r.value for r in timeline_of(rows)]
    steps = [v.split(": ", 1)[1].split(" - ")[0] for v in values if not v.startswith("System")]
    assert steps == [
        "Raised", "Submitted", "Issued", "Answered", "Answer rejected", "Reissued",
        "Issued", "Answered", "Answer accepted", "Closed",
    ]  # fmt: skip
    assert "amy: Answer rejected - no" in values and "amy: Reissued - names both beams" in values
    assert [v for v in values if v.startswith("System")] == [
        "System: Answer required clock met - Answered"
    ] * 2


def test_the_real_walk_names_the_answerer_and_the_day(walk: Walk) -> None:
    rows = {r.label: r.value for r in real_rows(walk, "user:kim")}
    assert rows["Answered by"] == "cy on 2026-10-26"
    assert rows["Answer"] == "Re-route." and rows["Proposed solution"] == "Move the beam."


def test_the_real_walk_leaks_nothing_in_plain_mode(walk: Walk) -> None:
    for actor in ("user:kim", "user:dora"):
        text = details_lines(real_rows(walk, actor))
        assert find_technical(text, Labels(domains={"technical": "Technical"})) == [], actor
        assert "svc:" not in text and "Workflow" not in text and "Technical." not in text


def test_the_escalation_is_in_the_timeline_only_for_a_reader_of_the_new_item(walk: Walk) -> None:
    """History is viewer-filtered (ADR-0016): the plain reader finds no trace of the escalation."""
    plain = real_rows(walk, "user:kim")
    assert "Escalated to" not in labels_of(plain)
    assert not any("Escalated" in r.value for r in plain)
    controller = real_rows(walk, "user:dora")
    assert [r.value for r in controller if r.label == "Escalated to"] == ["P123-EW-0001 (Draft)"]
    escalated = [r.value for r in timeline_of(controller) if "Escalated" in r.value]
    assert escalated == ["ben: Escalated - to P123-EW-0001"]


def test_the_real_walk_in_technical_mode_adds_times_and_stored_actors(walk: Walk) -> None:
    rows = real_rows(walk, "user:dora", TECHNICAL)
    [times] = [r for r in rows if r.label == "Timeline times"]
    assert "user:amy" in times.value and "Escalated" in times.value
    assert times.value.splitlines()[0].split("  ")[0].count(":") == 1  # a time of day
