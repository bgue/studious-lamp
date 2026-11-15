"""The permit type table (P2-PTW S1): six entries, the design's flags, and what load refuses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from tl_mod_permits.names import PERMIT_TYPES
from tl_mod_permits.types_table import (
    TYPES_FILE,
    TypeRule,
    TypesTableError,
    load_types,
    parse_types,
)


def _raw() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(Path(TYPES_FILE).read_text(encoding="utf-8"))
    return loaded


def test_one_entry_per_enum_value() -> None:
    table = load_types()
    assert list(table) == list(PERMIT_TYPES)
    assert len(table) == 6
    assert all(isinstance(rule, TypeRule) for rule in table.values())


def test_the_flags_equal_the_design_table() -> None:
    table = load_types()
    gas = {t for t, r in table.items() if r.needs_gas_test}
    isolation = {t for t, r in table.items() if r.needs_isolation}
    one_day = {t for t, r in table.items() if r.max_days == 1}
    assert gas == {"hot_work", "confined_space"}
    assert isolation == {"confined_space", "isolation"}
    assert one_day == {"hot_work", "confined_space"}
    assert {r.max_days for r in table.values()} == {1, 7}


def test_precautions_are_the_design_lists() -> None:
    table = load_types()
    assert [len(table[t].precautions) for t in PERMIT_TYPES] == [4, 4, 4, 4, 3, 1]
    for rule in table.values():
        assert all(0 < len(p.text) <= 120 for p in rule.precautions)


def test_a_rule_is_frozen() -> None:
    rule = load_types()["hot_work"]
    with pytest.raises(ValidationError):
        rule.needs_gas_test = False  # type: ignore[misc]


def test_the_table_is_read_once() -> None:
    assert load_types()["general"] is load_types()["general"]


def test_a_missing_type_is_refused() -> None:
    raw = _raw()
    del raw["types"]["excavation"]
    with pytest.raises(TypesTableError, match="excavation"):
        parse_types(raw)


def test_an_unknown_type_key_is_refused() -> None:
    raw = _raw()
    raw["types"]["welding"] = raw["types"]["general"]
    with pytest.raises(TypesTableError, match="welding"):
        parse_types(raw)


def test_an_unknown_field_is_refused() -> None:
    raw = _raw()
    raw["types"]["general"]["needs_permit"] = True
    with pytest.raises(TypesTableError):
        parse_types(raw)


def test_a_duplicate_precaution_id_is_refused() -> None:
    raw = _raw()
    first = raw["types"]["hot_work"]["precautions"][0]
    raw["types"]["hot_work"]["precautions"].append({"id": first["id"], "text": "Again"})
    with pytest.raises(TypesTableError, match="duplicate"):
        parse_types(raw)


def test_a_long_precaution_text_and_a_bad_max_days_are_refused() -> None:
    raw = _raw()
    raw["types"]["general"]["precautions"][0]["text"] = "x" * 121
    with pytest.raises(TypesTableError):
        parse_types(raw)
    raw = _raw()
    raw["types"]["general"]["max_days"] = 3
    with pytest.raises(TypesTableError):
        parse_types(raw)
