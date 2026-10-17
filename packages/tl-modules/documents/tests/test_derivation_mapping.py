"""The publish mapping: its LinkML-generated format and the rules that need the row schema."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tl_mod_documents.derivation.mapping import MappingInvalidError, check_mapping

ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tag"],
    "properties": {
        "tag": {"type": "string"},
        "service": {"type": "string"},
        "type": {"type": "string"},
        "size_in": {"type": "number"},
        "title": {"type": "string"},
    },
}
TAGS: dict[str, Any] = {
    "target": "tags",
    "key_column": "tag",
    "columns": [
        {"column": "tag", "to": "number"},
        {"column": "service", "to": "service"},
        {"column": "type", "to": "class", "values": {"CV": "ControlValve"}},
        {"column": "size_in", "to": "psets.valve_data.size_in"},
    ],
}
DOCUMENTS: dict[str, Any] = {
    "target": "documents",
    "key_column": "tag",
    "columns": [{"column": "tag", "to": "number"}, {"column": "title", "to": "title"}],
}


def problems_of(raw: Any, kind: str | None = "tags", schema: dict[str, Any] | None = None) -> str:
    with pytest.raises(MappingInvalidError) as caught:
        check_mapping(raw, schema or ROW_SCHEMA, kind)
    return "; ".join(caught.value.problems)


def test_a_good_mapping_of_each_kind_is_parsed() -> None:
    tags = check_mapping(TAGS, ROW_SCHEMA, "tags")
    assert tags.target == "tags" and tags.key_column == "tag" and len(tags.columns) == 4
    assert tags.columns[2].values == {"CV": "ControlValve"}
    docs = check_mapping(DOCUMENTS, ROW_SCHEMA, "documents")
    assert [c.to for c in docs.columns] == ["number", "title"]


def test_a_custom_pset_property_is_a_target() -> None:
    raw = copy.deepcopy(TAGS)
    raw["columns"].append({"column": "service", "to": "psets.valve_data.x.fat_by"})
    assert "mapped twice" in problems_of(raw)
    raw["columns"][-1]["column"] = "title"
    assert check_mapping(raw, ROW_SCHEMA, "tags").columns[-1].to == "psets.valve_data.x.fat_by"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda m: m.pop("columns"), "columns"),
        (lambda m: m.update(target="widgets"), "target"),
        (lambda m: m.update(extra=1), "extra"),
        (lambda m: m["columns"].clear(), "columns"),
        (lambda m: m["columns"][0].update(to="Number"), "to"),
        (lambda m: m["columns"][0].update(to="psets.valve_data"), "to"),
        (lambda m: m["columns"][0].pop("column"), "column"),
    ],
)
def test_a_mapping_that_does_not_fit_its_format_is_refused_with_the_place(
    change: Any, fragment: str
) -> None:
    raw = copy.deepcopy(TAGS)
    change(raw)
    assert fragment in problems_of(raw)


def test_what_is_not_an_object_is_refused() -> None:
    for raw in ("tags", None, [], 3):
        assert "must be an object" in problems_of(raw)


def test_the_schema_must_be_publishable_as_the_mapping_says() -> None:
    assert "no target_kind" in problems_of(TAGS, kind=None)
    assert "publishes 'tags' but the schema's target_kind is 'documents'" in problems_of(
        TAGS, kind="documents"
    )


def test_every_column_must_be_a_property_of_the_row_schema() -> None:
    raw = copy.deepcopy(TAGS)
    raw["columns"][1]["column"] = "nowhere"
    assert "column 'nowhere' is not a property" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["key_column"] = "nowhere"
    assert "key_column 'nowhere'" in problems_of(raw)


def test_exactly_one_column_is_the_number_and_it_is_the_key() -> None:
    raw = copy.deepcopy(TAGS)
    raw["columns"].pop(0)
    assert "exactly one column must map to number" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["key_column"] = "service"
    assert "must be the column mapped to number ('tag')" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["columns"][1]["to"] = "number"
    text = problems_of(raw)
    assert "two columns map to number" in text and "exactly one column" in text


def test_a_target_must_be_one_the_kind_takes() -> None:
    raw = copy.deepcopy(DOCUMENTS)
    raw["columns"].append({"column": "service", "to": "class"})
    assert "'class' is not a field a documents row takes" in problems_of(raw, "documents")
    raw = copy.deepcopy(DOCUMENTS)
    raw["columns"].append({"column": "service", "to": "psets.valve_data.size_in"})
    assert "only tags take property sets" in problems_of(raw, "documents")
    raw = copy.deepcopy(TAGS)
    raw["columns"].append({"column": "title", "to": "title"})
    assert "'title' is not a field a tags row takes" in problems_of(raw)


def test_a_document_needs_a_title() -> None:
    raw = copy.deepcopy(DOCUMENTS)
    raw["columns"].pop(1)
    assert "needs a title" in problems_of(raw, "documents")


def test_translations_are_for_text_columns_and_are_bounded() -> None:
    raw = copy.deepcopy(TAGS)
    raw["columns"][3]["values"] = {"4": "four"}
    assert "translations apply to text columns only" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["columns"][2]["values"] = {str(i): "x" for i in range(501)}
    assert "more than 500 translations" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["columns"][2]["values"] = {"CV": "x" * 201}
    assert "longer than 200" in problems_of(raw)
    raw = copy.deepcopy(TAGS)
    raw["columns"][2]["values"] = {"CV": 1}
    assert problems_of(raw)  # a non-text translation is refused (pydantic)
