"""The plain text of the schema review (P1-I8-T04b). Provided; do not edit."""

from __future__ import annotations

from fakes_schemareg import make_package
from tl_mod_schemareg.impact_types import ImpactEntry, ImpactReport, empty_report
from tl_mod_schemareg.views import SampleExample, SampleTestView
from tl_schema.classify import Change, build_report
from tl_tui.schema_review_text import (
    MAX_LINES,
    NEXT_STEPS,
    classification_lines,
    impact_lines,
    next_step,
    sample_lines,
    title_line,
)


def test_the_title_and_the_next_step_follow_the_state() -> None:
    detail = make_package("co.acme.engineering", "3.3.0", "InReview", worst_class="constraining")
    assert title_line(detail) == "Engineering, version 3.3.0  InReview  class constraining"
    assert title_line(make_package()) == "Engineering, version 3.3.0  Draft  class -"
    assert title_line(detail, technical=True) == (
        "co.acme.engineering@3.3.0  InReview  class constraining"
    )
    assert title_line(make_package(), technical=True) == "co.acme.engineering@3.3.0  Draft  class -"
    assert next_step("Draft") == "Next: analyse (a), then submit (s)."
    assert next_step("InReview") == "Next: approve (y) or ask for changes (c)."
    assert next_step("Approved") == "Next: publish (p)."
    assert set(NEXT_STEPS) == {
        "Draft",
        "InReview",
        "Approved",
        "Published",
        "Deprecated",
        "Retired",
    }
    assert next_step("Odd") == "State Odd."


def test_a_version_not_analysed_says_which_key_makes_the_report() -> None:
    assert classification_lines(make_package()) == ["Not analysed: press a to analyse."]
    assert impact_lines(None) == ["No impact report: press a to analyse."]
    assert sample_lines(None) == ["Not run: press t to test on a sample of records."]


def test_the_classification_names_the_worst_class_and_each_change() -> None:
    report = build_report(
        "co.acme.engineering@3.2.0",
        "co.acme.engineering@3.3.0",
        [
            Change(cls="additive", code="property_added", path="psets.a.b", detail="b is new."),
            Change(cls="constraining", code="required", path="psets.a.c", detail="c is required."),
        ],
    )
    detail = make_package(classification=report, analysed=True)
    assert classification_lines(detail) == [
        "Worst constraining  auto-adoptable no  blocks submit no",
        "Base Engineering, version 3.2.0",
        "additive  A: b  b is new.",
        "constraining  A: c  c is required.",
    ]
    assert classification_lines(detail, technical=True) == [
        "Worst constraining  auto-adoptable no  blocks submit no",
        "Base co.acme.engineering@3.2.0",
        "additive  psets.a.b  b is new.",
        "constraining  psets.a.c  c is required.",
    ]
    first = build_report(None, "x@1.0.0", [])
    assert classification_lines(make_package(classification=first))[:2] == [
        "Worst additive  auto-adoptable yes  blocks submit no",
        "Base -",
    ]
    assert classification_lines(make_package(classification=first), technical=True)[:2] == [
        "Worst additive  auto-adoptable yes  blocks submit no",
        "Base -",
    ]


def test_a_long_list_of_changes_is_cut_with_a_count_of_the_rest() -> None:
    changes = [
        Change(cls="additive", code="property_added", path=f"psets.a.p{n:03}", detail="New.")
        for n in range(MAX_LINES + 5)
    ]
    detail = make_package(classification=build_report(None, "x@1.0.0", changes))
    lines = classification_lines(detail)
    assert len(lines) == 2 + MAX_LINES + 1
    assert lines[-1] == "... 5 more" and lines[2] == "additive  A: p000  New."
    technical = classification_lines(detail, technical=True)
    assert technical[2] == "additive  psets.a.p000  New."


def test_the_impact_names_its_digest_counts_and_entries() -> None:
    entry = ImpactEntry(
        section="columns",
        target="cur_valve_data.size_in",
        change="column_added",
        count=None,
        detail="A column is added.",
    )
    other = ImpactEntry(
        section="records", target="psets.valve_data.size_in", change="property_removed",
        count=12, detail="12 records hold a value.",
    )  # fmt: skip
    report = ImpactReport(
        scope="project:P123", old_hash="a" * 64, new_hash="b" * 64, changed_paths=("p",),
        entries=(other, entry), counts={"records": 1, "columns": 1}, truncated=True,
    )  # fmt: skip
    assert impact_lines(report) == [
        "Scope project:P123",
        "Counts records 1, columns 1",
        "records  Valve data: size in  property_removed  12  12 records hold a value.",
        "columns  cur_valve_data.size_in  column_added  -  A column is added.",
        "(report cut)",
    ]
    assert impact_lines(report, technical=True) == [
        "Scope project:P123",
        f"Digest {report.digest}",
        "Counts records 1, columns 1",
        "records  psets.valve_data.size_in  property_removed  12  12 records hold a value.",
        "columns  cur_valve_data.size_in  column_added  -  A column is added.",
        "(report cut)",
    ]
    quiet = impact_lines(empty_report("company", None, "c" * 64))
    assert quiet[0] == "Scope company" and quiet[1] == "Counts -" and len(quiet) == 2
    quiet_technical = impact_lines(empty_report("company", None, "c" * 64), technical=True)
    assert quiet_technical[0] == "Scope company" and quiet_technical[2] == "Counts -"
    assert len(quiet_technical) == 3


def test_the_sample_test_counts_and_lists_examples() -> None:
    example = SampleExample(
        key="V-101", path="psets.valve_data.size_in", rule="required", message="Missing."
    )
    view = SampleTestView(
        package="co.acme.engineering@3.3.0",
        scope="company",
        sample=1000,
        checked=40,
        newly_nonconformant=2,
        newly_warning=1,
        fixed=3,
        examples=[example],
    )
    assert sample_lines(view) == [
        "Tested Engineering, version 3.3.0  scope company  sample 1000  checked 40",
        "Newly nonconformant 2  newly warning 1  fixed 3",
        "V-101  Valve data: size in  required  Missing.",
    ]
    assert sample_lines(view, technical=True) == [
        "Tested co.acme.engineering@3.3.0  scope company  sample 1000  checked 40",
        "Newly nonconformant 2  newly warning 1  fixed 3",
        "V-101  psets.valve_data.size_in  required  Missing.",
    ]


def test_record_type_keys_and_paths_in_a_service_line_read_in_words() -> None:
    from tl_tui.schema_review_text import plain_message

    text = "psets.valve_data.size_in on core.Record in co.acme.engineering@4.0.0"
    assert plain_message(text) == "Valve data: size in on Record in Engineering, version 4.0.0"
    assert plain_message(text, technical=True) == text
