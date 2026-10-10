"""Typed setting values: checking, parsing from text, bounds, and display (brief 30.1).

Values are JSON. ``normalise`` is the one gate a value passes before it is written: it knows each
``SettingType``, the definition's ``validation`` and the size limits that keep an event small.
``check_bounds`` applies the limits a company set for its projects (brief 30.2). ``parse_text``
turns what a person typed (CLI, TUI) into a value; it only parses, the caller still calls
``normalise``.

Units: a ``duration`` is ``<whole number><ms|s|m|h|d|w>`` and its range is in seconds; a ``size``
is ``<whole number><B|KB|MB|GB|TB>`` with binary multiples (``1KB`` is 1024 bytes) and its range is
in bytes.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date
from typing import Any, cast

from tl_core.services.errors import (
    InvalidSettingValueError,
    SettingOutOfBoundsError,
)
from tl_core.settings.types import SettingDefinition

MAX_LIST_ITEMS = 500
MAX_STRING = 4096
MAX_JSON_CHARS = 64_000

_KEY = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
_DURATION = re.compile(r"(\d{1,12})(ms|s|m|h|d|w)")
_SIZE = re.compile(r"(\d{1,15})(B|KB|MB|GB|TB)")
_DURATION_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0}
_SIZE_BYTES = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
_TRUE = frozenset({"true", "yes", "on", "1"})
_FALSE = frozenset({"false", "no", "off", "0"})
_NUMERIC_TYPES = frozenset({"int", "decimal", "duration", "size"})
_BOUND_KEYS = frozenset({"minimum", "maximum", "choices"})


def duration_seconds(value: str) -> float:
    """Seconds in a duration text such as ``5m``. Raises ``InvalidSettingValueError``."""
    found = _DURATION.fullmatch(value)
    if found is None:
        raise InvalidSettingValueError(
            f"{value!r} is not a duration: a whole number and a unit, as in 90s, 5m, 24h or 2w"
        )
    return int(found.group(1)) * _DURATION_SECONDS[found.group(2)]


def size_bytes(value: str) -> int:
    """Bytes in a size text such as ``50MB``. Raises ``InvalidSettingValueError``."""
    found = _SIZE.fullmatch(value)
    if found is None:
        raise InvalidSettingValueError(
            f"{value!r} is not a size: a whole number and a unit, as in 512KB or 50MB"
        )
    return int(found.group(1)) * _SIZE_BYTES[found.group(2)]


def is_number(value: Any) -> bool:
    """A JSON number (int or finite float); a bool is not one."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (isinstance(value, int) or math.isfinite(value))
    )


def numeric_of(setting_type: str, value: Any) -> float | None:
    """The number a range applies to: the value, its seconds, or its bytes; None if not numeric."""
    if setting_type in ("int", "decimal") and is_number(value):
        return float(value)
    if setting_type == "duration" and isinstance(value, str):
        return duration_seconds(value)
    if setting_type == "size" and isinstance(value, str):
        return float(size_bytes(value))
    return None


def _matches(pattern: str, text: str) -> bool:
    try:
        return re.fullmatch(pattern, text) is not None
    except re.error as exc:
        raise InvalidSettingValueError(f"the definition's pattern is not valid: {exc}") from exc


def same_json(left: Any, right: Any) -> bool:
    """Whether two JSON values are the same value of the same JSON type.

    Python says ``True == 1`` and ``1.0 == 1``; JSON does not, so equality for no-op detection and
    for choices goes through the canonical text (``true`` is not ``1``, ``1.0`` is not ``1``).
    """
    try:
        return _canonical(left) == _canonical(right)
    except (TypeError, ValueError):
        return False


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def in_choices(value: Any, choices: Any) -> bool:
    """Whether ``value`` is one of ``choices`` (a list), by :func:`same_json`."""
    return isinstance(choices, list) and any(same_json(value, c) for c in choices)  # pyright: ignore[reportUnknownVariableType]


