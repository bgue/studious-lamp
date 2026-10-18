"""Cases the provided tests of the first wave leave open (found by the mutation run, P1-I5).

Each test names the rule it pins. They run against the merged code of T07a, T07c and T07f.
"""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core.ledger.types import ConcurrencyError
from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence import domains as dm
from tl_mod_correspondence.errors import (
    ClauseNotFoundError,
    InvalidClauseError,
    InvalidItemError,
    LetterRenderError,
)
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import BASE, PROJECT, CorrWorld, frozen_today
from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document

MONDAY = "2026-10-19"


def stored(world: CorrWorld, file_id: str) -> bytes:
    assert world.files is not None
    with open_uow(world.db, readonly=True) as uow:
        opened = world.files.open_file(uow, PROJECT, file_id, actor="user:u")
        try:
            return opened.data.read()
        finally:
            opened.data.close()


def test_updating_the_recipients_checks_the_parties_like_receiving_does(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Programme")
        with pytest.raises(InvalidItemError, match="not a party"):
            world.update(made.stream_id, to=[Recipient(party_id="01J000000000000000000000")])
        with pytest.raises(InvalidItemError, match="not a party"):
            world.update(made.stream_id, cc=[Recipient(party_id="01J000000000000000000000")])
        party = world.party()
        world.update(made.stream_id, to=[Recipient(party_id=party.stream_id)])
    assert world.item(made.key or "").to[0]["party_id"] == party.stream_id


def test_issuing_with_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        with pytest.raises(ConcurrencyError):
            world.issue(draft.stream_id, expected_version=1)
        assert world.item(draft.key or "").state == "Draft"
        world.issue(draft.stream_id, expected_version=world.item(draft.key or "").version)


def test_the_letter_carries_the_issue_day_not_the_day_an_earlier_text_was_received(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        world.update(draft.stream_id, received_on="2026-09-01")
        world.issue(draft.stream_id, issued_on="2026-10-12", date_reason="posted earlier")
    item = world.item(draft.key or "")
    data = stored(world, item.rendition_file_id or "")
    assert b"2026-10-12" in data or b"12 October 2026" in data
    assert b"2026-10-19" not in data and b"19 October 2026" not in data


def test_a_letter_too_long_to_print_is_a_render_error_and_the_draft_stays(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter", body="line\n" * 3000)
        with pytest.raises(LetterRenderError, match="pages"):
            world.issue(draft.stream_id)
    assert world.item(draft.key or "").state == "Draft"


def _two_templates() -> dm.DomainSet:
    base = catalog.domain_set()
    changed: list[dm.DomainDefinition] = []
    for definition in base.all():
        if definition.code == "general":
            first = next(t for t in definition.templates if t.subtype == "letter")
            second = first.model_copy(update={"code": "general-letter-b", "header": "SECOND"})
            definition = definition.model_copy(
                update={"templates": (first, second, *definition.templates[1:])}
            )
        changed.append(definition)
    return dm.DomainSet(changed)


def test_with_two_templates_for_a_subtype_the_first_is_used(world: CorrWorld) -> None:
    with frozen_today(MONDAY), catalog.use_domains(_two_templates()):
        draft = world.draft(domain="general", subtype="letter")
        world.issue(draft.stream_id)
        chosen = world.draft(domain="general", subtype="letter")
        world.issue(chosen.stream_id, template="general-letter-b")
    issued = [p for n, p in world.events_of(draft.stream_id) if n == "Correspondence.Issued"]
    assert issued[0]["template"] == "general-letter"
    other = [p for n, p in world.events_of(chosen.stream_id) if n == "Correspondence.Issued"]
    assert other[0]["template"] == "general-letter-b"


def test_a_contact_added_after_one_ended_takes_a_new_position(world: CorrWorld) -> None:
    party = world.party(contacts=[{"name": "Ann", "email": "ann@meridian.example"}])
    world.end_contact(party.stream_id, 1)
    world.add_contact(party.stream_id, name="Bob", email="bob@meridian.example")
    world.add_contact(party.stream_id, name="Cy", email="cy@meridian.example")
    with open_uow(world.db, readonly=True) as uow:
        everyone = registry.contacts_of(uow.conn(), party.stream_id, include_ended=True)
    assert [(c.position, c.name) for c in everyone] == [(1, "Ann"), (2, "Bob"), (3, "Cy")]


def test_a_clause_of_another_project_is_not_found_to_retire(world: CorrWorld) -> None:
    foreign = world.clause("CT-9", "1", scope="project:P999")
    with pytest.raises(ClauseNotFoundError):
        world.retire_clause(foreign.stream_id)  # this world's scope is P123
    with open_uow(world.db, readonly=True) as uow:
        row = registry.get_clause(uow.conn(), foreign.stream_id)
    assert row is not None and row.is_active


def test_a_contract_document_of_another_project_is_refused(world: CorrWorld) -> None:
    with open_uow(world.db) as uow:
        document = handle_register_document(
            uow,
            RegisterDocument(
                **{**BASE, "scope": "project:P999"},
                number="CON-0001",
                title="Contract",
                doc_type="ISO",
                discipline="PIP",
            ),
        )
    with pytest.raises(InvalidClauseError, match="not a document"):
        world.clause("CT-1", "30", contract_document_id=document.stream_id)
    assert PROJECT == "project:P123"
