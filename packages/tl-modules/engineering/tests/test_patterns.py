"""Registry numbering patterns: parsing and checking a number, and the allocator wiring (T05)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from engworld import COMPANY, PROJECT, Events, put_standard, put_value
from sqlalchemy import Engine
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import NewEvent
from tl_core.numbering.config import numbering_for
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_mod_engineering import patterns
from tl_mod_engineering.names import TAG

DAY = date(2026, 6, 1)
TAG_DATA: dict[str, Any] = {
    "record_type": "engineering.Tag",
    "template": "{area}-{mnemonic}-{seq:4}",
    "segments": {
        "area": {"role": "area", "list": "Area", "registry": None},
        "mnemonic": {"role": "mnemonic", "list": None, "registry": "mnemonic"},
        "seq": {"role": "sequence", "list": None, "registry": None},
    },
    "allocate": False,
    "gap_free": True,
    "scope": "project:*",
    "reserved": [],
}


@pytest.fixture
def world(engine: Engine, events: Events) -> Engine:
    put_standard(events, engine, "code_list", "Area", policy="extensible")
    for code in ("10", "47"):
        put_value(events, engine, "Area", code)
    for code in ("FV", "PT"):
        put_standard(events, engine, "mnemonic", code)
    put_standard(events, engine, "numbering_pattern", "tag", data=TAG_DATA)
    return engine


def parse(engine: Engine, number: str, scope: str = PROJECT) -> patterns.ParsedNumber:
    with engine.connect() as conn:
        found = patterns.pattern_for(conn, "engineering.Tag")
        assert found is not None
        return patterns.parse_number(conn, scope, found, number, on=DAY)


def test_the_registry_pattern_is_found_by_the_record_type_it_numbers(world: Engine) -> None:
    with world.connect() as conn:
        found = patterns.pattern_for(conn, "engineering.Tag")
        assert patterns.pattern_for(conn, "engineering.Other") is None
        assert [p.code for p in patterns.patterns(conn)] == ["tag"]
    assert found is not None and found.template == "{area}-{mnemonic}-{seq:4}"
    assert (
        found.segments["area"].list == "Area" and found.segments["mnemonic"].registry == "mnemonic"
    )
    assert (found.allocate, found.gap_free, found.scope) == (False, True, "project:*")


def test_a_good_number_is_read_into_its_segments(world: Engine) -> None:
    parsed = parse(world, "47-FV-1001")
    assert parsed.ok and parsed.issues == []
    assert parsed.pattern_code == "tag"
    assert parsed.segments == {"area": "47", "mnemonic": "FV", "seq": "1001"}
    assert (parsed.area, parsed.mnemonic, parsed.sequence) == ("47", "FV", 1001)


def test_a_near_miss_lists_every_problem_at_once(world: Engine) -> None:
    parsed = parse(world, "47-XX-1")
    assert not parsed.ok
    assert [(i.segment, i.rule) for i in parsed.issues] == [
        ("seq", "sequence"),
        ("mnemonic", "unknown_mnemonic"),
    ]
    assert parsed.issues[0].message == "the sequence '1' must be written with 4 digits, like 0001"
    assert parsed.issues[1].message == "'XX' is not a registered mnemonic"
    assert (parsed.area, parsed.mnemonic, parsed.sequence) == ("47", "XX", 1)
    assert parsed.issues[1].as_dict() == {
        "segment": "mnemonic",
        "rule": "unknown_mnemonic",
        "level": "error",
        "message": "'XX' is not a registered mnemonic",
    }


@pytest.mark.parametrize(
    ("number", "rules"),
    [
        ("99-FV-1001", [("area", "unknown_code")]),
        ("47-fv-1001", [("mnemonic", "unknown_mnemonic")]),
        ("47-FV-01001", [("seq", "sequence")]),
        ("47-FV-0000", [("seq", "sequence")]),
        ("47-FV-ABCD", [("seq", "sequence")]),
        (
            "99-ZZ-12",
            [("seq", "sequence"), ("area", "unknown_code"), ("mnemonic", "unknown_mnemonic")],
        ),
    ],
)
def test_each_kind_of_problem_has_its_rule(
    world: Engine, number: str, rules: list[tuple[str, str]]
) -> None:
    assert [(i.segment, i.rule) for i in parse(world, number).issues] == rules


@pytest.mark.parametrize("number", ["hello", "47-FV", "47_FV_1001", "47-FV-1001-A", ""])
def test_a_number_without_the_shape_has_one_issue_and_no_segments(
    world: Engine, number: str
) -> None:
    parsed = parse(world, number)
    assert [(i.segment, i.rule) for i in parsed.issues] == [(None, "pattern")]
    assert (
        parsed.issues[0].message
        == f"{number!r} does not fit the pattern {{area}}-{{mnemonic}}-{{seq:4}}"
    )
    assert parsed.segments == {} and parsed.sequence is None


def test_a_project_value_of_a_list_is_a_good_area_for_that_project_only(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Area", "47A", scope=PROJECT, crosswalk="47")
    assert parse(world, "47A-FV-1001").ok
    assert [i.rule for i in parse(world, "47A-FV-1001", "project:P999").issues] == ["unknown_code"]


def test_a_value_out_of_its_dates_is_inactive(world: Engine, events: Events) -> None:
    put_value(events, world, "Area", "20", effective_to="2026-01-31")
    assert [(i.segment, i.rule) for i in parse(world, "20-FV-1001").issues] == [
        ("area", "inactive_code")
    ]


def test_a_missing_list_is_reported_not_raised(engine: Engine, events: Events) -> None:
    put_standard(events, engine, "mnemonic", "FV")
    put_standard(events, engine, "numbering_pattern", "tag", data=TAG_DATA)
    assert [(i.segment, i.rule) for i in parse(engine, "47-FV-1001").issues] == [
        ("area", "unknown_list")
    ]


# --- feeding the allocator ------------------------------------------------------------------


def test_only_patterns_that_allocate_reach_the_numbering_service(
    world: Engine, events: Events
) -> None:
    with world.connect() as conn:
        assert patterns.ledger_numbering_patterns(conn) == []
    put_standard(
        events,
        world,
        "numbering_pattern",
        "doc",
        data={
            **TAG_DATA,
            "record_type": "engineering.Doc",
            "template": "{project}-{type}-{seq:3}",
            "segments": {"seq": {"role": "sequence", "list": None, "registry": None}},
            "allocate": True,
            "gap_free": False,
            "scope": "project:P123",
            "reserved": [[1, 9]],
        },
    )
    with world.connect() as conn:
        (found,) = patterns.ledger_numbering_patterns(conn)
    assert (found.id, found.record_type, found.type_code) == (
        "registry:doc",
        "engineering.Doc",
        "DOC",
    )
    assert (found.scope, found.gap_free, found.reserved) == ("project:P123", False, [(1, 9)])
    assert found.template == "{project}-{type}-{seq:3}"


def test_the_allocator_numbers_a_module_record_from_a_registry_pattern(db: DbTarget) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id="S-tag",
            stream_type="engineering.NumberingPattern",
            scope=COMPANY,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={
                        "record_type": "engineering.NumberingPattern",
                        "key": "NP:tag@1.0.0",
                        "title": "tag",
                        "psets": {},
                    },
                ),
                NewEvent(
                    event_type="Standard.Defined",
                    payload={
                        "kind": "numbering_pattern",
                        "code": "tag",
                        "label": "tag",
                        "edition": "co.acme.standards@1.0.0",
                        "data": {**TAG_DATA, "allocate": True},
                    },
                ),
            ],
            actor="user:u",
            source="test",
            correlation_id="c",
        )
    command = Command(actor="user:u", source="test", scope=PROJECT)

    def make(area: str, mnemonic: str) -> str:
        created = create_module_record(
            uow,
            command,
            record_type=TAG,
            title="t",
            key=None,
            numbering={"area": area, "mnemonic": mnemonic},
        )
        assert created.key is not None
        return created.key

    with open_uow(db) as uow:
        assert "registry:tag" in [p.id for p in numbering_for(uow.conn()).all()]
        keys = [make("47", "FV"), make("47", "FV"), make("10", "PT")]
    assert keys == ["47-FV-0001", "47-FV-0002", "10-PT-0001"]