def _describe(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=repr)
    return text if len(text) <= 80 else text[:77] + "..."


def _check_item(defn: SettingDefinition, item: Any) -> None:
    validation = defn.validation
    if isinstance(item, str):
        if len(item) > MAX_STRING:
            raise InvalidSettingValueError(f"{defn.key}: an item is longer than {MAX_STRING}")
    elif not (is_number(item) or isinstance(item, bool)):
        raise InvalidSettingValueError(
            f"{defn.key}: list items are text, numbers or true/false, not {_describe(item)}"
        )
    if validation is None:
        return
    if validation.choices is not None and not in_choices(item, validation.choices):
        raise InvalidSettingValueError(
            f"{defn.key}: {_describe(item)} is not one of {_describe(validation.choices)}"
        )
    if validation.pattern is not None and not (
        isinstance(item, str) and _matches(validation.pattern, item)
    ):
        raise InvalidSettingValueError(
            f"{defn.key}: {_describe(item)} does not match the pattern {validation.pattern}"
        )


def _check_range(defn: SettingDefinition, value: Any) -> None:
    validation = defn.validation
    if validation is None:
        return
    number = numeric_of(defn.type, value)
    if number is None:
        return
    if validation.minimum is not None and number < validation.minimum:
        raise InvalidSettingValueError(
            f"{defn.key}: {_describe(value)} is below the minimum {validation.minimum:g}"
        )
    if validation.maximum is not None and number > validation.maximum:
        raise InvalidSettingValueError(
            f"{defn.key}: {_describe(value)} is above the maximum {validation.maximum:g}"
        )


def _wrong_type(defn: SettingDefinition, value: Any) -> InvalidSettingValueError:
    return InvalidSettingValueError(f"{defn.key} takes a {defn.type} value, not {_describe(value)}")


def _check_text(defn: SettingDefinition, value: str) -> None:
    kind = defn.type
    if len(value) > MAX_STRING:
        raise InvalidSettingValueError(f"{defn.key}: the text is longer than {MAX_STRING}")
    validation = defn.validation
    if kind == "enum":
        choices = validation.choices if validation is not None else None
        if choices is None or not in_choices(value, choices):
            raise InvalidSettingValueError(
                f"{defn.key}: {_describe(value)} is not one of {_describe(choices or [])}"
            )
    elif kind == "string":
        pattern = validation.pattern if validation is not None else None
        if pattern is not None and not _matches(pattern, value):
            raise InvalidSettingValueError(
                f"{defn.key}: {_describe(value)} does not match the pattern {pattern}"
            )
    elif kind == "duration":
        duration_seconds(value)
    elif kind == "size":
        size_bytes(value)
    elif kind == "date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError(value)
        except ValueError as exc:
            raise InvalidSettingValueError(
                f"{defn.key}: {_describe(value)} is not a date (YYYY-MM-DD)"
            ) from exc


def normalise(defn: SettingDefinition, value: Any) -> Any:
    """``value`` if it is a valid value of ``defn``, else ``InvalidSettingValueError``.

    Checks the type, the definition's ``validation`` (range, ``choices``, ``pattern``; for a
    list they apply to each item) and the size limits (at most ``MAX_LIST_ITEMS`` items, strings
    of ``MAX_STRING`` characters, ``MAX_JSON_CHARS`` of JSON for a ``json`` value). It does not
    convert: ``"5"`` is not an ``int``.
    """
    kind = defn.type
    original = value
    if kind == "bool":
        if not isinstance(value, bool):
            raise _wrong_type(defn, value)
    elif kind == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise _wrong_type(defn, value)
    elif kind == "decimal":
        if not is_number(value):
            raise _wrong_type(defn, value)
    elif kind == "list":
        if not isinstance(value, list):
            raise _wrong_type(defn, value)
        items = cast("list[Any]", value)
        if len(items) > MAX_LIST_ITEMS:
            raise InvalidSettingValueError(f"{defn.key}: more than {MAX_LIST_ITEMS} items")
        for item in items:
            _check_item(defn, item)
    elif kind == "json":
        try:
            text = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InvalidSettingValueError(f"{defn.key}: the value is not JSON data") from exc
        if len(text) > MAX_JSON_CHARS:
            raise InvalidSettingValueError(
                f"{defn.key}: the JSON is longer than {MAX_JSON_CHARS} characters"
            )
    else:  # string, enum, duration, size, date
        if not isinstance(value, str):
            raise _wrong_type(defn, value)
        _check_text(defn, value)
    _check_range(defn, original)
    return original


