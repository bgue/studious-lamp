"""The package validator: layout, lock, LinkML lint, compile, form, workflow, settings, examples.

Every case starts from the committed example (``schema/fixtures/types``), changes one thing, and
checks the issue the validator reports. Cases that are about the *files* rewrite ``type.lock`` so
the lock does not hide the issue under test.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from tl_core.extypes.lock import write_lock
from tl_core.extypes.types import TypeIssue, TypeRegistration
from tl_core.extypes.validate import describe_package, read_settings, validate_package
from tl_core.schema_provider import DirectorySchemaProvider

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types"


class Pkg:
    """A scratch copy of an example package at ``<root>/co.acme/<Name>/<version>``."""

    def __init__(self, tmp_path: Path, name: str = "LiftPlan", version: str = "1.0.0") -> None:
        self.root = tmp_path / "types"
        self.path = self.root / "co.acme" / name / version
        shutil.copytree(FIXTURES / "co.acme" / name / "1.0.0", self.path)
        self.provider = DirectorySchemaProvider()

    def edit(self, relative: str, old: str, new: str, *, relock: bool = True) -> None:
        file = self.path / relative
        text = file.read_text(encoding="utf-8")
        assert old in text, f"{old!r} not in {relative}"
        file.write_text(text.replace(old, new), encoding="utf-8")
        if relock:
            write_lock(self.path)

    def write(self, relative: str, text: str, *, relock: bool = True) -> None:
        file = self.path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        if relock:
            write_lock(self.path)

    def validate(self) -> tuple[TypeRegistration | None, list[TypeIssue]]:
        return validate_package(self.path, provider=self.provider, root=self.root)

    def issues(self) -> list[tuple[str, str | None]]:
        registration, issues = self.validate()
        assert registration is None, "expected the package to be refused"
        return [(i.kind, i.path) for i in issues]

    def details(self) -> str:
        return "\n".join(i.detail for i in self.validate()[1])


@pytest.fixture
def lift(tmp_path: Path) -> Pkg:
    return Pkg(tmp_path)


@pytest.fixture
def observation(tmp_path: Path) -> Pkg:
    return Pkg(tmp_path, "SafetyObservation")


# --- the examples are valid -----------------------------------------------------------------------


def test_the_object_backed_example_is_valid(lift: Pkg) -> None:
    registration, issues = lift.validate()
    assert issues == []
    assert registration is not None
    assert registration.type_ref == "co.acme.LiftPlan@1.0.0"
    assert registration.storage_mode == "object-backed"
    assert registration.status == "active"
    assert registration.index_fields == ["lift_date", "crane", "load_tonnes", "risk_class"]
    assert registration.owner == ""  # sync fills the owner in
    assert registration.location_uri == lift.path.resolve().as_uri()
    assert len(registration.content_hash) == 64 and len(registration.schema_hash) == 64


def test_the_managed_example_is_valid(observation: Pkg) -> None:
    registration, issues = observation.validate()
    assert issues == [] and registration is not None
    assert registration.storage_mode == "managed"
    assert registration.index_fields == ["observed_on", "category", "severity", "location"]


def test_the_content_hash_covers_the_files_and_the_schema_hash_ignores_the_version(
    tmp_path: Path,
) -> None:
    first = Pkg(tmp_path / "a")
    second = Pkg(tmp_path / "b", version="1.1.0")
    one, _ = first.validate()
    two, _ = second.validate()
    assert one is not None and two is not None
    assert one.content_hash == two.content_hash  # the hash covers the files, not the path
    assert one.schema_hash == two.schema_hash  # same class, so bodies stay valid across them
    assert describe_package(first.path, first.root).content_hash == one.content_hash


# --- layout -----------------------------------------------------------------------------


def test_a_missing_type_yaml_is_a_layout_issue(lift: Pkg) -> None:
    (lift.path / "type.yaml").unlink()
    write_lock(lift.path)
    assert ("layout", "type.yaml") in lift.issues()


def test_a_bad_version_directory_is_a_layout_issue(tmp_path: Path) -> None:
    pkg = Pkg(tmp_path)
    moved = pkg.root / "co.acme" / "LiftPlan" / "v1"
    pkg.path.rename(moved)
    pkg.path = moved
    kinds = pkg.issues()
    assert ("layout", None) in kinds
    assert "MAJOR.MINOR.PATCH" in pkg.details()


def test_a_package_at_the_wrong_depth_is_a_layout_issue(tmp_path: Path) -> None:
    pkg = Pkg(tmp_path)
    shallow = pkg.root / "LiftPlan"
    shutil.copytree(pkg.path, shallow)
    registration, issues = validate_package(shallow, provider=pkg.provider, root=pkg.root)
    assert registration is None
    assert any(i.kind == "layout" and "levels" in i.detail for i in issues)
    assert describe_package(shallow, pkg.root).type_ref == "invalid:LiftPlan"


def test_a_symbolic_link_in_a_package_is_a_layout_issue(lift: Pkg, tmp_path: Path) -> None:
    secret = tmp_path / "secret.yaml"
    secret.write_text("x: 1\n")
    os.symlink(secret, lift.path / "examples" / "linked.json")
    assert ("layout", "examples/linked.json") in lift.issues()


# --- the lock -----------------------------------------------------------------------------------


def test_a_missing_lock_is_a_lock_issue(lift: Pkg) -> None:
    (lift.path / "type.lock").unlink()
    assert ("lock", "type.lock") in lift.issues()


def test_an_edited_file_under_a_stale_lock_is_a_lock_issue(lift: Pkg) -> None:
    lift.edit("README.md", "LiftPlan", "LiftPlan!", relock=False)
    assert lift.issues() == [("lock", "README.md")]


# --- LinkML lint and compile ---------------------------------------------------------------------


def test_a_lint_error_is_a_lint_issue(lift: Pkg) -> None:
    lift.edit("type.yaml", "  LiftPlan:\n    is_a", "  liftPlan:\n    is_a")
    kinds = [kind for kind, _ in lift.issues()]
    assert "lint" in kinds


def test_a_class_that_is_not_an_extension_record_does_not_compile(lift: Pkg) -> None:
    lift.edit("type.yaml", "is_a: ExtensionRecord", "is_a: RecordEnvelope")
    assert ("compile", "type.yaml") in lift.issues()
    assert "ExtensionRecord" in lift.details()


def test_the_class_must_be_the_one_the_directory_names(lift: Pkg) -> None:
    lift.edit("type.yaml", "  LiftPlan:\n    is_a", "  OtherPlan:\n    is_a")
    assert "the class LiftPlan named by the directory is not declared" in lift.details()


def test_a_missing_import_of_the_base_class_is_refused(lift: Pkg) -> None:
    lift.edit("type.yaml", "  - throughline/core/extension\n", "")
    assert "imports must include" in lift.details()


def test_a_slot_that_shadows_an_envelope_field_is_refused(lift: Pkg) -> None:
    lift.edit("type.yaml", "      method_statement:", "      title:")
    lift.edit("form.yaml", "method_statement", "title")  # keep form.yaml consistent
    assert "field of the record envelope" in lift.details()


def test_a_slot_name_must_be_lower_snake_case(lift: Pkg) -> None:
    lift.edit("type.yaml", "      exclusion_zone_m:", "      ExclusionZone:")
    lift.edit("form.yaml", "exclusion_zone_m", "ExclusionZone")
    assert "lower snake case" in lift.details()


def test_a_range_that_is_a_class_is_refused(lift: Pkg) -> None:
    lift.edit(
        "type.yaml",
        "      crane:\n        required: true",
        "      crane:\n        range: LiftPlan\n        required: true",
    )
    assert "range 'LiftPlan' is not supported" in lift.details()


def test_a_version_in_type_yaml_must_match_the_directory(observation: Pkg) -> None:
    observation.edit("type.yaml", "version: 1.0.0", "version: 2.0.0")
    assert "differs from the directory version" in observation.details()


def test_directory_backed_storage_is_unsupported_in_v0(lift: Pkg) -> None:
    lift.edit("type.yaml", "tl:storage_mode: object-backed", "tl:storage_mode: directory-backed")
    assert ("unsupported", "type.yaml") in lift.issues()


def test_an_unknown_storage_mode_is_a_compile_issue(lift: Pkg) -> None:
    lift.edit("type.yaml", "tl:storage_mode: object-backed", "tl:storage_mode: cloud")
    assert ("compile", "type.yaml") in lift.issues()


def test_a_pset_name_that_belongs_to_another_package_is_a_conflict(tmp_path: Path) -> None:
    from tl_schema.compose import compose
    from tl_schema.packages import PackageDoc, PropertyDef, PsetDef

    pkg = Pkg(tmp_path)
    company = PackageDoc(
        package="co.other.base",
        version="1.0.0",
        kind="company",
        description="A company package that already owns the pset name.",
        psets={
            "co_acme_lift_plan": PsetDef(
                description="Taken.", properties={"a": PropertyDef(description="A property.")}
            )
        },
    )

    class Fixed:
        def effective(self, scope: str):  # type: ignore[no-untyped-def]
            return compose([company], scope)

        def scopes(self) -> list[str]:
            return ["company"]

    registration, issues = validate_package(pkg.path, provider=Fixed(), root=pkg.root)
    assert registration is None
    assert [(i.kind, i.path) for i in issues] == [("conflict", "type.yaml")]
    assert "co.other.base" in issues[0].detail


# --- form, workflow, settings, examples ----------------------------------------------------------


def test_form_hints_may_only_name_slots(lift: Pkg) -> None:
    lift.edit("form.yaml", "  crane:\n    label: Crane", "  crain:\n    label: Crane")
    assert ("compile", "form.yaml") in lift.issues()
    assert "crain" in lift.details()


def test_unknown_keys_in_form_yaml_are_refused(lift: Pkg) -> None:
    lift.write("form.yaml", "colour: red\n")
    assert ("compile", "form.yaml") in lift.issues()


def test_a_workflow_for_another_record_type_is_refused(lift: Pkg) -> None:
    lift.edit("workflow.yaml", "record_type: co.acme.LiftPlan", "record_type: core.Record")
    assert ("compile", "workflow.yaml") in lift.issues()
    assert "record_type must be co.acme.LiftPlan" in lift.details()


def test_a_workflow_with_an_unknown_state_is_refused(lift: Pkg) -> None:
    lift.edit("workflow.yaml", "to: Approved", "to: Nowhere")
    assert ("compile", "workflow.yaml") in lift.issues()


def test_a_setting_key_outside_the_namespace_is_refused(lift: Pkg) -> None:
    lift.edit("settings.yaml", "co.acme.lift_plan.max_load_tonnes", "feed.reactions.enabled")
    assert ("settings", "settings.yaml") in lift.issues()
    assert "must start with co.acme." in lift.details()


def test_a_secret_setting_is_refused(lift: Pkg) -> None:
    lift.edit(
        "settings.yaml", "    lockable: true\n", "    lockable: true\n    sensitivity: secret\n"
    )
    assert "secret settings are not available" in lift.details()


def test_a_setting_owned_by_someone_else_is_refused(lift: Pkg) -> None:
    lift.edit("settings.yaml", "owner: co.acme.LiftPlan", "owner: platform")
    assert "owner must be co.acme.LiftPlan" in lift.details()


def test_an_invalid_setting_definition_is_refused(lift: Pkg) -> None:
    lift.edit("settings.yaml", "type: decimal", "type: banana")
    assert ("settings", "settings.yaml") in lift.issues()


def test_read_settings_returns_the_definitions_with_the_type_as_owner(lift: Pkg) -> None:
    from tl_core.extypes.names import parse_type_ref

    definitions, issues = read_settings(lift.path, parse_type_ref("co.acme.LiftPlan@1.0.0"))
    assert issues == []
    assert [d.key for d in definitions] == ["co.acme.lift_plan.max_load_tonnes"]
    assert definitions[0].owner == "co.acme.LiftPlan"


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"crane": "CR-12"}, "'lift_date' is a required property"),
        (
            {"crane": "CR-12", "lift_date": "2026-11-03", "load_tonnes": 5, "risk_class": "huge"},
            "risk_class",
        ),
        (
            {"crane": "crane 12", "lift_date": "2026-11-03", "load_tonnes": 5, "risk_class": "low"},
            "crane",
        ),
        (
            {"crane": "CR-12", "lift_date": "03/11/2026", "load_tonnes": 5, "risk_class": "low"},
            "lift_date",
        ),
        (
            {"crane": "CR-1", "lift_date": "2026-11-03", "load_tonnes": -1, "risk_class": "low"},
            "load_tonnes",
        ),
        (
            {
                "crane": "CR-1",
                "lift_date": "2026-11-03",
                "load_tonnes": 1,
                "risk_class": "low",
                "x": 1,
            },
            "'x' was unexpected",
        ),
    ],
)
def test_an_example_that_does_not_validate_is_an_example_issue(
    lift: Pkg, body: dict[str, object], fragment: str
) -> None:
    lift.write("examples/bad.json", json.dumps(body))
    registration, issues = lift.validate()
    assert registration is None
    assert {(i.kind, i.path) for i in issues} == {("example", "examples/bad.json")}
    assert fragment in "\n".join(i.detail for i in issues)


def test_an_unreadable_example_is_an_example_issue(lift: Pkg) -> None:
    lift.write("examples/broken.json", "{not json")
    assert ("example", "examples/broken.json") in lift.issues()


def test_a_yaml_example_is_checked_too(lift: Pkg) -> None:
    lift.write("examples/plan.yaml", "crane: CR-9\nlift_date: 2026-11-03\n")
    # a YAML date is not a string: the body schema wants text
    assert ("example", "examples/plan.yaml") in lift.issues()


def test_every_issue_is_reported_not_just_the_first(lift: Pkg) -> None:
    lift.write("examples/bad.json", "{}")
    lift.edit("workflow.yaml", "to: Approved", "to: Nowhere")
    lift.edit("settings.yaml", "co.acme.lift_plan.max_load_tonnes", "x.y")
    kinds = {kind for kind, _ in lift.issues()}
    assert kinds == {"example", "compile", "settings"}


def test_validation_writes_nothing(lift: Pkg) -> None:
    before = sorted(p.relative_to(lift.path).as_posix() for p in lift.path.rglob("*"))
    lift.validate()
    after = sorted(p.relative_to(lift.path).as_posix() for p in lift.path.rglob("*"))
    assert before == after
