"""Confirm a triage and reclassify an item (P1-I5-T07b)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ValidationError
from tl_core import confidentiality as cf
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_correspondence import catalog
from tl_mod_correspondence import domains as dm
from tl_mod_correspondence.errors import (
    InvalidClockError,
    InvalidItemError,
    ItemStateError,
    UnknownDomainError,
)
from tl_mod_correspondence.testing import CorrWorld, frozen_today

MONDAY = "2026-10-19"


def names(done: Any) -> list[str]:
    return [e.event_type for e in done.events]


def test_confirming_a_triage_records_the_domain_and_moves_the_item(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        done = world.triage(made.stream_id)
    assert names(done) == [
        "Correspondence.Triaged",
        "Correspondence.Updated",  # the General letter wants an answer
        "Workflow.Transitioned",
    ]
    item = world.item("P123-COR-0001")
    assert (item.state, item.domain, item.subtype) == ("Triaged", "general", "letter")
    assert (item.triaged_on, item.triaged_by) == (MONDAY, "user:u")
    assert item.response_required is True  # the General letter wants an answer
    triaged = [p for n, p in world.events_of(made.stream_id) if n == "Correspondence.Triaged"][0]
    assert triaged == {
        "domain": "general",
        "subtype": "letter",
        "referenced_ids": [],
        "clock_ids": [],
        "triaged_on": MONDAY,
        "suggestion": None,
    }


def test_the_subtype_decides_whether_an_answer_is_expected_unless_the_person_says(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        memo = world.receive("Memo to all staff")
        world.triage(memo.stream_id, subtype="memo")
        letter = world.receive("A letter")
        world.triage(letter.stream_id, response_required=False, response_due="2026-11-02")
    assert world.item(memo.key or "").response_required is False
    kept = world.item(letter.key or "")
    assert (kept.response_required, kept.response_due) == (False, "2026-11-02")


def test_the_event_keeps_the_suggestion_only_when_the_person_chose_differently(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Transmittal 12 for review", body="Drawings attached.")
        world.triage(made.stream_id, domain="general")
        same = world.receive("Transmittal 13 for review", body="Drawings attached.")
        world.triage(same.stream_id, domain="document_control", subtype="transmittal")
    first = [p for n, p in world.events_of(made.stream_id) if n == "Correspondence.Triaged"][0]
    second = [p for n, p in world.events_of(same.stream_id) if n == "Correspondence.Triaged"][0]
    assert first["suggestion"] == "document_control"
    assert second["suggestion"] is None


def test_a_subtype_with_a_receipt_clock_starts_it_on_the_day_the_item_arrived(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Submittal of revision C", received_on="2026-10-12")
        world.triage(made.stream_id, domain="document_control", subtype="submittal")
    [clock] = world.clocks(made.key or "")
    assert (clock.label, clock.kind, clock.day_type, clock.duration_days) == (
        "Review return due",
        "response_from_us",
        "working",
        10,
    )
    assert (clock.start_on, clock.due_on, clock.warn_days) == (
        "2026-10-12",
        "2026-10-26",
        [3, 1],
    )
    started = world.events_of(clock.id)[1][1]
    assert started["trigger"] == "receipt" and started["item_id"] == made.stream_id
    triaged = [p for n, p in world.events_of(made.stream_id) if n == "Correspondence.Triaged"][0]
    assert triaged["clock_ids"] == [clock.id]


def test_the_issue_clocks_do_not_start_at_triage_and_start_clocks_false_skips_the_rest(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        general = world.receive()
        world.triage(general.stream_id)
        skipped = world.receive("Submittal two")
        world.triage(
            skipped.stream_id, domain="document_control", subtype="submittal", start_clocks=False
        )
    assert world.clocks(general.key or "") == []
    assert world.clocks(skipped.key or "") == []


def test_the_references_the_person_confirmed_become_links(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        earlier = world.receive("Earlier letter")
        made = world.receive("Follow-up")
        world.triage(made.stream_id, referenced_ids=[earlier.stream_id])
    links = world.rows(
        "SELECT from_id, to_id, relation, source FROM cur_links WHERE from_id = :f",
        f=made.stream_id,
    )
    assert [(r["to_id"], r["relation"]) for r in links] == [(earlier.stream_id, "references")]
    assert links[0]["source"] == "rule"  # made by the triage rule, not typed in by hand
    triaged = [p for n, p in world.events_of(made.stream_id) if n == "Correspondence.Triaged"][0]
    assert triaged["referenced_ids"] == [earlier.stream_id]


def test_a_reference_that_is_unknown_foreign_hidden_repeated_or_itself_is_refused(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        other = world.receive("Other")
        secret = world.receive("Secret")
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(secret.stream_id, "restricted")
        foreign = world.receive("Foreign", scope="project:P999")
        made = world.receive("Mine")
        for ref in ("01J000000000000000000000", secret.stream_id, foreign.stream_id):
            with pytest.raises(RecordNotFoundError):
                world.triage(made.stream_id, referenced_ids=[ref])
        with pytest.raises(InvalidItemError):
            world.triage(made.stream_id, referenced_ids=[other.stream_id, other.stream_id])
        with pytest.raises(InvalidItemError):
            world.triage(made.stream_id, referenced_ids=[made.stream_id])
    assert world.item(made.key or "").state == "Received"
    assert world.rows("SELECT link_id FROM cur_links") == []


def test_only_a_received_item_is_triaged_and_only_to_a_known_domain_and_subtype(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        draft = world.draft()
        with pytest.raises(ItemStateError):
            world.triage(draft.stream_id)
        with pytest.raises(UnknownDomainError):
            world.triage(made.stream_id, domain="legal")
        with pytest.raises(UnknownDomainError):
            world.triage(made.stream_id, domain="general", subtype="submittal")
        with pytest.raises(ValidationError):
            world.triage(made.stream_id, unknown=1)
        world.triage(made.stream_id)
        with pytest.raises(ItemStateError):
            world.triage(made.stream_id)
    assert world.item(made.key or "").state == "Triaged"


@pytest.fixture
def clause_domains() -> Iterator[None]:
    """The submittal subtype's clock cites clause CT-1/20.1."""
    base = catalog.domain_set()
    changed: list[dm.DomainDefinition] = []
    for definition in base.all():
        if definition.code != "document_control":
            changed.append(definition)
            continue
        subtypes = []
        for subtype in definition.subtypes:
            if subtype.code == "submittal":
                clock = subtype.clocks[0].model_copy(update={"clause": "CT-1/20.1"})
                subtype = subtype.model_copy(update={"clocks": (clock,)})
            subtypes.append(subtype)
        changed.append(definition.model_copy(update={"subtypes": tuple(subtypes)}))
    with catalog.use_domains(dm.DomainSet(changed)):
        yield


