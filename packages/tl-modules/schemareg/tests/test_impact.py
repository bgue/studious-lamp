"""The impact report of a change of the effective schema (brief 27.4, 27.7; P1-I8-T03)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from tl_mod_schemareg import impact as impact_module
from tl_mod_schemareg.impact import impact_report
from tl_mod_schemareg.impact_types import (
    MAX_ENTRIES,
    ImpactFacts,
    ImpactReport,
    Reference,
)
from tl_mod_schemareg.testing import fixture_text, next_version
from tl_schema.compose import compose
from tl_schema.effective import EffectiveSchema
from tl_schema.registry import parse_package

Edit = Callable[[dict[str, Any]], None]
SIZE = "psets.valve_data.size_in"
TAG = "psets.valve_data.tag_no"


def schema_of(text: str, scope: str = "company") -> EffectiveSchema:
    return compose([parse_package(text, source="test")], scope)


def old_new(edit: Edit, scope: str = "company") -> tuple[EffectiveSchema, EffectiveSchema]:
    old = schema_of(fixture_text("co.acme.engineering"), scope)
    return old, schema_of(next_version("co.acme.engineering", "3.3.0", edit), scope)


def props(data: dict[str, Any]) -> dict[str, Any]:
    return data["psets"]["valve_data"]["properties"]


def report(edit: Edit, facts: ImpactFacts | None = None, scope: str = "company") -> ImpactReport:
    old, new = old_new(edit, scope)
    return impact_report(old, new, facts or ImpactFacts())


def entries(r: ImpactReport, section: str) -> list[tuple[str, str]]:
    return [(e.target, e.change) for e in r.entries if e.section == section]


def add_plain(data: dict[str, Any]) -> None:
    props(data)["seat_leak_class"] = {"description": "Seat leakage class.", "range": "string"}


def test_nothing_changed_touches_nothing() -> None:
    old = schema_of(fixture_text("co.acme.engineering"))
    r = impact_report(old, old, ImpactFacts(value_counts={SIZE: 40}))
    assert r.entries == () and r.changed_paths == () and r.counts == {} and not r.truncated
    assert (r.old_hash, r.new_hash, r.scope) == (old.hash, old.hash, "company")


def test_a_label_or_description_alone_is_not_a_change() -> None:
    def reword(data: dict[str, Any]) -> None:
        props(data)["tag_no"]["label"] = "Tag"
        props(data)["tag_no"]["description"] = "The instrument tag, reworded."

    r = report(reword, ImpactFacts(value_counts={TAG: 9}))
    assert r.changed_paths == () and r.entries == ()


def test_an_added_property_has_no_records_but_changes_the_views_and_the_tool_schema() -> None:
    r = report(add_plain, ImpactFacts(value_counts={"psets.valve_data.seat_leak_class": 5}))
    assert r.changed_paths == ("psets.valve_data.seat_leak_class",)
    assert entries(r, "records") == []
    assert entries(r, "views") == [("project views of company", "views_regenerated")]
    assert entries(r, "mcp_schemas") == [("core.Record tool input schema", "schema_regenerated")]
    (tool,) = [e for e in r.entries if e.section == "mcp_schemas"]
    assert tool.detail == "the input schema for core.Record changes (1 property)"
    assert r.counts == {"views": 1, "mcp_schemas": 1}


def test_a_removed_property_lists_the_records_that_hold_values() -> None:
    def remove(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]

    r = report(remove, ImpactFacts(value_counts={TAG: 12}))
    assert entries(r, "records") == [(TAG, "property_removed")]
    (entry,) = [e for e in r.entries if e.section == "records"]
    assert entry.count == 12 and "12 record(s)" in entry.detail and "history" in entry.detail
    assert entries(r, "views") == [("project views of company", "views_regenerated")]


def test_a_removed_property_nobody_holds_a_value_for_lists_no_records() -> None:
    def remove(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]

    assert entries(report(remove, ImpactFacts(value_counts={TAG: 0})), "records") == []
    assert entries(report(remove), "records") == []


def _retype(data: dict[str, Any]) -> None:
    props(data)["size_in"]["range"] = "int"


def _reunit(data: dict[str, Any]) -> None:
    props(data)["size_in"]["unit"] = "mm"


def _more_values(data: dict[str, Any]) -> None:
    data["code_lists"]["MaterialCode"]["values"].append({"code": "TI", "label": "Titanium"})


def _require(data: dict[str, Any]) -> None:
    props(data)["size_in"]["required_in_states"] = ["Design"]


def _floor(data: dict[str, Any]) -> None:
    props(data)["size_in"]["minimum"] = 1


def _pattern(data: dict[str, Any]) -> None:
    props(data)["tag_no"]["pattern"] = "^[A-Z]{1,3}-[0-9]{4}$"


def _default(data: dict[str, Any]) -> None:
    props(data)["manufacturer"]["default"] = "Acme"


def _more_mappings(data: dict[str, Any]) -> None:
    props(data)["size_in"]["exact_mappings"] = ["cfihos:CFIHOS-40000123", "ifc:Size"]


MANUFACTURER = "psets.valve_data.manufacturer"
BODY = "psets.valve_data.body_material"


@pytest.mark.parametrize(
    "edit, path, code",
    [
        (_retype, SIZE, "type_changed"),
        (_reunit, SIZE, "type_changed"),
        (_more_values, BODY, "values_changed"),
        (_require, SIZE, "rule_changed"),
        (_floor, SIZE, "rule_changed"),
        (_pattern, TAG, "rule_changed"),
        (_default, MANUFACTURER, "definition_changed"),
        (_more_mappings, SIZE, "definition_changed"),
    ],
)
def test_a_modified_property_gets_the_code_of_the_field_that_changed(
    edit: Edit, path: str, code: str
) -> None:
    r = report(edit, ImpactFacts(value_counts={path: 7}))
    assert r.changed_paths == (path,)
    assert entries(r, "records") == [(path, code)]
    (entry,) = [e for e in r.entries if e.section == "records"]
    assert entry.count == 7 and "checked again" in entry.detail
    assert entries(r, "views") == []  # a modified property adds nothing to the views


def test_a_custom_section_property_is_addressed_with_x() -> None:
    company = parse_package(fixture_text("co.acme.engineering"), source="company")
    old = compose([company, parse_package(fixture_text("x.P123"), source="ext")], "project:P123")
    changed = fixture_text("x.P123").replace(
        "      fat_witness_by:\n        label: FAT witness\n"
        "        description: Client witness for the factory acceptance test.\n"
        "        range: string",
        "      fat_witness_by:\n        label: FAT witness\n"
        "        description: Client witness for the factory acceptance test.\n"
        "        range: int",
    )
    assert changed != fixture_text("x.P123")
    new = compose([company, parse_package(changed, source="ext")], "project:P123")
    path = "psets.valve_data.x.fat_witness_by"
    r = impact_report(old, new, ImpactFacts(value_counts={path: 6}))
    assert r.changed_paths == (path,)
    assert entries(r, "records") == [(path, "type_changed")]


def test_the_strongest_group_wins_when_several_fields_change() -> None:
    def edit(data: dict[str, Any]) -> None:
        props(data)["size_in"]["range"] = "int"  # type
        props(data)["size_in"]["minimum"] = 2  # rule

    r = report(edit, ImpactFacts(value_counts={SIZE: 3}))
    assert entries(r, "records") == [(SIZE, "type_changed")]


def test_a_property_that_becomes_materialized_gets_a_column() -> None:
    def edit(data: dict[str, Any]) -> None:
        props(data)["tag_no"]["materialize"] = True

    r = report(edit)
    assert entries(r, "columns") == [("pset__valve_data__tag_no", "column_added")]
    assert entries(r, "views") == [("project views of company", "views_regenerated")]


def test_a_property_that_stops_being_materialized_keeps_its_column() -> None:
    def edit(data: dict[str, Any]) -> None:
        props(data)["size_in"]["materialize"] = False

    r = report(edit)
    assert entries(r, "columns") == [("pset__valve_data__size_in", "column_dropped")]
    (entry,) = [e for e in r.entries if e.section == "columns"]
    assert "stays" in entry.detail


def test_a_column_that_changes_type_is_reported() -> None:
    def edit(data: dict[str, Any]) -> None:
        props(data)["size_in"]["range"] = "string"
        del props(data)["size_in"]["unit"]
        del props(data)["size_in"]["minimum"]
        del props(data)["size_in"]["maximum"]

    r = report(edit)
    assert entries(r, "columns") == [("pset__valve_data__size_in", "column_type_changed")]


def test_a_new_pset_adds_views_columns_and_tool_schemas_for_its_types() -> None:
    def edit(data: dict[str, Any]) -> None:
        data["psets"]["pump_data"] = {
            "description": "Pump data for rotating equipment.",
            "applies_to": ["engineering.Tag"],
            "properties": {
                "flow": {"description": "Rated flow.", "range": "decimal", "materialize": True}
            },
        }

    r = report(edit)
    assert "psets.pump_data.flow" in r.changed_paths
    assert entries(r, "columns") == [("pset__pump_data__flow", "column_added")]
    assert ("engineering.Tag tool input schema", "schema_regenerated") in entries(r, "mcp_schemas")


def test_a_mapping_that_names_a_removed_or_modified_path_is_listed() -> None:
    def edit(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]
        props(data)["size_in"]["minimum"] = 1

    facts = ImpactFacts(
        references=[
            Reference("mapping", "instrument-index", TAG),
            Reference("rule", "size-check", SIZE),
            Reference("endpoint", "ep-1", "psets.valve_data.manufacturer"),  # unchanged
            Reference("enricher", "e-1", "psets.valve_data.seat_leak_class"),  # unknown
        ]
    )
    r = report(edit, facts)
    assert entries(r, "mappings") == [
        ("mapping instrument-index", "property_removed"),
        ("rule size-check", "rule_changed"),
    ]
    (removed,) = [e for e in r.entries if e.target == "mapping instrument-index"]
    assert removed.detail == f"mapping instrument-index names {TAG}, which is removed"
    (changed,) = [e for e in r.entries if e.target == "rule size-check"]
    assert changed.detail == f"rule size-check names {SIZE}, which has changed"


def test_a_reference_to_an_added_path_is_not_an_impact() -> None:
    facts = ImpactFacts(references=[Reference("mapping", "m", "psets.valve_data.seat_leak_class")])
    assert entries(report(add_plain, facts), "mappings") == []


def test_reports_are_a_section_of_their_own() -> None:
    def edit(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]

    facts = ImpactFacts(references=[Reference("report", "tag conformance report", TAG)])
    r = report(edit, facts)
    assert entries(r, "reports") == [("report tag conformance report", "property_removed")]
    assert entries(r, "mappings") == []


def test_a_first_schema_has_every_path_added_and_every_column_new() -> None:
    new = schema_of(fixture_text("co.acme.engineering"))
    r = impact_report(None, new, ImpactFacts(value_counts={SIZE: 4}))
    assert r.old_hash is None and r.new_hash == new.hash
    assert SIZE in r.changed_paths and entries(r, "records") == []
    assert ("pset__valve_data__size_in", "column_added") in entries(r, "columns")
    assert entries(r, "views") == [("project views of company", "views_regenerated")]


def test_the_scope_names_the_view_entry() -> None:
    r = report(add_plain, scope="project:P123")
    assert r.scope == "project:P123"
    assert entries(r, "views") == [("project views of project:P123", "views_regenerated")]


def test_entries_are_ordered_by_section_then_target_and_counts_follow_the_section_order() -> None:
    def edit(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]
        props(data)["size_in"]["minimum"] = 1
        props(data)["body_material"]["materialize"] = False
        for name in ("p1", "p2", "p3", "p4"):
            props(data)[name] = {"description": "A new property.", "range": "string"}

    facts = ImpactFacts(value_counts={TAG: 2, SIZE: 3})
    r = report(edit, facts)
    order = [e.section for e in r.entries]
    sections = ["records", "columns", "views", "mappings", "reports", "mcp_schemas"]
    assert order == sorted(order, key=sections.index)
    assert [e.target for e in r.entries if e.section == "records"] == sorted([TAG, SIZE])
    assert list(r.counts) == [s for s in sections if s in r.counts]
    assert sum(r.counts.values()) == len(r.entries)
    assert list(r.changed_paths) == sorted(r.changed_paths)


def test_the_report_is_deterministic_and_its_digest_follows_its_content() -> None:
    facts = ImpactFacts(value_counts={TAG: 2})

    def remove(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]

    first, second = report(remove, facts), report(remove, facts)
    assert first == second and first.digest == second.digest and len(first.digest) == 64
    assert report(remove, ImpactFacts(value_counts={TAG: 3})).digest != first.digest


def test_a_long_report_is_cut_at_the_limit_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(impact_module, "MAX_ENTRIES", 2)

    def edit(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]
        props(data)["size_in"]["minimum"] = 1
        props(data)["manufacturer"]["default"] = "Acme"

    r = report(
        edit, ImpactFacts(value_counts={TAG: 1, SIZE: 1, "psets.valve_data.manufacturer": 1})
    )
    assert len(r.entries) == 2 and r.truncated
    assert r.counts == {"records": 2}
    assert MAX_ENTRIES == 500
    assert not report(edit).truncated


def test_a_report_with_exactly_the_limit_is_not_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    def edit(data: dict[str, Any]) -> None:
        del props(data)["tag_no"]
        props(data)["size_in"]["minimum"] = 1

    facts = ImpactFacts(value_counts={TAG: 1, SIZE: 1})
    full = report(edit, facts)
    assert len(full.entries) > 2
    monkeypatch.setattr(impact_module, "MAX_ENTRIES", len(full.entries))
    exact = report(edit, facts)
    assert exact.entries == full.entries and not exact.truncated