def check_definition(defn: SettingDefinition) -> None:
    """Raise ``ValueError`` unless the definition is coherent and its default is a valid value."""
    if _KEY.fullmatch(defn.key) is None:
        raise ValueError(
            f"{defn.key!r} is not a key: dotted lower-case words, as in feed.reactions.enabled"
        )
    if defn.type == "enum" and not (defn.validation and defn.validation.choices):
        raise ValueError(f"{defn.key}: an enum needs validation.choices")
    if defn.validation is not None:
        v = defn.validation
        if (v.minimum is not None or v.maximum is not None) and defn.type not in _NUMERIC_TYPES:
            raise ValueError(f"{defn.key}: a range applies to int, decimal, duration and size")
        if v.minimum is not None and v.maximum is not None and v.minimum > v.maximum:
            raise ValueError(f"{defn.key}: minimum is above maximum")
        if v.pattern is not None:
            try:
                re.compile(v.pattern)
            except re.error as exc:
                raise ValueError(f"{defn.key}: pattern is not valid: {exc}") from exc
    if "platform" not in defn.scopes:
        raise ValueError(f"{defn.key}: scopes must include platform (the default)")
    try:
        normalise(defn, defn.default)
    except InvalidSettingValueError as exc:
        raise ValueError(f"{defn.key}: the default is not valid: {exc}") from exc


def _limit_number(defn: SettingDefinition, name: str, raw: Any) -> float:
    """A bound's number: the value for int and decimal, seconds or bytes for duration and size."""
    if defn.type in ("duration", "size"):
        if not isinstance(raw, str):
            raise InvalidSettingValueError(f"{defn.key}: {name} must be text such as 10m or 5MB")
        found = numeric_of(defn.type, raw)
        assert found is not None
        return found
    if not is_number(raw):
        raise InvalidSettingValueError(f"{defn.key}: {name} must be a number")
    return float(raw)


def check_bounds_shape(defn: SettingDefinition, bounds: dict[str, Any]) -> dict[str, Any]:
    """The bounds a company may set for ``defn``, checked; raises ``InvalidSettingValueError``.

    Keys are ``minimum`` and ``maximum`` (for int, decimal, duration and size: a number, or for
    the last two their text such as ``10m``) and ``choices`` (a list of values, each valid for the
    definition, or items of it for a list). The result has numbers for ``minimum`` and
    ``maximum`` as given.
    """
    unknown = set(bounds) - _BOUND_KEYS
    if unknown:
        raise InvalidSettingValueError(
            f"{defn.key}: bounds may use minimum, maximum and choices, not {sorted(unknown)}"
        )
    clean: dict[str, Any] = {}
    numbers: dict[str, float] = {}
    for name in ("minimum", "maximum"):
        if bounds.get(name) is None:
            continue
        if defn.type not in _NUMERIC_TYPES:
            raise InvalidSettingValueError(
                f"{defn.key}: {name} applies to int, decimal, duration and size, not {defn.type}"
            )
        numbers[name] = _limit_number(defn, name, bounds[name])
        clean[name] = bounds[name]
    if len(numbers) == 2 and numbers["minimum"] > numbers["maximum"]:
        raise InvalidSettingValueError(f"{defn.key}: minimum is above maximum")
    if bounds.get("choices") is not None:
        choices = bounds["choices"]
        if defn.type in ("json", "bool") or not isinstance(choices, list) or not choices:
            raise InvalidSettingValueError(
                f"{defn.key}: choices must be a non-empty list (not for bool or json keys)"
            )
        if len(choices) > MAX_LIST_ITEMS:  # pyright: ignore[reportUnknownArgumentType]
            raise InvalidSettingValueError(f"{defn.key}: more than {MAX_LIST_ITEMS} choices")
        for choice in choices:  # pyright: ignore[reportUnknownVariableType]
            if defn.type == "list":
                _check_item(defn, choice)
            else:
                normalise(defn, choice)
        clean["choices"] = choices
    return clean


