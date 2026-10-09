"""Package loading and adoption (P0-I2-T01). Copied into place by the ticket; do not edit."""

from __future__ import annotations

import copy
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_schema.packages import PackageDoc
from tl_schema.registry import (
    DEFAULT_SCHEMA_DIR,
    PackageError,
    PackageRegistry,
    default_schema_dir,
    load_package,
    parse_package,
)

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]

COMPANY_FILE = "co.acme.engineering@3.2.0.yaml"


def registry_of(build_docs: Build, mutate: Callable[[Raw], None] | None = None) -> PackageRegistry:
    return PackageRegistry(build_docs(mutate))


def keys(docs: list[PackageDoc]) -> list[str]:
    return [d.key() for d in docs]


# --- parsing and loading -----------------------------------------------------------------------


def test_parse_package_reads_a_fixture(fixture_dir: Path) -> None:
    doc = parse_package((fixture_dir / COMPANY_FILE).read_text(encoding="utf-8"), source="inline")
    assert (doc.package, doc.version, doc.kind) == ("co.acme.engineering", "3.2.0", "company")
    assert "valve_data" in doc.psets


def test_parse_package_reports_bad_yaml_with_the_source() -> None:
    with pytest.raises(PackageError) as caught:
        parse_package("package: [unclosed", source="bad.yaml")
    assert str(caught.value).startswith("bad.yaml")


def test_parse_package_rejects_a_non_mapping() -> None:
    with pytest.raises(PackageError) as caught:
        parse_package("- just\n- a list\n", source="list.yaml")
    assert str(caught.value).startswith("list.yaml")


def test_parse_package_lists_validation_errors(raw_packages: Raw) -> None:
    data = raw_packages["x.P123"]
    data["version"] = "1.4"
    data["surprise"] = True
    with pytest.raises(PackageError) as caught:
        parse_package(yaml.safe_dump(data), source="x.yaml")
    message = str(caught.value)
    assert message.startswith("x.yaml")
    assert "version" in message
    assert "surprise" in message


def test_load_package_reads_a_file(fixture_dir: Path) -> None:
    assert load_package(fixture_dir / COMPANY_FILE).key() == "co.acme.engineering@3.2.0"


def test_load_package_requires_the_canonical_file_name(tmp_path: Path, fixture_dir: Path) -> None:
    wrong = tmp_path / "company.yaml"
    shutil.copy(fixture_dir / COMPANY_FILE, wrong)
    with pytest.raises(PackageError) as caught:
        load_package(wrong)
    assert "co.acme.engineering@3.2.0.yaml" in str(caught.value)


# --- the registry ------------------------------------------------------------------------------


def test_from_directory_loads_the_fixtures(fixture_dir: Path) -> None:
    registry = PackageRegistry.from_directory(fixture_dir)
    assert registry.names() == ["co.acme.engineering", "prj.P123", "x.P123"]
    assert registry.versions("x.P123") == ["1.4.0"]
    assert registry.get("prj.P123", "1.0.0").kind == "project"
    assert registry.latest("co.acme.engineering").version == "3.2.0"
    assert registry.projects() == ["P123"]
    registry.check()


def test_from_directory_errors(tmp_path: Path) -> None:
    with pytest.raises(PackageError):
        PackageRegistry.from_directory(tmp_path / "missing")
    empty = PackageRegistry.from_directory(tmp_path)
    assert empty.names() == []
    assert empty.projects() == []
    (tmp_path / "broken@1.0.0.yaml").write_text("package: [", encoding="utf-8")
    with pytest.raises(PackageError):
        PackageRegistry.from_directory(tmp_path)


def test_add_rejects_the_same_version_twice(build_docs: Build) -> None:
    docs = build_docs()
    registry = PackageRegistry(docs)
    with pytest.raises(PackageError):
        registry.add(docs[0])
    with pytest.raises(PackageError):
        PackageRegistry([docs[0], docs[0]])


def test_get_and_latest_report_unknown_names(build_docs: Build) -> None:
    registry = registry_of(build_docs)
    assert registry.versions("nope") == []
    with pytest.raises(PackageError):
        registry.get("co.acme.engineering", "9.9.9")
    with pytest.raises(PackageError):
        registry.latest("nope")


