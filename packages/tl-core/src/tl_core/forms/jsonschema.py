"""JSON Schema projection of a form's answers (P2-FORMS T01; ADR-0031).

A pure projection: no I/O, and it imports only ``tl_core.forms.rules`` and ``tl_core.forms.types``.
It describes the shape of each answer. Visibility, required answers and repeated questions are not
decided here; ``validate_answers`` decides them, and the top-level ``x-note`` says so.
"""

from __future__ import annotations

import copy
from typing import Any

from tl_core.forms.rules import validate_questions
from tl_core.forms.types import (
    FORMAT_1,
    FORMAT_2,
    MAX_ANSWER_TEXT,
    MAX_NOTE,
    MAX_PHOTOS,
)

_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_TOP_NOTE = "visibility, required answers and repeated questions are checked by validate_answers"
_YES_NO_NA = ["yes", "no", "na"]
_ULID_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"  # same as rules._ULID; photo file ids


def to_json_schema(fields: list[dict[str, Any]], fmt: int = FORMAT_2) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) for the answers list of a template with these fields.

    Raises ``ValueError`` for an unknown format, or for fields that ``validate_questions`` refuses
    (the first problem is the message).
    """
    if fmt not in (FORMAT_1, FORMAT_2):
        raise ValueError(f"unknown form format {fmt!r}")
    problems = validate_questions(fields, fmt=fmt)
    if problems:
        raise ValueError(problems[0])
    return {
        "$schema": _SCHEMA_URI,
        "type": "array",
        "maxItems": len(fields),
        "items": {"oneOf": [_branch(field) for field in fields]},
        "x-note": _TOP_NOTE,
    }


def _branch(field: dict[str, Any]) -> dict[str, Any]:
    branch: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["q", "value"],
        "title": field["text"],
        "properties": {
            "q": {"const": field["id"]},
            "value": _value_schema(field),
            "note": {"type": ["string", "null"], "maxLength": MAX_NOTE},
        },
        "x-required": field["required"],
        "x-section": field.get("section"),
        "x-help": field.get("help"),
        "x-visible-when": copy.deepcopy(field.get("visible_when")),
        "x-unit": field.get("unit"),
    }
    if field["kind"] == "number":
        branch["x-min"] = field.get("min")
        branch["x-max"] = field.get("max")
    # x- keys with a null value are left out
    return {key: value for key, value in branch.items() if value is not None}


def _value_schema(field: dict[str, Any]) -> dict[str, Any]:
    kind = field["kind"]
    if kind == "yes_no_na":
        return {"enum": list(_YES_NO_NA)}
    if kind == "number":
        return {"type": "number"}
    if kind == "text":
        return {"type": "string", "maxLength": MAX_ANSWER_TEXT}
    if kind == "choice":
        return {"enum": list(field["choices"])}
    if kind == "multi":
        return {
            "type": "array",
            "items": {"enum": list(field["choices"])},
            "uniqueItems": True,
        }
    if kind == "date":
        return {"type": "string", "format": "date"}
    if kind == "photo":
        return {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_PHOTOS,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": _ULID_PATTERN},
        }
    # validate_questions has already refused any other kind
    raise ValueError(f"unknown kind {kind!r}")
