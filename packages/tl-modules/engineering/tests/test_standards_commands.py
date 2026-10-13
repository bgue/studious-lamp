"""Registry commands against a real ledger on every adapter (P1-I1-T03)."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import as_json
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError
from tl_core.services.commands import CommandResult
from tl_mod_engineering import registry
from tl_mod_engineering.errors import (
    AlreadyClosedError,
    CrosswalkRequiredError,
    DuplicateCodeValueError,
    DuplicateStandardError,
    InvalidCrosswalkError,
    InvalidPatternError,
    InvalidSupersessionError,
    ListClosedError,
    RegistryScopeError,
    StandardNotFoundError,
    UnknownCodeListError,
)
from tl_mod_engineering.handlers.standards import (
    AddCodeValue,
    CloseCodeValue,
    CloseStandard,
    RegisterCodeList,
    RegisterMnemonic,
    RegisterNumberingPattern,
    handle_add_code_value,
    handle_close_code_value,
    handle_close_standard,
    handle_register_code_list,
    handle_register_mnemonic,
    handle_register_numbering_pattern,
)

COMPANY: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "company"}
PROJECT: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}
EDITION = "co.acme.standards@1.0.0"
TAG_SEGMENTS: dict[str, Any] = {
    "area": {"role": "area", "list": "Area"},
    "mnemonic": {"role": "mnemonic", "registry": "mnemonic"},
    "seq": {"role": "sequence"},
}


def code_list(db: DbTarget, name: str = "Material", policy: str = "extensible", **more: Any) -> Any:
    fields: dict[str, Any] = {
        "code": name,
        "label": f"{name} list",
        "definition": "A list.",
        "edition": EDITION,
        "value_list_policy": policy,
    }
    fields.update(more)
    with open_uow(db) as uow:
        return handle_register_code_list(uow, RegisterCodeList(**{**COMPANY, **fields}))


def value(db: DbTarget, name: str, code: str, base: dict[str, Any] = COMPANY, **more: Any) -> Any:
    fields: dict[str, Any] = {"code_list": name, "code": code, "label": f"{code} label"}
    fields.update(more)
    with open_uow(db) as uow:
        return handle_add_code_value(uow, AddCodeValue(**{**base, **fields}))


def standard(db: DbTarget, kind: str, code: str) -> registry.StandardRow:
    with open_uow(db, readonly=True) as uow:
        (row,) = registry.find_standards(uow.conn(), scope="company", kind=kind, code=code)
    return row


def code_value(db: DbTarget, scope: str, name: str, code: str) -> registry.CodeValueRow:
    with open_uow(db, readonly=True) as uow:
        row = registry.find_code_value(uow.conn(), scope, name, code)
    assert row is not None
    return row


def count(db: DbTarget, table: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


# --- code lists, mnemonics, patterns -------------------------------------------------------------


def test_a_code_list_is_an_envelope_plus_a_standard_row(db: DbTarget) -> None:
    made = code_list(db, "Discipline", "closed", owner="role:steward", adoption="mandatory")
    assert made.key == "CL:Discipline@1.0.0" and made.version == 2
    assert [e.event_type for e in made.events] == ["Record.Created", "Standard.Defined"]
    row = standard(db, "code_list", "Discipline")
    assert (row.id, row.scope, row.record_type) == (
        made.stream_id,
        "company",
        "engineering.CodeList",
    )
    assert (row.label, row.definition, row.edition) == ("Discipline list", "A list.", EDITION)
    assert (row.owner, row.adoption, row.value_list_policy) == (
        "role:steward",
        "mandatory",
        "closed",
    )
    assert (row.lifecycle, row.key, row.version, row.data) == ("active", made.key, 2, {})


def test_a_mnemonic_keeps_its_hints_in_data(db: DbTarget) -> None:
    with open_uow(db) as uow:
        made = handle_register_mnemonic(
            uow,
            RegisterMnemonic(
                **COMPANY,
                code="FV",
                label="Flow control valve",
                edition=EDITION,
                class_hint="ControlValve",
            ),
        )
    assert made.key == "MN:FV@1.0.0"
    row = standard(db, "mnemonic", "FV")
    assert row.data == {"class_hint": "ControlValve", "discipline": None}
    assert row.record_type == "engineering.Mnemonic" and row.value_list_policy is None


def pattern(db: DbTarget, **more: Any) -> Any:
    fields: dict[str, Any] = {
        "code": "tag",
        "label": "Tag number",
        "definition": "Area, mnemonic, sequence.",
        "edition": EDITION,
        "record_type": "engineering.Tag",
        "template": "{area}-{mnemonic}-{seq:4}",
        "segments": TAG_SEGMENTS,
    }
    fields.update(more)
    with open_uow(db) as uow:
        return handle_register_numbering_pattern(
            uow, RegisterNumberingPattern(**{**COMPANY, **fields})
        )


def test_a_numbering_pattern_keeps_its_template_and_segments_in_data(db: DbTarget) -> None:
    code_list(db, "Area")
    made = pattern(db)
    assert made.key == "NP:tag@1.0.0"
    row = standard(db, "numbering_pattern", "tag")
    assert row.data == {
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


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"template": "{area}-{mnemonic}"}, "exactly one"),
        ({"segments": {"area": TAG_SEGMENTS["area"], "seq": TAG_SEGMENTS["seq"]}}, "no definition"),
        (
            {"segments": {**TAG_SEGMENTS, "area": {"role": "area", "list": "Nowhere"}}},
            "names the code list 'Nowhere'",
        ),
    ],
)
def test_a_pattern_that_cannot_work_is_refused_and_writes_nothing(
    db: DbTarget, change: dict[str, Any], fragment: str
) -> None:
    code_list(db, "Area")
    before = count(db, "cur_core_record")
    with pytest.raises(InvalidPatternError, match=fragment):
        pattern(db, **change)
    assert count(db, "cur_core_record") == before


def test_one_active_pattern_numbers_a_record_type(db: DbTarget) -> None:
    code_list(db, "Area")
    first = pattern(db)
    with pytest.raises(InvalidPatternError, match="already numbered by the active pattern 'tag'"):
        pattern(db, code="tag2")
    with open_uow(db) as uow:
        handle_close_standard(uow, CloseStandard(**COMPANY, stream_id=first.stream_id, reason="r"))
    assert pattern(db, code="tag2").key == "NP:tag2@1.0.0"


def test_an_entry_is_registered_once_per_edition(db: DbTarget) -> None:
    code_list(db, "Material")
    with pytest.raises(
        DuplicateStandardError, match="already registered in co.acme.standards@1.0.0"
    ):
        code_list(db, "Material")
    second = code_list(db, "Material", edition="co.acme.standards@2.0.0")
    assert second.key == "CL:Material@2.0.0"


def test_registry_entries_are_company_records(db: DbTarget) -> None:
    with pytest.raises(RegistryScopeError, match="company records"):
        with open_uow(db) as uow:
            handle_register_code_list(
                uow,
                RegisterCodeList(**PROJECT, code="X", label="x", edition=EDITION),
            )
    assert count(db, "cur_core_record") == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"code": "area"},
        {"edition": "1.0.0"},
        {"edition": "co.acme.standards@1.0"},
        {"effective_from": "2026/01/01"},
        {"label": ""},
        {"value_list_policy": "open"},
    ],
)
def test_a_malformed_code_list_command_is_refused(bad: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"code": "Area", "label": "x", "edition": EDITION}
    fields.update(bad)
    with pytest.raises(ValidationError):
        RegisterCodeList(**COMPANY, **fields)


def test_a_mnemonic_must_be_upper_case() -> None:
    with pytest.raises(ValidationError):
        RegisterMnemonic(**COMPANY, code="fv", label="x", edition=EDITION)


# --- code values ---------------------------------------------------------------------------------


def test_a_company_value_takes_the_list_edition_and_counts_up_by_ten(db: DbTarget) -> None:
    code_list(db, "Material")
    first = value(db, "Material", "CS", attributes={"note": 1}, meaning="https://x/cs")
    second = value(db, "Material", "SS316L", sort_order=5)
    third = value(db, "Material", "other")
    assert first.key == "CV:Material.CS@1.0.0"
    assert [e.event_type for e in first.events] == ["Record.Created", "CodeValue.Defined"]
    row = code_value(db, "company", "Material", "CS")
    assert (row.origin, row.sort_order, row.edition, row.crosswalk) == (
        "company",
        10,
        EDITION,
        None,
    )
    assert (row.meaning, row.attributes, row.lifecycle) == ("https://x/cs", {"note": 1}, "active")
    assert code_value(db, "company", "Material", "SS316L").sort_order == 5
    assert code_value(db, "company", "Material", "other").sort_order == 20
    assert second.version == third.version == 2


def test_a_project_value_follows_the_policy_of_its_list(db: DbTarget) -> None:
    code_list(db, "Material", "extensible")
    code_list(db, "Discipline", "closed")
    code_list(db, "Craft", "project_defined")
    value(db, "Material", "SS316L")
    value(db, "Discipline", "PIP")
    value(db, "Craft", "WLD")
    made = value(db, "Material", "SS316L-NACE", PROJECT, crosswalk="SS316L")
    assert made.key == "CV:Material.SS316L-NACE"
    row = code_value(db, "project:P123", "Material", "SS316L-NACE")
    assert (row.origin, row.crosswalk, row.edition) == ("project", "SS316L", "project")
    value(db, "Craft", "RIG", PROJECT)
    with pytest.raises(CrosswalkRequiredError):
        value(db, "Material", "NEW", PROJECT)
    with pytest.raises(InvalidCrosswalkError):
        value(db, "Material", "NEW", PROJECT, crosswalk="NOPE")
    with pytest.raises(ListClosedError):
        value(db, "Discipline", "XYZ", PROJECT, crosswalk="PIP")
    with pytest.raises(DuplicateCodeValueError):
        value(db, "Craft", "WLD", PROJECT)
    with pytest.raises(UnknownCodeListError):
        value(db, "Nope", "X")
    assert count(db, "cur_engineering_code_value") == 5


def test_a_malformed_value_command_is_refused() -> None:
    with pytest.raises(ValidationError):
        AddCodeValue(**COMPANY, code_list="Area", code="a b", label="x")
    with pytest.raises(ValidationError):
        AddCodeValue(**COMPANY, code_list="Area", code="A", label="x", effective_to="soon")


# --- closing -------------------------------------------------------------------------------------


def close_standard(db: DbTarget, made: CommandResult, **more: Any) -> Any:
    fields: dict[str, Any] = {"stream_id": made.stream_id, "reason": "test"}
    fields.update(more)
    with open_uow(db) as uow:
        return handle_close_standard(uow, CloseStandard(**{**COMPANY, **fields}))


def test_closing_an_entry_retires_it_and_keeps_the_row(db: DbTarget) -> None:
    made = code_list(db, "Material")
    closed = close_standard(db, made, effective_to="2027-01-01", reason="Replaced by edition 2")
    (event,) = closed.events
    assert event.payload == {
        "lifecycle": "retired",
        "superseded_by": None,
        "effective_to": "2027-01-01",
        "reason": "Replaced by edition 2",
    }
    row = standard(db, "code_list", "Material")
    assert (row.lifecycle, row.effective_to, row.version) == ("retired", "2027-01-01", 3)
    with open_uow(db, readonly=True) as uow:
        assert registry.active_standard(uow.conn(), "company", "code_list", "Material") is None


def test_an_entry_can_be_superseded_by_the_next_edition_of_its_kind(db: DbTarget) -> None:
    old = code_list(db, "Material")
    new = code_list(db, "Material", edition="co.acme.standards@2.0.0")
    close_standard(db, old, lifecycle="superseded", superseded_by=new.stream_id)
    assert standard_by_id(db, old.stream_id).superseded_by == new.stream_id
    with open_uow(db, readonly=True) as uow:
        active = registry.active_standard(uow.conn(), "company", "code_list", "Material")
    assert active is not None and active.id == new.stream_id


def standard_by_id(db: DbTarget, stream_id: str) -> registry.StandardRow:
    with open_uow(db, readonly=True) as uow:
        row = registry.get_standard(uow.conn(), stream_id)
    assert row is not None
    return row


@pytest.mark.parametrize("more", [{"lifecycle": "superseded"}, {"superseded_by": "nope"}])
def test_an_inconsistent_replacement_is_refused(db: DbTarget, more: dict[str, Any]) -> None:
    made = code_list(db, "Material")
    with pytest.raises(InvalidSupersessionError):
        close_standard(db, made, **more)
    with pytest.raises(InvalidSupersessionError):
        close_standard(db, made, lifecycle="superseded", superseded_by=made.stream_id)
    assert standard(db, "code_list", "Material").lifecycle == "active"


def test_a_replacement_must_be_of_the_same_kind(db: DbTarget) -> None:
    made = code_list(db, "Material")
    with open_uow(db) as uow:
        mnemonic = handle_register_mnemonic(
            uow, RegisterMnemonic(**COMPANY, code="FV", label="x", edition=EDITION)
        )
    with pytest.raises(InvalidSupersessionError):
        close_standard(db, made, lifecycle="superseded", superseded_by=mnemonic.stream_id)


def test_closing_twice_or_an_unknown_entry_is_refused(db: DbTarget) -> None:
    made = code_list(db, "Material")
    close_standard(db, made)
    with pytest.raises(AlreadyClosedError, match="retired"):
        close_standard(db, made)
    ghost = CommandResult(stream_id="nope", key=None, version=1, events=[])
    with pytest.raises(StandardNotFoundError):
        close_standard(db, ghost)


def test_closing_checks_the_expected_version_when_given(db: DbTarget) -> None:
    made = code_list(db, "Material")
    with pytest.raises(ConcurrencyError):
        close_standard(db, made, expected_version=1)
    close_standard(db, made, expected_version=2)


def test_a_code_value_is_closed_like_an_entry(db: DbTarget) -> None:
    code_list(db, "Material")
    old = value(db, "Material", "CS")
    new = value(db, "Material", "CS2")
    other = value(db, "Material", "X")
    with open_uow(db) as uow:
        handle_close_code_value(
            uow,
            CloseCodeValue(
                **COMPANY,
                stream_id=old.stream_id,
                lifecycle="superseded",
                superseded_by=new.stream_id,
                reason="renamed",
            ),
        )
    row = code_value(db, "company", "Material", "CS")
    assert (row.lifecycle, row.superseded_by, row.version) == ("superseded", new.stream_id, 3)
    with open_uow(db) as uow, pytest.raises(AlreadyClosedError):
        handle_close_code_value(uow, CloseCodeValue(**COMPANY, stream_id=old.stream_id, reason="r"))
    with open_uow(db) as uow, pytest.raises(StandardNotFoundError):
        handle_close_code_value(uow, CloseCodeValue(**COMPANY, stream_id="nope", reason="r"))
    code_list(db, "Craft")
    foreign = value(db, "Craft", "WLD")
    with open_uow(db) as uow, pytest.raises(InvalidSupersessionError):
        handle_close_code_value(
            uow,
            CloseCodeValue(
                **COMPANY,
                stream_id=other.stream_id,
                lifecycle="superseded",
                superseded_by=foreign.stream_id,
                reason="r",
            ),
        )


# --- the ledger is the truth ---------------------------------------------------------------------


def test_a_rebuild_of_the_projections_gives_the_same_rows(db: DbTarget) -> None:
    code_list(db, "Area")
    code_list(db, "Material")
    value(db, "Material", "CS")
    value(db, "Material", "SS316L-NACE", PROJECT, crosswalk="CS")
    pattern(db)
    closing = code_list(db, "Old")
    close_standard(db, closing)

    def snapshot() -> list[Any]:
        with open_uow(db, readonly=True) as uow:
            conn = uow.conn()
            return [
                [tuple(r) for r in conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))]
                for table in ("cur_engineering_standard", "cur_engineering_code_value")
            ]

    before = snapshot()
    rebuild_projections(db)
    assert snapshot() == before
    with open_uow(db, readonly=True) as uow:
        stored: Any = (
            uow.conn()
            .execute(text("SELECT data_json FROM cur_engineering_standard WHERE code = 'tag'"))
            .scalar_one()
        )
    assert as_json(stored)["template"] == "{area}-{mnemonic}-{seq:4}"
