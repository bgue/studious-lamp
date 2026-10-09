"""Conformance evaluator: enforcement levels, required states, waivers, modes (brief 6.3)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from tl_schema.compose import compose
from tl_schema.conformance import evaluate
from tl_schema.effective import EffectiveSchema
from tl_schema.forms import ConformanceReport
from tl_schema.packages import PackageDoc

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]
TODAY = date(2026, 10, 9)
RECORD = "core.Record"


def run(
    schema: EffectiveSchema,
    psets: dict[str, Any],
    *,
    state: str | None = None,
    on: date = TODAY,
) -> ConformanceReport:
    return evaluate(schema, RECORD, psets, state=state, on=on)


def summary(report: ConformanceReport) -> list[tuple[str, str, str]]:
    return [(i.path, i.rule, i.level) for i in report.issues]


def with_conformance(build_docs: Build, settings: dict[str, Any]) -> EffectiveSchema:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["conformance"] = settings

    return compose(build_docs(mutate), "project:P123")


# --- engagement and missing values -------------------------------------------------------------


def test_a_record_without_values_is_ok(effective: EffectiveSchema) -> None:
    report = run(effective, {})
    assert report.status == "ok" and report.issues == []
    assert report.effective_schema_hash == effective.hash


def test_a_missing_advisory_property_is_a_warning(effective: EffectiveSchema) -> None:
    report = run(effective, {"valve_data": {"size_in": 4}})
    assert report.status == "warning"
    assert summary(report) == [("psets.valve_data.manufacturer", "required_in_state", "warning")]
    assert report.issues[0].message == "Manufacturer is required"


def test_a_missing_required_in_state_property_is_nonconformant(effective: EffectiveSchema) -> None:
    psets = {"valve_data": {"manufacturer": "Acme"}}
    assert run(effective, psets).status == "ok"  # no state: state-bound rules do not apply
    report = run(effective, psets, state="Design")
    assert report.status == "nonconformant"
    assert summary(report) == [
        ("psets.valve_data.body_material", "required_in_state", "nonconformant"),
        ("psets.valve_data.size_in", "required_in_state", "nonconformant"),
    ]
    assert report.issues[0].message == "Body material is required in state Design"
    only_installed = run(effective, psets, state="Installed")
    assert summary(only_installed) == [
        ("psets.valve_data.size_in", "required_in_state", "nonconformant")
    ]


def test_a_state_no_rule_names_adds_nothing(effective: EffectiveSchema) -> None:
    assert run(effective, {"valve_data": {"manufacturer": "Acme"}}, state="Closed").status == "ok"


def test_null_means_missing(effective: EffectiveSchema) -> None:
    report = run(effective, {"valve_data": {"size_in": 4, "manufacturer": None}})
    assert summary(report) == [("psets.valve_data.manufacturer", "required_in_state", "warning")]


def test_project_psets_are_checked_once_engaged(effective: EffectiveSchema) -> None:
    ok = run(effective, {"prj": {"shutdown_tie_in": {"approved": True}}})
    assert ok.status == "ok"
    bad = run(effective, {"prj": {"shutdown_tie_in": {"approved": "yes"}}})
    assert summary(bad) == [("psets.prj.shutdown_tie_in.approved", "type", "warning")]


def test_a_required_custom_property(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["extends"][0]["custom"]["fat_witness_by"]["required_in_states"] = ["Design"]

    schema = compose(build_docs(mutate), "project:P123")
    psets = {"valve_data": {"manufacturer": "Acme", "size_in": 4, "body_material": "CS"}}
    report = run(schema, psets, state="Design")
    assert summary(report) == [
        ("psets.valve_data.x.fat_witness_by", "required_in_state", "warning")
    ]


def test_a_mandatory_pset_without_a_class_filter_is_always_engaged(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["valve_data"]["class_filter"] = None

    schema = compose(build_docs(mutate), "project:P123")
    report = run(schema, {})
    assert summary(report) == [("psets.valve_data.manufacturer", "required_in_state", "warning")]


# --- value rules -------------------------------------------------------------------------------


def test_type_range_pattern_and_value_list_rules(effective: EffectiveSchema) -> None:
    psets = {
        "valve_data": {
            "manufacturer": "Acme",
            "size_in": 500,
            "tag_no": "bad tag",
            "body_material": "UNOBTAINIUM",
            "fail_action": "XX",
        }
    }
    report = run(effective, psets)
    assert report.status == "nonconformant"
    assert summary(report) == [
        ("psets.valve_data.body_material", "value_list", "nonconformant"),
        ("psets.valve_data.fail_action", "value_list", "nonconformant"),
        ("psets.valve_data.size_in", "range", "nonconformant"),
        ("psets.valve_data.tag_no", "pattern", "warning"),  # advisory property
    ]
    wrong_type = run(effective, {"valve_data": {"manufacturer": "A", "size_in": "four"}})
    assert summary(wrong_type) == [("psets.valve_data.size_in", "type", "nonconformant")]


def test_a_project_added_code_is_valid(effective: EffectiveSchema) -> None:
    psets = {"valve_data": {"manufacturer": "A", "body_material": "SS316L-NACE"}}
    assert run(effective, psets).status == "ok"


def test_dates_report_a_type_not_a_pattern(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["valve_data"]["properties"]["installed_on"] = {
            "description": "Date the valve was installed.",
            "range": "date",
        }

    schema = compose(build_docs(mutate), "project:P123")
    report = run(schema, {"valve_data": {"manufacturer": "A", "installed_on": "yesterday"}})
    assert summary(report) == [("psets.valve_data.installed_on", "type", "nonconformant")]


def test_unknown_properties_take_the_pset_enforcement(effective: EffectiveSchema) -> None:
    psets = {"valve_data": {"manufacturer": "A", "nope": 1, "x": {"other": 2}}}
    report = run(effective, psets)
    assert summary(report) == [
        ("psets.valve_data.nope", "type", "nonconformant"),
        ("psets.valve_data.x.other", "type", "nonconformant"),
    ]
    project = run(effective, {"prj": {"shutdown_tie_in": {"zzz": 1}}})
    assert summary(project) == [("psets.prj.shutdown_tie_in.zzz", "type", "warning")]


def test_a_custom_section_in_a_locked_pset(build_docs: Build) -> None:
    company = compose([d for d in build_docs() if d.kind == "company"], "company")
    report = run(company, {"safety_data": {"sil_rating": 2, "x": {"a": 1}}})
    assert summary(report) == [("psets.safety_data.x", "locked", "nonconformant")]
    assert "does not allow a custom section" in report.issues[0].message
    missing = run(company, {"safety_data": {"x": {"a": 1}}}, state="Installed")
    assert ("psets.safety_data.sil_rating", "required_in_state", "nonconformant") in summary(
        missing
    )


def test_unknown_root_psets_are_ignored(effective: EffectiveSchema) -> None:
    assert run(effective, {"enrich": {"ai": {"valve_type": "ball"}}, "other": 1}).status == "ok"


def test_issues_are_sorted_and_deterministic(effective: EffectiveSchema) -> None:
    psets = {"valve_data": {"tag_no": "x", "size_in": "y", "nope": 1}}
    first = run(effective, psets, state="Design")
    assert first == run(effective, psets, state="Design")
    paths = [i.path for i in first.issues]
    assert paths == sorted(paths)


# --- project conformance modes -----------------------------------------------------------------

BAD = {"valve_data": {"size_in": 500, "manufacturer": "Acme"}}


def test_strict_is_the_default_mode(effective: EffectiveSchema) -> None:
    assert run(effective, BAD).status == "nonconformant"


def test_lenient_mode_relaxes_required_ness_only(build_docs: Build) -> None:
    schema = with_conformance(build_docs, {"mode": "lenient"})
    missing = run(schema, {"valve_data": {"manufacturer": "Acme"}}, state="Design")
    assert missing.status == "warning"
    assert {(i.rule, i.level) for i in missing.issues} == {("required_in_state", "warning")}
    assert len(missing.issues) == 2  # size_in and body_material, both enforcement required
    strict = run(
        compose(build_docs(), "project:P123"), {"valve_data": {"manufacturer": "A"}}, state="Design"
    )
    assert strict.status == "nonconformant"


def test_lenient_mode_keeps_data_errors_nonconformant(build_docs: Build) -> None:
    schema = with_conformance(build_docs, {"mode": "lenient"})
    report = run(schema, BAD)
    assert report.status == "nonconformant"
    assert summary(report) == [("psets.valve_data.size_in", "range", "nonconformant")]
    company = compose([d for d in build_docs() if d.kind == "company"], "company")
    lenient_company = company.model_copy(
        update={"conformance": schema.conformance, "hash": "lenient-company"}
    )
    locked = run(lenient_company, {"safety_data": {"sil_rating": 2, "x": {"a": 1}}})
    assert summary(locked) == [("psets.safety_data.x", "locked", "nonconformant")]


def test_lenient_mode_ends_on_its_date(build_docs: Build) -> None:
    schema = with_conformance(build_docs, {"mode": "lenient", "lenient_until": "2026-12-31"})
    psets = {"valve_data": {"manufacturer": "A"}}
    assert run(schema, psets, state="Design", on=date(2026, 12, 31)).status == "warning"
    assert run(schema, psets, state="Design", on=date(2027, 1, 1)).status == "nonconformant"


def waiver(path: str, expires: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": path, "reason": "Legacy data.", "approver": "user:dm"}
    if expires is not None:
        entry["expires"] = expires
    return entry


def test_a_waiver_relaxes_one_property(build_docs: Build) -> None:
    schema = with_conformance(
        build_docs,
        {"mode": "strict_with_waivers", "waivers": [waiver("psets.valve_data.size_in")]},
    )
    report = run(schema, BAD)
    assert report.status == "waived" and report.issues == []
    other = run(schema, {"valve_data": {"size_in": 500, "tag_no": "bad"}})
    assert summary(other) == [
        ("psets.valve_data.manufacturer", "required_in_state", "warning"),
        ("psets.valve_data.tag_no", "pattern", "warning"),
    ]
    assert other.status == "warning"


def test_a_waived_missing_property(build_docs: Build) -> None:
    schema = with_conformance(
        build_docs,
        {"mode": "strict_with_waivers", "waivers": [waiver("psets.valve_data.size_in")]},
    )
    report = run(
        schema, {"valve_data": {"manufacturer": "A", "body_material": "CS"}}, state="Design"
    )
    assert report.status == "waived"


def test_an_expired_waiver_no_longer_applies(build_docs: Build) -> None:
    schema = with_conformance(
        build_docs,
        {
            "mode": "strict_with_waivers",
            "waivers": [waiver("psets.valve_data.size_in", "2026-10-09")],
        },
    )
    assert run(schema, BAD, on=date(2026, 10, 9)).status == "waived"
    assert run(schema, BAD, on=date(2026, 10, 10)).status == "nonconformant"


def test_waivers_do_nothing_unless_the_mode_allows_them(build_docs: Build) -> None:
    schema = with_conformance(
        build_docs, {"mode": "strict", "waivers": [waiver("psets.valve_data.size_in")]}
    )
    assert run(schema, BAD).status == "nonconformant"
