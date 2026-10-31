"""The eleven platform settings of Phase 2 wave 0 (W0-B1): type, default, bounds, scopes, lock.

The expectations are written out here from the W0-B1 report, not read back from the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tl_core.services.errors import InvalidSettingValueError
from tl_core.settings.registry import load_definitions
from tl_core.settings.types import SettingDefinition
from tl_core.settings.values import check_definition, normalise

PLATFORM = Path(__file__).resolve().parents[2] / "schema" / "settings" / "platform.yaml"

#: key -> (type, default, minimum, maximum, choices, pattern, risk)
PHASE2: dict[str, tuple[str, Any, Any, Any, Any, Any, str]] = {
    "awp.iwp.ready_lead_weeks": ("int", 4, 0, 52, None, None, "normal"),
    "awp.backlog.target_weeks": ("int", 4, 0, 52, None, None, "normal"),
    "awp.iwp.size_hours": ("list", [60, 850], None, None, None, None, "normal"),
    "awp.release.signoff_roles": (
        "list",
        ["superuser"],
        None,
        None,
        ["user", "superuser"],
        None,
        "advanced",
    ),
    "awp.release.allow_unknown_checks": ("bool", False, None, None, None, None, "advanced"),
    "awp.rules_of_credit.set": (
        "string",
        "",
        None,
        None,
        None,
        "^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$|^$",
        "normal",
    ),
    "awp.constraint.aging_days": ("int", 14, 1, 365, None, None, "normal"),
    "awp.constraint.auto_raise": ("bool", True, None, None, None, None, "normal"),
    "awp.constraint.default_owners": (
        "list",
        [],
        None,
        None,
        None,
        "^user:[A-Za-z0-9._-]{1,64}$",
        "normal",
    ),
    "materials.receipt.mtr_required_categories": (
        "list",
        [],
        None,
        None,
        None,
        "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
        "normal",
    ),
    "scaffold.inspection.interval_days": ("int", 7, 1, 90, None, None, "normal"),
}
OLD_KEYS = 17


@pytest.fixture(scope="module")
def definitions() -> dict[str, SettingDefinition]:
    return {d.key: d for d in load_definitions(PLATFORM)}


def test_the_platform_file_defines_28_keys_17_old_and_11_new(
    definitions: dict[str, SettingDefinition],
) -> None:
    assert len(PHASE2) == 11
    assert len(definitions) == 28 == OLD_KEYS + len(PHASE2)
    assert set(PHASE2) <= set(definitions)
    assert len(set(definitions) - set(PHASE2)) == OLD_KEYS


@pytest.mark.parametrize("key", sorted(PHASE2))
def test_each_key_has_its_type_default_bounds_and_risk(
    definitions: dict[str, SettingDefinition], key: str
) -> None:
    kind, default, minimum, maximum, choices, pattern, risk = PHASE2[key]
    found = definitions[key]
    assert found.type == kind
    assert found.default == default
    assert found.risk == risk
    validation = found.validation
    assert (validation.minimum if validation else None) == minimum
    assert (validation.maximum if validation else None) == maximum
    assert (validation.choices if validation else None) == choices
    assert (validation.pattern if validation else None) == pattern


@pytest.mark.parametrize("key", sorted(PHASE2))
def test_each_key_is_set_at_every_scope_lockable_and_live(
    definitions: dict[str, SettingDefinition], key: str
) -> None:
    found = definitions[key]
    assert found.scopes == ["platform", "company", "project"]
    assert found.lockable is True
    assert found.effect == "live"
    assert found.sensitivity == "normal"
    assert found.since == "0.1.0"
    assert found.owner == "platform"
    assert found.description.strip() and found.docs and found.docs.strip()


@pytest.mark.parametrize("key", sorted(PHASE2))
def test_each_definition_is_coherent_and_its_default_is_a_valid_value(
    definitions: dict[str, SettingDefinition], key: str
) -> None:
    found = definitions[key]
    check_definition(found)
    assert normalise(found, found.default) == found.default


@pytest.mark.parametrize(
    ("key", "low", "high"),
    [
        ("awp.iwp.ready_lead_weeks", 0, 52),
        ("awp.backlog.target_weeks", 0, 52),
        ("awp.constraint.aging_days", 1, 365),
        ("scaffold.inspection.interval_days", 1, 90),
    ],
)
def test_an_integer_bound_accepts_the_edges_and_refuses_one_past_them(
    definitions: dict[str, SettingDefinition], key: str, low: int, high: int
) -> None:
    found = definitions[key]
    assert normalise(found, low) == low and normalise(found, high) == high
    with pytest.raises(InvalidSettingValueError, match="below the minimum"):
        normalise(found, low - 1)
    with pytest.raises(InvalidSettingValueError, match="above the maximum"):
        normalise(found, high + 1)


@pytest.mark.parametrize(
    "key", [k for k, v in PHASE2.items() if v[0] == "int"] + ["awp.constraint.auto_raise"]
)
def test_a_wrong_type_is_refused(definitions: dict[str, SettingDefinition], key: str) -> None:
    found = definitions[key]
    for wrong in ("4", 4.5, None, [1], True if found.type == "int" else 1):
        with pytest.raises(InvalidSettingValueError, match="takes a"):
            normalise(found, wrong)


def test_the_size_hours_pair_is_a_list_of_numbers_without_a_range_check(
    definitions: dict[str, SettingDefinition],
) -> None:
    found = definitions["awp.iwp.size_hours"]
    assert normalise(found, [10, 20]) == [10, 20]
    assert normalise(found, [100, 50]) == [100, 50]  # the module checks low < high
    with pytest.raises(InvalidSettingValueError):
        normalise(found, "60,850")
    with pytest.raises(InvalidSettingValueError):
        normalise(found, [{"low": 1}])


def test_signoff_roles_are_limited_to_the_choices(
    definitions: dict[str, SettingDefinition],
) -> None:
    found = definitions["awp.release.signoff_roles"]
    assert normalise(found, ["user", "superuser"]) == ["user", "superuser"]
    assert normalise(found, []) == []
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        normalise(found, ["viewer"])
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        normalise(found, ["superuser", "admin"])


@pytest.mark.parametrize(
    ("value", "good"),
    [
        ("", True),
        ("COAA 2024", True),
        ("a" * 64, True),
        ("a" * 65, False),
        (" leading space", False),
        ("-dash first", False),
        ("semi;colon", False),
    ],
)
def test_the_rules_of_credit_edition_is_empty_or_a_short_name(
    definitions: dict[str, SettingDefinition], value: str, good: bool
) -> None:
    found = definitions["awp.rules_of_credit.set"]
    if good:
        assert normalise(found, value) == value
    else:
        with pytest.raises(InvalidSettingValueError, match="pattern"):
            normalise(found, value)


@pytest.mark.parametrize(
    ("key", "good", "bad"),
    [
        (
            "awp.constraint.default_owners",
            ["user:alice", "user:a.b-c_1"],
            ["alice", "agent:x", "user:"],
        ),
        (
            "materials.receipt.mtr_required_categories",
            ["PIPE", "a.b-c_1"],
            ["", "-x", "a b", "x" * 65],
        ),
    ],
)
def test_list_items_follow_the_item_pattern(
    definitions: dict[str, SettingDefinition], key: str, good: list[str], bad: list[str]
) -> None:
    found = definitions[key]
    assert normalise(found, good) == good
    assert normalise(found, []) == []
    for item in bad:
        with pytest.raises(InvalidSettingValueError, match="pattern"):
            normalise(found, [good[0], item])


def test_the_two_risky_keys_are_the_only_advanced_ones_among_the_new_eleven(
    definitions: dict[str, SettingDefinition],
) -> None:
    assert {k for k in PHASE2 if definitions[k].risk == "advanced"} == {
        "awp.release.signoff_roles",
        "awp.release.allow_unknown_checks",
    }
