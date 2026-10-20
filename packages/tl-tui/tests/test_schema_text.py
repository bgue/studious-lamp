"""The plain text of the schema workbench (P1-I8-T04a). Provided; do not edit."""

from __future__ import annotations

from fakes_schemareg import make_package
from tl_mod_schemareg.testing import fixture_text
from tl_mod_schemareg.views import LintIssueView
from tl_tui.schema_text import (
    COLUMNS,
    diff_lines,
    header_lines,
    lint_lines,
    property_lines,
    tree_cells,
)


def test_the_versions_of_a_package_read_as_a_tree() -> None:
    rows = [
        make_package("x.P123", "1.4.0", scope="project:P123"),
        make_package("co.acme.engineering", "3.3.0", worst_class="additive", analysed=True),
        make_package("co.acme.engineering", "3.2.0", "Published", worst_class="additive"),
    ]
    assert COLUMNS == ("Package", "Version", "State", "Class", "Scope", "Drafted by")
    assert tree_cells(rows) == [
        ("x.P123", "1.4.0", "Draft", "-", "project:P123", "user:dev"),
        ("co.acme.engineering", "3.3.0", "Draft", "additive", "company", "user:dev"),
        ("", "3.2.0", "Published", "additive (stale)", "company", "user:dev"),
    ]
    assert tree_cells([]) == []


def test_the_header_names_who_did_what() -> None:
    detail = make_package(
        "co.acme.engineering",
        "3.3.0",
        "Approved",
        worst_class="constraining",
        analysed=True,
        submitted_by="user:kim",
        approved_by="user:boss",
        changelog="Adds seat leakage.",
    )
    assert header_lines(detail) == [
        "co.acme.engineering@3.3.0  Approved",
        "Kind company  Scope company  Project -",
        "Drafted by user:dev  Submitted by user:kim  Approved by user:boss",
        "Class constraining  Analysed yes  Published -",
        "Changelog Adds seat leakage.",
    ]


def test_a_company_package_lists_its_code_lists_psets_and_properties() -> None:
    lines = property_lines(fixture_text("co.acme.engineering"))
    assert lines[:8] == [
        "list MaterialCode  extensible  5 values",
        "list FailAction  closed  3 values",
        "pset valve_data  required  mandatory  applies to core.Record",
        "  size_in  decimal  required  req Design,Installed  -",
        "  body_material  MaterialCode  required  req -  extensible",
        "  fail_action  FailAction  locked  req -  closed",
        "  tag_no  string  advisory  req -  -",
        "  manufacturer  string  advisory  req *  -",
    ]
    assert (
        "pset provenance  advisory  mandatory  applies to engineering.Tag, documents.Document"
        in lines
    )
    assert len(lines) == 13


def test_an_extension_lists_what_it_tightens_adds_and_customises() -> None:
    assert property_lines(fixture_text("x.P123")) == [
        "extends co.acme.engineering@3.2.0#valve_data",
        "  tighten body_material  required_in_states=Design",
        "  add MaterialCode  SS316L-NACE  -> SS316L",
        "  custom x.fat_witness_by  string",
        "  custom x.tie_in_window  string",
    ]


def test_a_project_package_lists_its_own_psets() -> None:
    assert property_lines(fixture_text("prj.P123")) == [
        "pset shutdown_tie_in  advisory  optional  applies to core.Record",
        "  window  string  advisory  req -  -",
        "  approved  bool  advisory  req -  -",
    ]


def test_a_package_that_does_not_parse_says_so_in_one_line() -> None:
    lines = property_lines("package: [not a package\n")
    assert len(lines) == 1 and lines[0].startswith("! The package does not parse: ")
    assert property_lines("") != [] and property_lines("")[0].startswith("! ")


def test_lint_findings_are_counted_then_listed() -> None:
    issues = [
        LintIssueView(severity="error", rule="L1", path="psets.a", message="No description."),
        LintIssueView(severity="warning", rule="L2", path="psets.b.c", message="Unit missing."),
        LintIssueView(severity="warning", rule="L2", path="psets.b.d", message="Unit missing."),
    ]
    assert lint_lines(issues) == [
        "Lint: 1 errors, 2 warnings",
        "error  L1  psets.a  No description.",
        "warning  L2  psets.b.c  Unit missing.",
        "warning  L2  psets.b.d  Unit missing.",
    ]
    assert lint_lines([]) == ["Lint: 0 errors, 0 warnings"]


def test_the_diff_is_shown_or_the_reason_there_is_none() -> None:
    plain = make_package()
    assert diff_lines(plain) == [
        "Not analysed yet: the diff against the version below is made by analyse."
    ]
    first = plain.model_copy(update={"classification": object()})
    assert diff_lines(first) == ["No base to compare with (first version)."]
    with_diff = plain.model_copy(update={"diff": "--- a\n+++ b\n+size\n"})
    assert diff_lines(with_diff) == ["--- a", "+++ b", "+size"]
    cut = with_diff.model_copy(update={"diff_truncated": True})
    assert diff_lines(cut)[-2:] == ["+size", "(diff cut)"]
