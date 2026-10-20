"""Issue a letter: the PDF, the stub send, the clocks (P1-I5-T07c)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence.errors import (
    InvalidItemError,
    ItemBackdatedError,
    ItemStateError,
    LetterRenderError,
)
from tl_mod_correspondence.testing import PROJECT, CorrWorld, frozen_today
from tl_mod_documents.derivation import store

MONDAY = "2026-10-19"


def stored(world: CorrWorld, file_id: str) -> tuple[bytes, Any]:
    assert world.files is not None
    with open_uow(world.db, readonly=True) as uow:
        opened = world.files.open_file(uow, PROJECT, file_id, actor="user:u")
        try:
            return opened.data.read(), opened.info
        finally:
            opened.data.close()


def test_issuing_stores_a_pdf_marks_the_send_a_stub_and_moves_the_item(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter", body="We confirm the dates.")
        done = world.issue(draft.stream_id)
    assert [e.event_type for e in done.events if e.event_type.startswith("Correspondence")] == [
        "Correspondence.Issued"
    ]
    item = world.item(draft.key or "")
    assert (item.state, item.delivery, item.issued_on) == ("Issued", "stub", MONDAY)
    payload = [p for n, p in world.events_of(draft.stream_id) if n == "Correspondence.Issued"][0]
    assert payload["delivery"] == "stub"
    assert payload["template"] == "general-letter"
    assert payload["issued_on"] == MONDAY and payload["date_reason"] is None
    data, info = stored(world, payload["rendition_file_id"])
    assert data.startswith(b"%PDF-")
    assert hashlib.sha256(data).hexdigest() == payload["rendition_sha256"] == item.rendition_sha256
    assert (info.slot, info.filename, info.record_id) == (
        "rendition",
        "P123-COR-0001.pdf",
        draft.stream_id,
    )
    assert b"P123-COR-0001" in data and b"We confirm the dates." in data


def test_the_letter_is_deterministic(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.draft(domain="general", subtype="letter")
        second = world.draft(domain="general", subtype="letter")
        world.issue(first.stream_id)
        world.issue(second.stream_id)
    one, two = (world.item(k or "") for k in (first.key, second.key))
    assert one.rendition_sha256 != two.rendition_sha256  # the numbers differ
    again = world.item(first.key or "")
    assert again.rendition_sha256 == one.rendition_sha256


def test_the_issue_clock_starts_on_the_issue_day_on_the_project_calendar(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        done = world.issue(draft.stream_id)
    [clock] = world.clocks(draft.key or "")
    assert (clock.label, clock.kind, clock.state) == (
        "Reply expected",
        "response_from_them",
        "running",
    )
    assert (clock.start_on, clock.due_on, clock.calendar) == (
        MONDAY,
        "2026-11-02",
        "P123-default@1",
    )
    assert clock.warn_days == [7, 3, 1]
    payload = [p for n, p in world.events_of(draft.stream_id) if n == "Correspondence.Issued"][0]
    assert payload["clock_ids"] == [clock.id]
    assert done.events[0].event_type == "Record.Created"  # the clock is made first
    started = world.events_of(clock.id)[1][1]
    assert started["trigger"] == "issue" and started["item_number"] == draft.key


def test_a_subtype_without_an_issue_clock_starts_none(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="memo")
        world.issue(draft.stream_id)
    assert world.clocks(draft.key or "") == []
    assert world.item(draft.key or "").state == "Issued"


def test_the_template_is_chosen_by_subtype_or_by_code(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        memo = world.draft(domain="general", subtype="memo")
        world.issue(memo.stream_id)
        other = world.draft(domain="general", subtype="letter")
        world.issue(other.stream_id, template="general-memo")
        with pytest.raises(LetterRenderError, match="nope"):
            world.issue(world.draft(domain="general", subtype="letter").stream_id, template="nope")
        with pytest.raises(LetterRenderError):  # a notification has no template of its own
            world.issue(world.draft(domain="general", subtype="notification").stream_id)

    def template(key: str | None) -> str:
        found = [
            p for n, p in world.events_of(world.item(key or "").id) if n == "Correspondence.Issued"
        ]
        return found[0]["template"]

    assert template(memo.key) == "general-memo"
    assert template(other.key) == "general-memo"


def test_the_issue_date_defaults_to_today_an_earlier_day_needs_a_reason(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        with pytest.raises(ItemBackdatedError):
            world.issue(draft.stream_id, issued_on="2026-10-12")
        with pytest.raises(ItemBackdatedError):
            world.issue(draft.stream_id, issued_on="2026-10-20")
        with pytest.raises(ValidationError):
            world.issue(draft.stream_id, issued_on="2026-10-12", unknown=1)
        assert world.item(draft.key or "").state == "Draft"
        world.issue(draft.stream_id, issued_on="2026-10-12", date_reason="posted a week ago")
    payload = [p for n, p in world.events_of(draft.stream_id) if n == "Correspondence.Issued"][0]
    assert (payload["issued_on"], payload["date_reason"]) == ("2026-10-12", "posted a week ago")
    [clock] = world.clocks(draft.key or "")
    assert (clock.start_on, clock.due_on) == ("2026-10-12", "2026-10-26")


def test_only_a_draft_letter_we_wrote_is_issued_and_only_once(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        got = world.forge_item("P123-COR-0050", state="Received")
        with pytest.raises(ItemStateError):
            world.issue(got)
        draft = world.draft(domain="general", subtype="letter")
        world.issue(draft.stream_id)
        with pytest.raises(ItemStateError):
            world.issue(draft.stream_id)
        incoming_draft = world.forge_item("P123-COR-0051", state="Draft", direction="in")
        with pytest.raises(ItemStateError):
            world.issue(incoming_draft)


def test_a_letter_needs_a_domain_a_recipient_and_a_file_service(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        no_domain = world.draft()
        with pytest.raises(InvalidItemError, match="reclassify"):
            world.issue(no_domain.stream_id)
        no_one = world.draft(domain="general", subtype="letter", to=[])
        with pytest.raises(InvalidItemError, match="recipient"):
            world.issue(no_one.stream_id)
        fine = world.draft(domain="general", subtype="letter")
        with store.use_files(None), pytest.raises(LetterRenderError, match="file service"):
            world.issue(fine.stream_id)
        assert world.item(fine.key or "").state == "Draft"
        world.issue(fine.stream_id)


def test_issuing_a_reply_records_the_answer_to_the_letter_it_replies_to(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        parent = world.forge_item("P123-COR-0060", state="Received")
        owed = world.start_clock(parent, kind="response_from_us", label="Reply due")
        draft = world.draft(responds_to_id=parent, domain="general", subtype="letter")
        done = world.issue(draft.stream_id)
    assert world.item("P123-COR-0060").state == "Responded"
    assert world.item("P123-COR-0060").responded_on == MONDAY
    assert world.clock(owed.stream_id).state == "met"
    responded = [p for n, p in world.events_of(parent) if n == "Correspondence.Responded"]
    assert responded == [{"response_id": draft.stream_id, "responded_on": MONDAY}]
    assert any(e.stream_id == parent for e in done.events)
    [reply_clock] = world.clocks(draft.key or "")  # the reply's own clock keeps running
    assert reply_clock.state == "running"


def test_a_parent_that_is_already_answered_is_left_alone(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        parent = world.forge_item("P123-COR-0060", state="Received")
        first = world.draft(responds_to_id=parent, domain="general", subtype="letter")
        second = world.draft(responds_to_id=parent, domain="general", subtype="letter")
        world.issue(first.stream_id)
        world.issue(second.stream_id)
    assert world.item(second.key or "").state == "Issued"
    responded = [p for n, p in world.events_of(parent) if n == "Correspondence.Responded"]
    assert len(responded) == 1


def test_an_unknown_foreign_or_hidden_draft_is_not_found(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        with pytest.raises(RecordNotFoundError):
            world.issue("01J000000000000000000000")
        with pytest.raises(RecordNotFoundError):
            world.issue(draft.stream_id, scope="project:P999")
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(draft.stream_id, "restricted")
        with pytest.raises(RecordNotFoundError):
            world.issue(draft.stream_id)
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.issue(draft.stream_id)
            assert world.item(draft.key or "").state == "Issued"