def check_bounds(defn: SettingDefinition, bounds: dict[str, Any] | None, value: Any) -> None:
    """Raise ``SettingOutOfBoundsError`` when ``value`` breaks the company's ``bounds``."""
    if not bounds:
        return
    number = numeric_of(defn.type, value)
    if number is not None:
        low = bounds.get("minimum")
        if low is not None and number < _limit_number(defn, "minimum", low):
            raise SettingOutOfBoundsError(
                f"{defn.key}: {_describe(value)} is below the company minimum "
                f"{_describe(low)} for projects"
            )
        high = bounds.get("maximum")
        if high is not None and number > _limit_number(defn, "maximum", high):
            raise SettingOutOfBoundsError(
                f"{defn.key}: {_describe(value)} is above the company maximum "
                f"{_describe(high)} for projects"
            )
    choices = bounds.get("choices")
    if choices is not None:
        items = value if defn.type == "list" else [value]
        for item in items:
            if not in_choices(item, choices):
                raise SettingOutOfBoundsError(
                    f"{defn.key}: {_describe(item)} is not one of the company's choices "
                    f"{_describe(choices)} for projects"
                )


def within_bounds(defn: SettingDefinition, bounds: dict[str, Any] | None, value: Any) -> bool:
    """Whether ``value`` keeps to ``bounds`` (the resolver ignores a stored value that does not)."""
    try:
        check_bounds(defn, bounds, value)
    except SettingOutOfBoundsError:
        return False
    except InvalidSettingValueError:
        return False
    return True


def parse_text(defn: SettingDefinition, text: str) -> Any:
    """What a person typed, as a value of ``defn``'s type (not yet checked: call ``normalise``).

    ``bool`` takes true/false/yes/no/on/off/1/0; ``int`` and ``decimal`` take numbers; ``list``
    takes JSON (``["a", "b"]``) or comma-separated words; ``json`` takes JSON; the rest keep the
    text. Raises ``InvalidSettingValueError`` when the text cannot be read as that type.
    """
    kind = defn.type
    stripped = text.strip()
    if kind == "bool":
        word = stripped.lower()
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
        raise InvalidSettingValueError(f"{defn.key}: {text!r} is not true or false")
    if kind == "int":
        try:
            return int(stripped)
        except ValueError as exc:
            raise InvalidSettingValueError(f"{defn.key}: {text!r} is not a whole number") from exc
    if kind == "decimal":
        try:
            number = float(stripped)
        except ValueError as exc:
            raise InvalidSettingValueError(f"{defn.key}: {text!r} is not a number") from exc
        return int(number) if number.is_integer() and "." not in stripped else number
    if kind in ("list", "json"):
        if kind == "json" or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except ValueError as exc:
                raise InvalidSettingValueError(f"{defn.key}: {text!r} is not JSON") from exc
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return stripped


def format_value(value: Any, *, max_items: int | None = None) -> str:
    """A value as one line: ``true``, ``24``, ``5m``, ``[a, b, +2]`` (with ``max_items``)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        items = [format_value(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        if max_items is not None and len(items) > max_items:  # pyright: ignore[reportUnknownArgumentType]
            extra = len(items) - max_items  # pyright: ignore[reportUnknownArgumentType]
            items = [*items[:max_items], f"+{extra}"]
        return "[" + ", ".join(items) + "]"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
