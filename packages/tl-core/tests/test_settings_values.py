"""Setting values: types, ranges, bounds, parsing from text and display (brief 30.1, 30.2)."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.services.errors import InvalidSettingValueError, SettingOutOfBoundsError
from tl_core.settings.types import SettingDefinition, SettingValidation
from tl_core.settings.values import (
    check_bounds,
    check_bounds_shape,
    check_definition,
    duration_seconds,
    format_value,
    normalise,
    parse_text,
    size_bytes,
    within_bounds,
)


def defn(kind: str, default: Any, **validation: Any) -> SettingDefinition:
    return SettingDefinition.model_validate(
        {
            "key": "t.value",
            "type": kind,
            "default": default,
            "description": "d",
            "scopes": ["platform", "company", "project"],
            "validation": validation or None,
            "since": "0.1.0",
        }
    )


@pytest.mark.parametrize(
    ("kind", "good", "bad"),
    [
        ("bool", True, 1),
        ("bool", False, "false"),
        ("int", 5, 5.5),
        ("int", -3, True),
        ("decimal", 0.7, "0.7"),
        ("decimal", 3, True),
        ("string", "abc", 3),
        ("list", ["a", 1, True], "a"),
        ("duration", "5m", "5 minutes"),
        ("duration", "90s", 90),
        ("size", "50MB", "50 MB"),
        ("date", "2026-10-10", "2026-13-01"),
        ("json", {"a": [1, 2]}, float("nan")),
    ],
)
def test_each_type_takes_its_own_json_value(kind: str, good: Any, bad: Any) -> None:
    d = defn(kind, good)
    assert normalise(d, good) == good
    with pytest.raises(InvalidSettingValueError):
        normalise(d, bad)


def test_a_date_must_be_written_exactly() -> None:
    d = defn("date", "2026-10-10")
    for text in ("2026-1-1", "20261010", "2026-10-10T00:00:00"):
        with pytest.raises(InvalidSettingValueError):
            normalise(d, text)


def test_an_enum_takes_one_of_its_choices() -> None:
    d = defn("enum", "a", choices=["a", "b"])
    assert normalise(d, "b") == "b"
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        normalise(d, "c")


def test_a_string_pattern_must_match_in_full() -> None:
    d = defn("string", "ab", pattern="[a-z]+")
    assert normalise(d, "abc") == "abc"
    with pytest.raises(InvalidSettingValueError, match="pattern"):
        normalise(d, "abc1")


def test_list_choices_and_pattern_apply_to_each_item() -> None:
    chosen = defn("list", [], choices=["x", "y"])
    assert normalise(chosen, ["x", "y"]) == ["x", "y"]
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        normalise(chosen, ["x", "z"])
    patterned = defn("list", [], pattern="[a-z]+")
    with pytest.raises(InvalidSettingValueError, match="pattern"):
        normalise(patterned, ["ok", "Not"])
    with pytest.raises(InvalidSettingValueError, match="pattern"):
        normalise(patterned, [3])


def test_list_items_are_scalars_and_the_list_is_bounded() -> None:
    d = defn("list", [])
    with pytest.raises(InvalidSettingValueError, match="text, numbers or true/false"):
        normalise(d, [{"a": 1}])
    with pytest.raises(InvalidSettingValueError, match="more than"):
        normalise(d, ["x"] * 501)
    with pytest.raises(InvalidSettingValueError, match="longer"):
        normalise(d, ["x" * 5000])


def test_ranges_compare_numbers_seconds_and_bytes() -> None:
    assert normalise(defn("int", 5, minimum=1, maximum=10), 10) == 10
    with pytest.raises(InvalidSettingValueError, match="below the minimum"):
        normalise(defn("int", 5, minimum=1, maximum=10), 0)
    with pytest.raises(InvalidSettingValueError, match="above the maximum"):
        normalise(defn("decimal", 5, minimum=1, maximum=10), 10.5)
    d = defn("duration", "5m", minimum=10, maximum=86400)
    assert normalise(d, "10s") == "10s"
    assert normalise(d, "1d") == "1d"
    with pytest.raises(InvalidSettingValueError, match="below the minimum"):
        normalise(d, "9s")
    with pytest.raises(InvalidSettingValueError, match="above the maximum"):
        normalise(d, "2d")
    s = defn("size", "1MB", minimum=1024, maximum=1024**2)
    assert normalise(s, "1KB") == "1KB"
    with pytest.raises(InvalidSettingValueError):
        normalise(s, "2MB")


def test_units() -> None:
    assert duration_seconds("1w") == 604800 and duration_seconds("250ms") == 0.25
    assert size_bytes("1KB") == 1024 and size_bytes("2GB") == 2 * 1024**3
    for text in ("5", "m", "-5m", "5min", "1.5h", ""):
        with pytest.raises(InvalidSettingValueError):
            duration_seconds(text)
    with pytest.raises(InvalidSettingValueError):
        size_bytes("1kb")


def test_a_json_value_is_bounded_in_size() -> None:
    d = defn("json", None)
    assert normalise(d, {"k": "v"}) == {"k": "v"}
    with pytest.raises(InvalidSettingValueError, match="longer"):
        normalise(d, {"k": "v" * 70_000})


def test_a_definition_must_be_coherent() -> None:
    check_definition(defn("int", 3, minimum=1))
    with pytest.raises(ValueError, match="enum needs"):
        check_definition(defn("enum", "a"))
    with pytest.raises(ValueError, match="default is not valid"):
        check_definition(defn("int", 0, minimum=1))
    with pytest.raises(ValueError, match="range applies"):
        check_definition(defn("string", "a", minimum=1))
    with pytest.raises(ValueError, match="minimum is above maximum"):
        check_definition(defn("int", 5, minimum=9, maximum=2))
    with pytest.raises(ValueError, match="pattern is not valid"):
        check_definition(defn("string", "a", pattern="("))
    no_platform = defn("int", 3).model_copy(update={"scopes": ["company"]})
    with pytest.raises(ValueError, match="platform"):
        check_definition(no_platform)


# --- bounds the company sets for projects --------------------------------------------------------


def test_bounds_limit_numbers_durations_and_choices() -> None:
    num = defn("int", 5)
    check_bounds(num, {"minimum": 2, "maximum": 8}, 5)
    with pytest.raises(SettingOutOfBoundsError, match="below the company minimum"):
        check_bounds(num, {"minimum": 2}, 1)
    with pytest.raises(SettingOutOfBoundsError, match="above the company maximum"):
        check_bounds(num, {"maximum": 8}, 9)
    dur = defn("duration", "5m")
    check_bounds(dur, {"maximum": "1h"}, "30m")
    with pytest.raises(SettingOutOfBoundsError):
        check_bounds(dur, {"maximum": "1h"}, "2h")
    pick = defn("enum", "a", choices=["a", "b", "c"])
    check_bounds(pick, {"choices": ["a", "b"]}, "b")
    with pytest.raises(SettingOutOfBoundsError, match="choices"):
        check_bounds(pick, {"choices": ["a", "b"]}, "c")
    many = defn("list", [])
    check_bounds(many, {"choices": ["x", "y"]}, ["x"])
    with pytest.raises(SettingOutOfBoundsError):
        check_bounds(many, {"choices": ["x", "y"]}, ["x", "q"])
    check_bounds(num, None, 10**9)
    assert within_bounds(num, {"maximum": 3}, 3) is True
    assert within_bounds(num, {"maximum": 3}, 4) is False


@pytest.mark.parametrize(
    ("kind", "bounds"),
    [
        ("bool", {"minimum": 1}),
        ("string", {"maximum": 3}),
        ("int", {"minimum": "5"}),
        ("duration", {"maximum": 5}),
        ("int", {"minimum": 9, "maximum": 2}),
        ("duration", {"minimum": "2h", "maximum": "1h"}),
        ("int", {"wrong": 1}),
        ("enum", {"choices": []}),
        ("enum", {"choices": "a"}),
        ("bool", {"choices": [True]}),
    ],
)
def test_bounds_that_do_not_fit_the_type_are_refused(kind: str, bounds: dict[str, Any]) -> None:
    d = defn(
        kind, "a" if kind == "enum" else None, **({"choices": ["a"]} if kind == "enum" else {})
    )
    with pytest.raises(InvalidSettingValueError):
        check_bounds_shape(d, bounds)


def test_choices_of_a_bound_must_themselves_be_valid_values() -> None:
    pick = defn("enum", "a", choices=["a", "b"])
    assert check_bounds_shape(pick, {"choices": ["a"]}) == {"choices": ["a"]}
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        check_bounds_shape(pick, {"choices": ["z"]})


# --- text in, text out --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "text", "value"),
    [
        ("bool", "Yes", True),
        ("bool", "off", False),
        ("bool", " 1 ", True),
        ("int", " 42 ", 42),
        ("decimal", "0.7", 0.7),
        ("decimal", "24", 24),
        ("decimal", "24.0", 24.0),
        ("string", "  keep me  ", "keep me"),
        ("enum", "propose", "propose"),
        ("duration", "5m", "5m"),
        ("list", "a, b ,, c", ["a", "b", "c"]),
        ("list", '["a", 2]', ["a", 2]),
        ("list", "", []),
        ("json", '{"a": 1}', {"a": 1}),
    ],
)
def test_parse_text_reads_what_a_person_types(kind: str, text: str, value: Any) -> None:
    assert parse_text(defn(kind, None), text) == value


@pytest.mark.parametrize(
    ("kind", "text"),
    [("bool", "maybe"), ("int", "1.5"), ("int", "x"), ("decimal", "abc"), ("json", "{oops")],
)
def test_parse_text_refuses_what_it_cannot_read(kind: str, text: str) -> None:
    with pytest.raises(InvalidSettingValueError):
        parse_text(defn(kind, None), text)


def test_format_value_is_one_line() -> None:
    assert format_value(True) == "true" and format_value(None) == "null"
    assert format_value(["a", "b", "c", "d"]) == "[a, b, c, d]"
    assert format_value(["a", "b", "c", "d"], max_items=2) == "[a, b, +2]"
    assert format_value({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    assert format_value("5m") == "5m" and format_value(0.7) == "0.7"


def test_the_validation_model_has_only_the_four_documented_fields() -> None:
    assert set(SettingValidation.model_fields) == {"minimum", "maximum", "choices", "pattern"}


def test_a_number_too_large_for_a_float_is_out_of_range_not_an_error() -> None:
    d = defn("int", 5, minimum=1, maximum=10)
    with pytest.raises(InvalidSettingValueError, match="above the maximum"):
        normalise(d, 10**400)
    with pytest.raises(InvalidSettingValueError, match="below the minimum"):
        normalise(d, -(10**400))
    with pytest.raises(InvalidSettingValueError):
        normalise(d, 10**5000)
    with pytest.raises(SettingOutOfBoundsError, match="above the company maximum"):
        check_bounds(d, {"maximum": 8}, 10**400)
    with pytest.raises(SettingOutOfBoundsError, match="below the company minimum"):
        check_bounds(d, {"minimum": 2}, -(10**400))


def test_a_message_never_echoes_a_long_text_back_in_full() -> None:
    long_number = "9" * 5000
    for kind, text in (
        ("int", long_number),
        ("decimal", "x" * 5000),
        ("bool", "x" * 5000),
        ("duration", long_number + "m"),
        ("size", long_number + "MB"),
    ):
        d = defn(kind, 1 if kind == "int" else "5m" if kind == "duration" else True)
        with pytest.raises(InvalidSettingValueError) as caught:
            normalise(d, parse_text(d, text))
        assert len(str(caught.value)) < 250, kind
