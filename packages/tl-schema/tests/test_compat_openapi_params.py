"""The became-required parameter rule: an optional parameter turning required breaks callers."""

from __future__ import annotations

import copy
from typing import Any

from tl_schema.compat import diff_openapi


def _doc(*params: dict[str, Any]) -> dict[str, Any]:
    return {
        "paths": {
            "/items": {
                "get": {
                    "parameters": list(params),
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }


OPTIONAL_Q = {"name": "q", "in": "query", "required": False}
REQUIRED_Q = {"name": "q", "in": "query", "required": True}


def test_optional_parameter_became_required() -> None:
    base = _doc(OPTIONAL_Q)
    current = copy.deepcopy(base)
    current["paths"]["/items"]["get"]["parameters"][0]["required"] = True
    assert diff_openapi(base, current) == ["GET /items: parameter 'q' became required"]


def test_optional_parameter_without_required_key_became_required() -> None:
    base = _doc({"name": "q", "in": "query"})
    assert diff_openapi(base, _doc(REQUIRED_Q)) == ["GET /items: parameter 'q' became required"]


def test_parameter_stays_optional_no_line() -> None:
    assert diff_openapi(_doc(OPTIONAL_Q), _doc(OPTIONAL_Q)) == []


def test_required_parameter_stays_required_no_line() -> None:
    assert diff_openapi(_doc(REQUIRED_Q), _doc(REQUIRED_Q)) == []


def test_new_optional_parameter_no_line() -> None:
    new_optional = {"name": "limit", "in": "query", "required": False}
    assert diff_openapi(_doc(OPTIONAL_Q), _doc(OPTIONAL_Q, new_optional)) == []