def test_a_clock_template_that_names_a_clause_cites_it_and_needs_it_registered(
    world: CorrWorld, clause_domains: None
) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Submittal one")
        with pytest.raises(InvalidClockError, match="CT-1/20.1"):
            world.triage(first.stream_id, domain="document_control", subtype="submittal")
        assert world.item(first.key or "").state == "Received"
        clause_id = world.forge_clause()
        world.triage(first.stream_id, domain="document_control", subtype="submittal")
    [clock] = world.clocks(first.key or "")
    assert clock.clause_id == clause_id


def test_a_hidden_or_foreign_item_is_not_found(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        with pytest.raises(RecordNotFoundError):
            world.triage(made.stream_id, scope="project:P999")
        with pytest.raises(RecordNotFoundError):
            world.triage("01J000000000000000000000")
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(made.stream_id, "restricted")
        with pytest.raises(RecordNotFoundError):
            world.triage(made.stream_id)


def test_reclassify_changes_the_domain_and_keeps_the_state(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        world.triage(made.stream_id)
        world.reclassify(made.stream_id, "document_control", "submittal", reason="It has drawings")
    item = world.item(made.key or "")
    assert (item.state, item.domain, item.subtype) == ("Triaged", "document_control", "submittal")
    payload = world.events_of(made.stream_id)[-1][1]
    assert payload == {
        "from_domain": "general",
        "from_subtype": "letter",
        "domain": "document_control",
        "subtype": "submittal",
        "reason": "It has drawings",
    }


def test_reclassify_takes_a_draft_and_a_received_item(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain=None, subtype=None)
        assert world.item(draft.key or "").domain is None
        world.reclassify(draft.stream_id, "general", "letter")
        got = world.receive()
        world.reclassify(got.stream_id, "general", "memo")
    assert world.item(draft.key or "").subtype == "letter"
    assert world.item(got.key or "").subtype == "memo"
    assert world.events_of(draft.stream_id)[-1][1]["from_domain"] is None


def test_reclassify_refuses_no_change_a_blank_reason_an_issued_item_and_unknown_values(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        made = world.receive()
        world.triage(made.stream_id)
        with pytest.raises(NoChangesError):
            world.reclassify(made.stream_id, "general", "letter")
        with pytest.raises(ValidationError):
            world.reclassify(made.stream_id, "general", "memo", reason="  ")
        with pytest.raises(UnknownDomainError):
            world.reclassify(made.stream_id, "legal", "letter")
        closed = world.forge_item("P123-COR-0099", state="Triaged")
        world.close(closed)
        with pytest.raises(ItemStateError):
            world.reclassify(closed, "general", "memo")


def test_a_retired_clause_cannot_be_cited_by_a_clock(
    world: CorrWorld, clause_domains: None
) -> None:
    with frozen_today(MONDAY):
        world.retire_clause(world.forge_clause())
        made = world.receive("Submittal one")
        with pytest.raises(InvalidClockError, match="CT-1/20.1"):
            world.triage(made.stream_id, domain="document_control", subtype="submittal")
    assert world.item(made.key or "").state == "Received"


def test_reclassify_refuses_an_item_that_was_issued_or_answered(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        issued = world.forge_item("P123-COR-0097", state="Issued", direction="out")
        answered = world.forge_item("P123-COR-0098", state="Responded")
        for item in (issued, answered):
            with pytest.raises(ItemStateError):
                world.reclassify(item, "general", "memo")
