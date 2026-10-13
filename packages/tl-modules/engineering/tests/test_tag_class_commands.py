"""Tag class commands against a real ledger on every adapter (P1-I1-T07)."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import as_json
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError, UnknownPsetError, UnsupportedFieldError
from tl_mod_engineering import registry
from tl_mod_engineering.errors import (
    AlreadyClosedError,
    DuplicateTagClassError,
    InvalidTagClassError,
    RegistryScopeError,
    TagClassNotFoundError,
)
from tl_mod_engineering.handlers.tag_class import (
    CloseTagClass,
    DefineTagClass,
    ReviseTagClass,
    handle_close_tag_class,
    handle_define_tag_class,
    handle_revise_tag_class,
)
from tl_mod_engineering.names import TAG_CLASS, TAG_CLASS_TABLE

pytestmark = pytest.mark.usefixtures("fixture_schemas")

BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "company"}


def define(db: DbTarget, code: str = "ControlValve", **more: Any) -> CommandResult:
    fields: dict[str, Any] = {
        "code": code,
        "label": f"{code} label",
        "definition": f"What a {code} is.",
        "family": "valve",
        "required_psets": ["valve_data"],
        "itr_templates": ["ITR-VALVE-01"],
        "mnemonics": ["FV"],
        "edition": "co.acme.standards@1.0.0",
    }
    fields.update(more)
    with open_uow(db) as uow:
        return handle_define_tag_class(uow, DefineTagClass(**{**BASE, **fields}))


def revise(db: DbTarget, made: CommandResult, changes: dict[str, Any], **more: Any) -> Any:
    fields: dict[str, Any] = {"stream_id": made.stream_id, "changes": changes, "reason": "test"}
    fields.update(more)
    with open_uow(db) as uow:
        return handle_revise_tag_class(uow, ReviseTagClass(**{**BASE, **fields}))


def close(db: DbTarget, made: CommandResult, **more: Any) -> Any:
    fields: dict[str, Any] = {"stream_id": made.stream_id, "reason": "test"}
    fields.update(more)
    with open_uow(db) as uow:
        return handle_close_tag_class(uow, CloseTagClass(**{**BASE, **fields}))


def row(db: DbTarget, code: str = "ControlValve") -> registry.TagClassRow:
    with open_uow(db, readonly=True) as uow:
        found = registry.find_tag_classes(uow.conn(), "company", code=code)
    assert len(found) == 1
    return found[0]


def count(db: DbTarget, table: str = "cur_core_record") -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


# --- define --------------------------------------------------------------------------------------


def test_define_writes_the_envelope_and_the_typed_row(db: DbTarget) -> None:
    made = define(db)
    assert made.key == "TC:ControlValve" and made.version == 2
    assert [e.event_type for e in made.events] == ["Record.Created", "TagClass.Defined"]
    assert made.events[1].payload == {
        "code": "ControlValve",
        "label": "ControlValve label",
        "family": "valve",
        "required_psets": ["valve_data"],
        "itr_templates": ["ITR-VALVE-01"],
        "mnemonics": ["FV"],
        "edition": "co.acme.standards@1.0.0",
    }
    found = row(db)
    assert (found.id, found.scope, found.family) == (made.stream_id, "company", "valve")
    assert found.required_psets == ["valve_data"] and found.mnemonics == ["FV"]
    assert found.itr_templates == ["ITR-VALVE-01"]
    assert (found.lifecycle, found.key, found.version) == ("active", "TC:ControlValve", 2)
    assert (found.label, found.description) == ("ControlValve label", "What a ControlValve is.")
    with open_uow(db, readonly=True) as uow:
        record_type = (
            uow.conn()
            .execute(
                text("SELECT type FROM cur_core_record WHERE id = :id"), {"id": made.stream_id}
            )
            .scalar_one()
        )
    assert record_type == TAG_CLASS


def test_define_needs_no_psets_lists_or_definition(db: DbTarget) -> None:
    made = define(
        db,
        "Pump",
        family="pump",
        required_psets=[],
        itr_templates=[],
        mnemonics=[],
        definition=None,
    )
    found = row(db, "Pump")
    assert found.id == made.stream_id and found.required_psets == []
    assert found.description is None


def test_define_outside_company_scope_is_refused(db: DbTarget) -> None:
    with pytest.raises(RegistryScopeError, match="company records"):
        with open_uow(db) as uow:
            handle_define_tag_class(
                uow,
                DefineTagClass(
                    **{**BASE, "scope": "project:P123"},
                    code="X",
                    label="x",
                    family="valve",
                    edition="e@1.0.0",
                ),
            )
    assert count(db) == 0


def test_define_with_a_pset_the_company_schema_lacks_is_refused_and_writes_nothing(
    db: DbTarget,
) -> None:
    with pytest.raises(UnknownPsetError, match="no_such_pset"):
        define(db, required_psets=["valve_data", "no_such_pset"])
    assert count(db) == 0 and count(db, TAG_CLASS_TABLE) == 0


def test_define_a_second_time_is_refused_even_after_the_first_was_closed(db: DbTarget) -> None:
    first = define(db)
    with pytest.raises(DuplicateTagClassError, match="already defined"):
        define(db)
    close(db, first)
    with pytest.raises(DuplicateTagClassError, match="lifecycle retired"):
        define(db)
    assert count(db, TAG_CLASS_TABLE) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"code": "Control Valve"},
        {"code": ""},
        {"family": "boat"},
        {"label": ""},
        {"edition": ""},
    ],
)
def test_define_refuses_a_malformed_command(bad: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"code": "X", "label": "x", "family": "valve", "edition": "e@1.0.0"}
    fields.update(bad)
    with pytest.raises(ValidationError):
        DefineTagClass(**BASE, **fields)


# --- revise --------------------------------------------------------------------------------------


def test_revise_records_each_change_as_old_and_new_and_updates_the_row(db: DbTarget) -> None:
    made = define(db)
    changed = revise(
        db,
        made,
        {
            "label": "Control valve",
            "required_psets": ["valve_data", "safety_data"],
            "mnemonics": ["FV", "PV"],
            "family": "valve",  # unchanged: left out of the event
        },
        reason="SIS valves need safety data",
    )
    (event,) = changed.events
    assert event.event_type == "TagClass.Revised"
    assert event.payload == {
        "changes": {
            "label": ["ControlValve label", "Control valve"],
            "required_psets": [["valve_data"], ["valve_data", "safety_data"]],
            "mnemonics": [["FV"], ["FV", "PV"]],
        },
        "reason": "SIS valves need safety data",
    }
    assert changed.version == 3
    found = row(db)
    assert (found.label, found.version) == ("Control valve", 3)
    assert found.required_psets == ["valve_data", "safety_data"]
    assert found.mnemonics == ["FV", "PV"] and found.itr_templates == ["ITR-VALVE-01"]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"code": "Other"}, UnsupportedFieldError),
        ({"label": "ControlValve label"}, NoChangesError),
        ({}, NoChangesError),
        ({"label": "  "}, InvalidTagClassError),
        ({"family": "boat"}, InvalidTagClassError),
        ({"mnemonics": "FV"}, InvalidTagClassError),
        ({"mnemonics": [1]}, InvalidTagClassError),
        ({"required_psets": ["nope"]}, UnknownPsetError),
    ],
)
def test_revise_refuses_what_it_cannot_apply_and_writes_nothing(
    db: DbTarget, changes: dict[str, Any], error: type[Exception]
) -> None:
    made = define(db)
    with pytest.raises(error):
        revise(db, made, changes)
    assert row(db).version == 2


def test_revise_needs_a_reason() -> None:
    with pytest.raises(ValidationError):
        ReviseTagClass(**BASE, stream_id="x", changes={"label": "a"}, reason=" ")


def test_revise_an_unknown_or_foreign_class_is_not_found(db: DbTarget) -> None:
    made = define(db)
    with pytest.raises(TagClassNotFoundError):
        revise(db, CommandResult(stream_id="nope", key=None, version=1, events=[]), {"label": "x"})
    with pytest.raises(TagClassNotFoundError):
        with open_uow(db) as uow:
            handle_revise_tag_class(
                uow,
                ReviseTagClass(
                    **{**BASE, "scope": "project:P123"},
                    stream_id=made.stream_id,
                    changes={"label": "x"},
                    reason="r",
                ),
            )


def test_revise_a_closed_class_is_refused(db: DbTarget) -> None:
    made = define(db)
    close(db, made)
    with pytest.raises(AlreadyClosedError, match="retired"):
        revise(db, made, {"label": "x"})


def test_revise_checks_the_expected_version_when_given(db: DbTarget) -> None:
    made = define(db)
    with pytest.raises(ConcurrencyError):
        revise(db, made, {"label": "x"}, expected_version=1)
    revise(db, made, {"label": "x"}, expected_version=2)
    assert row(db).label == "x"


# --- close ---------------------------------------------------------------------------------------


def test_close_retires_a_class_and_keeps_its_row(db: DbTarget) -> None:
    made = define(db)
    closed = close(db, made, reason="Merged into another class")
    (event,) = closed.events
    assert event.event_type == "TagClass.Closed"
    assert event.payload == {
        "lifecycle": "retired",
        "superseded_by": None,
        "reason": "Merged into another class",
    }
    found = row(db)
    assert (found.lifecycle, found.version) == ("retired", 3)
    with open_uow(db, readonly=True) as uow:
        assert registry.active_tag_class(uow.conn(), "company", "ControlValve") is None


def test_close_as_superseded_names_the_replacing_class(db: DbTarget) -> None:
    old = define(db, "OldValve")
    new = define(db, "NewValve")
    close(db, old, lifecycle="superseded", superseded_by=new.stream_id)
    found = row(db, "OldValve")
    assert (found.lifecycle, found.superseded_by) == ("superseded", new.stream_id)


@pytest.mark.parametrize(
    "more",
    [
        {"lifecycle": "superseded"},
        {"lifecycle": "superseded", "superseded_by": "nope"},
        {"lifecycle": "retired", "superseded_by": "x"},
    ],
)
def test_close_refuses_an_inconsistent_replacement(db: DbTarget, more: dict[str, Any]) -> None:
    made = define(db)
    with pytest.raises(InvalidTagClassError):
        close(db, made, **more)
    assert row(db).lifecycle == "active"


def test_close_a_class_cannot_be_its_own_replacement(db: DbTarget) -> None:
    made = define(db)
    with pytest.raises(InvalidTagClassError):
        close(db, made, lifecycle="superseded", superseded_by=made.stream_id)


def test_close_twice_is_refused(db: DbTarget) -> None:
    made = define(db)
    close(db, made)
    with pytest.raises(AlreadyClosedError):
        close(db, made)


# --- the ledger is the truth ---------------------------------------------------------------------


def test_a_rebuild_of_the_projections_gives_the_same_rows(db: DbTarget) -> None:
    made = define(db)
    define(db, "Pump", family="pump", required_psets=[])
    revise(db, made, {"mnemonics": ["FV", "PV", "LV"]})
    close(db, define(db, "Retired"))
    before = [row(db, code) for code in ("ControlValve", "Pump", "Retired")]
    rebuild_projections(db)
    assert [row(db, code) for code in ("ControlValve", "Pump", "Retired")] == before
    with open_uow(db, readonly=True) as uow:
        stored: Any = (
            uow.conn()
            .execute(
                text(
                    "SELECT required_psets_json FROM cur_engineering_tag_class WHERE code = 'Pump'"
                )
            )
            .scalar_one()
        )
    assert as_json(stored) == []