def test_versions_sort_by_number_not_text(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        for version in ("3.10.0", "3.9.1"):
            extra = copy.deepcopy(raw["co.acme.engineering"])
            extra["version"] = version
            raw[f"co.acme.engineering@{version}"] = extra

    registry = registry_of(build_docs, mutate)
    assert registry.versions("co.acme.engineering") == ["3.2.0", "3.9.1", "3.10.0"]
    assert registry.latest("co.acme.engineering").version == "3.10.0"


# --- adoption ----------------------------------------------------------------------------------


def test_company_scope_adopts_the_latest_company_packages(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        newer = copy.deepcopy(raw["co.acme.engineering"])
        newer["version"] = "3.3.0"
        raw["co.acme.engineering@3.3.0"] = newer

    adopted = registry_of(build_docs, mutate).adopted("company")
    assert keys(adopted) == ["co.acme.engineering@3.3.0"]


def test_project_scope_adopts_company_extension_then_project_documents(
    build_docs: Build,
) -> None:
    adopted = registry_of(build_docs).adopted("project:P123")
    assert keys(adopted) == ["co.acme.engineering@3.2.0", "x.P123@1.4.0", "prj.P123@1.0.0"]


def test_a_pin_beats_a_newer_company_version(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        newer = copy.deepcopy(raw["co.acme.engineering"])
        newer["version"] = "3.3.0"
        raw["co.acme.engineering@3.3.0"] = newer

    registry = registry_of(build_docs, mutate)
    assert keys(registry.adopted("project:P123"))[0] == "co.acme.engineering@3.2.0"
    assert keys(registry.adopted("company")) == ["co.acme.engineering@3.3.0"]


def test_unpinned_company_packages_come_in_at_their_latest(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        other = copy.deepcopy(raw["co.acme.engineering"])
        other["package"] = "co.acme.piping"
        other["version"] = "1.0.0"
        other["psets"] = {}
        other["code_lists"] = {}
        raw["co.acme.piping"] = other

    adopted = registry_of(build_docs, mutate).adopted("project:P123")
    assert keys(adopted) == [
        "co.acme.engineering@3.2.0",
        "co.acme.piping@1.0.0",
        "x.P123@1.4.0",
        "prj.P123@1.0.0",
    ]


def test_a_project_without_packages_adopts_the_company_set(build_docs: Build) -> None:
    adopted = registry_of(build_docs).adopted("project:P999")
    assert keys(adopted) == ["co.acme.engineering@3.2.0"]


def test_the_highest_project_package_version_wins(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        newer = copy.deepcopy(raw["x.P123"])
        newer["version"] = "1.5.0"
        raw["x.P123@1.5.0"] = newer

    adopted = registry_of(build_docs, mutate).adopted("project:P123")
    assert "x.P123@1.5.0" in keys(adopted)
    assert "x.P123@1.4.0" not in keys(adopted)


def test_other_projects_packages_are_not_adopted(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        other = copy.deepcopy(raw["x.P123"])
        other["package"] = "x.P456"
        other["project"] = "P456"
        raw["x.P456"] = other

    registry = registry_of(build_docs, mutate)
    assert registry.projects() == ["P123", "P456"]
    assert "x.P456@1.4.0" not in keys(registry.adopted("project:P123"))
    assert "x.P456@1.4.0" in keys(registry.adopted("project:P456"))


def test_conflicting_pins_are_an_error(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        newer = copy.deepcopy(raw["co.acme.engineering"])
        newer["version"] = "3.3.0"
        raw["co.acme.engineering@3.3.0"] = newer
        raw["prj.P123"]["depends"] = {"co.acme.engineering": "3.3.0"}

    registry = registry_of(build_docs, mutate)
    with pytest.raises(PackageError):
        registry.adopted("project:P123")


@pytest.mark.parametrize("scope", ["P123", "project:", "projects:P123", "Company", ""])
def test_a_bad_scope_is_a_value_error(build_docs: Build, scope: str) -> None:
    with pytest.raises(ValueError):
        registry_of(build_docs).adopted(scope)


# --- cross-document checks ---------------------------------------------------------------------


def test_check_passes_for_consistent_documents(build_docs: Build) -> None:
    registry_of(build_docs).check()


def test_check_lists_every_problem(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["depends"] = {"co.acme.engineering": "9.9.9", "prj.P123": "1.0.0"}
        raw["x.P123"]["extends"][0]["ref"] = "co.acme.engineering@3.2.0#no_such_pset"

    with pytest.raises(PackageError) as caught:
        registry_of(build_docs, mutate).check()
    message = str(caught.value)
    assert "9.9.9" in message
    assert "prj.P123@1.0.0" in message
    assert "no_such_pset" in message


# --- fingerprint and defaults ------------------------------------------------------------------


def test_fingerprint_is_stable_and_sensitive(build_docs: Build) -> None:
    docs = build_docs()
    first = PackageRegistry(docs).fingerprint()
    assert len(first) == 64
    assert PackageRegistry(list(reversed(docs))).fingerprint() == first

    def mutate(raw: Raw) -> None:
        raw["x.P123"]["extends"][0]["labels"] = {"size_in": "NPS"}

    assert registry_of(build_docs, mutate).fingerprint() != first


def test_default_schema_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    assert default_schema_dir() == DEFAULT_SCHEMA_DIR
    assert DEFAULT_SCHEMA_DIR.name == "fixtures"
    monkeypatch.setenv("TL_SCHEMA_DIR", "")
    assert default_schema_dir() == DEFAULT_SCHEMA_DIR
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    assert default_schema_dir() == tmp_path
