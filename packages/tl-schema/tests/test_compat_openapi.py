"""The OpenAPI compatibility diff: additive passes; each breaking kind gives one line."""

from __future__ import annotations

import copy
from typing import Any

from tl_schema.compat import diff_openapi

ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": ["a", "b"]}},
    "required": ["id"],
}
BASE: dict[str, Any] = {
    "paths": {
        "/items": {
            "get": {
                "parameters": [{"name": "q", "in": "query", "required": False}],
                "responses": {"200": {"description": "ok"}, "404": {"description": "none"}},
            },
            "post": {"responses": {"200": {"description": "ok"}}},
        }
    },
    "components": {"schemas": {"Item": ITEM}},
}


def _new(fn: Any) -> list[str]:
    doc = copy.deepcopy(BASE)
    fn(doc)
    return diff_openapi(BASE, doc)


def _item(doc: dict[str, Any]) -> dict[str, Any]:
    return doc["components"]["schemas"]["Item"]  # type: ignore[no-any-return]


def _has(lines: list[str], *parts: str) -> bool:
    return any(all(p in line for p in parts) for line in lines)


def test_identical_and_additive_pass() -> None:
    assert diff_openapi(BASE, BASE) == []

    def grow(doc: dict[str, Any]) -> None:
        doc["paths"]["/new"] = {"get": {"responses": {"200": {"description": "ok"}}}}
        doc["paths"]["/items"]["get"]["parameters"].append(
            {"name": "page", "in": "query", "required": False}
        )
        doc["paths"]["/items"]["get"]["responses"]["500"] = {"description": "boom"}
        _item(doc)["properties"]["note"] = {"type": ["string", "null"]}
        _item(doc)["properties"]["kind"]["enum"].append("c")
        doc["components"]["schemas"]["Other"] = {"type": "object"}

    assert _new(grow) == []


def test_removed_operation_and_path() -> None:
    assert _has(
        _new(lambda d: d["paths"]["/items"].pop("post")), "POST /items", "operation removed"
    )
    assert _has(_new(lambda d: d["paths"].pop("/items")), "GET /items", "operation removed")


def test_removed_response_code() -> None:
    lines = _new(lambda d: d["paths"]["/items"]["get"]["responses"].pop("404"))
    assert _has(lines, "GET /items", "response 404 removed")


def test_removed_property_and_schema() -> None:
    assert _has(_new(lambda d: _item(d)["properties"].pop("kind")), "Item", "'kind' removed")
    assert _has(_new(lambda d: d["components"]["schemas"].pop("Item")), "Item", "removed")


def test_newly_required_field() -> None:
    assert _has(_new(lambda d: _item(d)["required"].append("kind")), "Item", "became required")

    def add(doc: dict[str, Any]) -> None:
        _item(doc)["properties"]["z"] = {"type": "string"}
        _item(doc)["required"].append("z")

    assert _has(_new(add), "Item", "'z'", "added as required")


def test_narrowed_enum() -> None:
    assert _has(
        _new(lambda d: _item(d)["properties"]["kind"]["enum"].pop()), "Item", "enum tightened"
    )


def test_new_required_parameter() -> None:
    def add(doc: dict[str, Any]) -> None:
        doc["paths"]["/items"]["get"]["parameters"].append(
            {"name": "tenant", "in": "query", "required": True}
        )

    assert _has(_new(add), "GET /items", "parameter 'tenant'", "added as required")
