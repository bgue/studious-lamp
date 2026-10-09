"""Lint rules over package documents (P0-I2-T08a). Copied into place by the ticket."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tl_schema.lint import LintIssue, lint_documents
from tl_schema.packages import PackageDoc

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]


def rules(issues: list[LintIssue]) -> list[tuple[str, str]]:
    return [(i.rule, i.path) for i in issues]


def valve(raw: Raw) -> dict[str, Any]:
    props: dict[str, Any] = raw["co.acme.engineering"]["psets"]["valve_data"]["properties"]
    return props


def test_the_fixtures_have_exactly_one_warning(build_docs: Build) -> None:
    issues = lint_documents(build_docs())
    assert issues == [
        LintIssue(
            severity="warning",
            rule="L004",
            package="co.acme.engineering@3.2.0",
            path="psets.valve_data.properties.body_material",
            message="promoted property has no exact_mappings",
        )
    ]


def test_l001_short_descriptions(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        valve(raw)["tag_no"]["description"] = "Tag."
        raw["co.acme.engineering"]["psets"]["safety_data"]["description"] = "Safety"
        raw["co.acme.engineering"]["code_lists"]["FailAction"]["description"] = "Fail"
        raw["x.P123"]["extends"][0]["custom"]["fat_witness_by"]["description"] = "FAT"

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L001"]
    assert [(i.package, i.path) for i in found] == [
        ("co.acme.engineering@3.2.0", "code_lists.FailAction"),
        ("co.acme.engineering@3.2.0", "psets.safety_data"),
        ("co.acme.engineering@3.2.0", "psets.valve_data.properties.tag_no"),
        ("x.P123@1.4.0", "extends.valve_data.custom.fat_witness_by"),
    ]
    assert all(i.severity == "warning" for i in found)


def test_l002_decimal_without_a_unit(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        del valve(raw)["size_in"]["unit"]

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L002"]
    assert rules(found) == [("L002", "psets.valve_data.properties.size_in")]
    assert found[0].message == "decimal property has no unit"


def test_l003_orphan_code_list(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["code_lists"]["Unused"] = {
            "description": "A list nothing refers to.",
            "values": [{"code": "A", "label": "A"}, {"code": "B", "label": "B"}],
        }

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L003"]
    assert rules(found) == [("L003", "code_lists.Unused")]
    assert found[0].package == "co.acme.engineering@3.2.0"


def test_a_list_used_only_by_an_extension_is_not_an_orphan(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["code_lists"]["Party"] = {
            "description": "Parties that can witness tests.",
            "values": [{"code": "CLIENT", "label": "Client"}, {"code": "TPI", "label": "TPI"}],
        }
        raw["x.P123"]["extends"][0]["custom"]["fat_witness_by"]["range"] = "Party"

    assert [i for i in lint_documents(build_docs(mutate)) if i.rule == "L003"] == []


def test_l004_promoted_without_mappings(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        valve(raw)["body_material"]["exact_mappings"] = ["cfihos:CFIHOS-40000999"]

    assert lint_documents(build_docs(mutate)) == []


def test_l005_similar_property_names(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["extends"][0]["custom"]["fat_witness"] = {
            "description": "Same thing under a near-identical name.",
            "range": "string",
        }
        valve(raw)["sizein"] = {"description": "Size with the underscore removed."}

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L005"]
    assert [(i.package, i.path) for i in found] == [
        ("co.acme.engineering@3.2.0", "psets.valve_data.properties.sizein"),
        ("x.P123@1.4.0", "extends.valve_data.custom.fat_witness_by"),
    ]
    # The issue sits on the later of the pair (sorted by package, then path) and names the earlier.
    assert "size_in" in found[0].message
    assert "fat_witness" in found[1].message


def test_same_name_in_two_psets_is_not_similar(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["safety_data"]["properties"]["manufacturer"] = {
            "description": "Manufacturer of the safety device."
        }

    assert [i for i in lint_documents(build_docs(mutate)) if i.rule == "L005"] == []


def test_l006_tiny_code_list(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["code_lists"]["FailAction"]["values"] = [
            {"code": "FC", "label": "Fail closed"}
        ]

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L006"]
    assert rules(found) == [("L006", "code_lists.FailAction")]


def test_l007_bad_record_type(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["prj.P123"]["psets"]["shutdown_tie_in"]["applies_to"] = ["core.Record", "weld"]

    found = [i for i in lint_documents(build_docs(mutate)) if i.rule == "L007"]
    assert len(found) == 1
    assert found[0].severity == "error"
    assert found[0].package == "prj.P123@1.0.0"
    assert found[0].path == "psets.shutdown_tie_in"
    assert "weld" in found[0].message


def test_issues_are_sorted_by_package_path_rule(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        valve(raw)["tag_no"]["description"] = "Tag."
        del valve(raw)["size_in"]["unit"]

    issues = lint_documents(build_docs(mutate))
    keys = [(i.package, i.path, i.rule) for i in issues]
    assert keys == sorted(keys)
    assert len(issues) >= 3
