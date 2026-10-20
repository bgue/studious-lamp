"""Parties, contacts and contract clauses (P1-I5-T07f)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import DuplicateKeyError
from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import (
    ClauseNotFoundError,
    CorrespondenceScopeError,
    InvalidClauseError,
    InvalidPartyError,
    PartyNotFoundError,
)
from tl_mod_correspondence.testing import PROJECT, CorrWorld


def party_row(world: CorrWorld, code: str) -> registry.PartyRow:
    with open_uow(world.db, readonly=True) as uow:
        found = registry.find_party(uow.conn(), PROJECT, code)
    assert found is not None
    return found


def contacts(world: CorrWorld, party_id: str, ended: bool = False) -> list[registry.ContactRow]:
    with open_uow(world.db, readonly=True) as uow:
        return registry.contacts_of(uow.conn(), party_id, include_ended=ended)


def test_a_party_is_registered_under_its_code_with_its_first_contacts(world: CorrWorld) -> None:
    made = world.party(
        contacts=[
            {"name": "Pat Jones", "email": "Pat@Meridian.example", "is_authorised": True},
            {"name": "Sam Lee", "title": "Planner", "domain": "general"},
        ]
    )
    assert made.key == "MER"
    assert [e.event_type for e in made.events] == ["Record.Created", "Party.Defined"]
    party = party_row(world, "MER")
    assert (party.name, party.project_role, party.email_domains, party.is_active) == (
        "Meridian Energy",
        "client",
        ["meridian.example"],
        True,
    )
    assert [
        (c.position, c.name, c.email, c.title, c.domain, c.is_authorised)
        for c in contacts(world, made.stream_id)
    ] == [
        (1, "Pat Jones", "pat@meridian.example", None, None, True),
        (2, "Sam Lee", None, "Planner", "general", False),
    ]
    payload = world.events_of(made.stream_id)[1][1]
    assert payload["code"] == "MER" and payload["email_domains"] == ["meridian.example"]
    assert payload["contacts"][0]["email"] == "pat@meridian.example"


def test_a_party_code_is_unique_in_its_project_and_an_email_domain_has_one_owner(
    world: CorrWorld,
) -> None:
    world.party()
    with pytest.raises(DuplicateKeyError):
        world.party(email_domains=["other.example"])
    with pytest.raises(InvalidPartyError, match="meridian.example"):
        world.party("OTH", "Other", email_domains=["Meridian.Example"])
    assert world.party("MER", "Same code elsewhere", scope="project:P999").key == "MER"


def test_a_bad_party_is_refused_before_anything_is_written(world: CorrWorld) -> None:
    bad: list[dict[str, Any]] = [
        {"code": ""},
        {"code": "has space"},
        {"code": "x" * 65},
        {"name": " "},
        {"name": "two\nlines"},
        {"project_role": "king"},
        {"email_domains": ["no-dot"]},
        {"email_domains": ["a.example", "A.EXAMPLE"]},
        {"email_domains": [f"d{i}.example" for i in range(21)]},
        {"contacts": [{"name": "x", "email": "not an email"}]},
        {"contacts": [{"name": "x", "domain": "General Admin"}]},
        {"contacts": [{"name": "x"}] * 101},
        {"contacts": [{"name": "x", "unknown": 1}]},
        {"unknown": 1},
    ]
    for more in bad:
        with pytest.raises(ValidationError):
            world.party(**more)
    assert world.rows("SELECT id FROM cur_core_record WHERE type = 'correspondence.Party'") == []
    with pytest.raises(CorrespondenceScopeError):
        world.party(scope="company")


def test_a_contact_is_added_at_the_next_position_and_ended_with_its_history_kept(
    world: CorrWorld,
) -> None:
    party = world.party(contacts=[{"name": "First"}])
    added = world.add_contact(party.stream_id, name="Second", email="second@meridian.example")
    assert added.events[0].event_type == "Party.ContactAdded"
    assert world.events_of(party.stream_id)[-1][1]["position"] == 2
    world.add_contact(party.stream_id, name="Third", is_authorised=True)
    assert [c.name for c in contacts(world, party.stream_id)] == ["First", "Second", "Third"]
    world.end_contact(party.stream_id, 2, reason="left the company")
    assert [(c.position, c.name) for c in contacts(world, party.stream_id)] == [
        (1, "First"),
        (3, "Third"),
    ]
    assert [(c.position, c.is_active) for c in contacts(world, party.stream_id, True)] == [
        (1, True),
        (2, False),
        (3, True),
    ]
    world.add_contact(party.stream_id, name="Fourth")  # a position is never reused
    assert [c.position for c in contacts(world, party.stream_id, True)] == [1, 2, 3, 4]
    ended = [p for n, p in world.events_of(party.stream_id) if n == "Party.ContactEnded"]
    assert ended == [{"position": 2, "reason": "left the company"}]


def test_contact_commands_refuse_unknown_ended_and_foreign_things(world: CorrWorld) -> None:
    party = world.party()
    other = world.party("OTH", "Other", email_domains=[], scope="project:P999")
    with pytest.raises(PartyNotFoundError):
        world.add_contact("01J000000000000000000000")
    with pytest.raises(PartyNotFoundError):
        world.add_contact(other.stream_id)
    with pytest.raises(InvalidPartyError):
        world.end_contact(party.stream_id, 1)  # no contact at all
    world.add_contact(party.stream_id)
    world.end_contact(party.stream_id, 1)
    with pytest.raises(InvalidPartyError):
        world.end_contact(party.stream_id, 1)  # already ended
    with pytest.raises(ValidationError):
        world.end_contact(party.stream_id, 0)  # positions start at 1
    with pytest.raises(ValidationError):
        world.add_contact(party.stream_id, email="no")
    full = world.party("FUL", "Full", email_domains=[], contacts=[{"name": "x"}] * 100)
    with pytest.raises(InvalidPartyError, match="100"):
        world.add_contact(full.stream_id)


def test_a_retired_party_stays_in_the_register_and_takes_no_more_contacts(
    world: CorrWorld,
) -> None:
    party = world.party()
    done = world.retire_party(party.stream_id, "merged into another")
    assert done.events[0].event_type == "Party.Retired"
    assert party_row(world, "MER").is_active is False
    with open_uow(world.db, readonly=True) as uow:
        assert [p.code for p in registry.list_parties(uow.conn(), PROJECT)] == []
        assert [
            p.code for p in registry.list_parties(uow.conn(), PROJECT, include_inactive=True)
        ] == ["MER"]
    with pytest.raises(InvalidPartyError):
        world.add_contact(party.stream_id)
    with pytest.raises(InvalidPartyError):
        world.retire_party(party.stream_id)
    with pytest.raises(ValidationError):
        world.retire_party(party.stream_id, "  ")
    # its email domain is free again
    assert world.party("NEW", "New owner").key == "NEW"


def test_a_clause_is_registered_under_contract_and_number(world: CorrWorld) -> None:
    made = world.clause(
        "CT-1",
        "20.1",
        notice_requirements="State the event and the days claimed.\nSign it.",
        required_recipients=["engineer", "project_manager"],
        service_method="letter",
        domains=["general", "document_control"],
    )
    assert made.key == "CT-1/20.1"
    assert [e.event_type for e in made.events] == ["Record.Created", "ContractClause.Defined"]
    with open_uow(world.db, readonly=True) as uow:
        clause = registry.find_clause(uow.conn(), PROJECT, "CT-1", "20.1")
    assert clause is not None
    assert (clause.time_bar_days, clause.time_bar_day_type, clause.service_method) == (
        28,
        "calendar",
        "letter",
    )
    assert clause.required_recipients == ["engineer", "project_manager"]
    assert clause.domains == ["general", "document_control"]
    assert clause.notice_requirements == "State the event and the days claimed.\nSign it."
    assert clause.is_active is True


def test_a_clause_without_a_time_bar_is_allowed_and_a_half_bar_is_not(world: CorrWorld) -> None:
    plain = world.clause("CT-1", "1", time_bar_days=None, time_bar_day_type=None)
    assert plain.key == "CT-1/1"
    for more in ({"time_bar_days": None}, {"time_bar_day_type": None}):
        with pytest.raises(ValidationError):
            world.clause("CT-1", "2", **more)


def test_a_bad_clause_is_refused_before_anything_is_written(world: CorrWorld) -> None:
    bad: list[dict[str, Any]] = [
        {"contract": ""},
        {"contract": "has space"},
        {"number": "a/b"},
        {"time_bar_days": 0},
        {"time_bar_days": 3651},
        {"time_bar_day_type": "weekly"},
        {"service_method": "pigeon"},
        {"required_recipients": ["Engineer"]},
        {"required_recipients": ["engineer", "engineer"]},
        {"domains": ["General"]},
        {"notice_requirements": "x" * 20_001},
        {"notice_requirements": "bell\x07"},
        {"unknown": 1},
    ]
    for more in bad:
        fields = {"contract": "CT-1", "number": "9", **more}
        with pytest.raises(ValidationError):
            world.clause(fields.pop("contract"), fields.pop("number"), **fields)
    assert (
        world.rows("SELECT id FROM cur_core_record WHERE type = 'correspondence.ContractClause'")
        == []
    )


def test_a_clause_is_unique_and_its_contract_document_must_be_a_document_of_the_project(
    world: CorrWorld,
) -> None:
    world.clause()
    with pytest.raises(DuplicateKeyError):
        world.clause()
    with pytest.raises(InvalidClauseError, match="not a document"):
        world.clause("CT-1", "21", contract_document_id="01J000000000000000000000")
    with pytest.raises(CorrespondenceScopeError):
        world.clause("CT-1", "22", scope="company")


def test_a_retired_clause_stays_in_the_register_and_is_retired_once(world: CorrWorld) -> None:
    made = world.clause()
    done = world.retire_clause(made.stream_id, "replaced by the 2027 conditions")
    assert done.events[0].event_type == "ContractClause.Retired"
    with open_uow(world.db, readonly=True) as uow:
        assert registry.list_clauses(uow.conn(), PROJECT) == []
        [row] = registry.list_clauses(uow.conn(), PROJECT, include_inactive=True)
    assert row.is_active is False
    with pytest.raises(InvalidClauseError):
        world.retire_clause(made.stream_id)
    with pytest.raises(ClauseNotFoundError):
        world.retire_clause("01J000000000000000000000")
    with pytest.raises(ValidationError):
        world.retire_clause(made.stream_id, " ")
