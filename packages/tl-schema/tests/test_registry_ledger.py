"""Ledger-published packages beside the directory ones: adoption by pin, waivers (P1-I8-T01)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from tl_schema.compile import SchemaCompileError
from tl_schema.compose import compose
from tl_schema.packages import PackageDoc, WaiverDef
from tl_schema.registry import PackageError, PackageRegistry

Build = Callable[..., list[PackageDoc]]


def _next_company(docs: list[PackageDoc], version: str = "3.3.0") -> PackageDoc:
    base = next(d for d in docs if d.package == "co.acme.engineering")
    raw = copy.deepcopy(base.model_dump(mode="json", exclude_none=True))
    raw["version"] = version
    return PackageDoc.model_validate(raw)


def _registry(build_docs: Build, *, depends: bool = False) -> tuple[PackageRegistry, PackageDoc]:
    docs = build_docs()
    registry = PackageRegistry(docs)
    newer = _next_company(docs)
    registry.add(newer, origin="ledger")
    return registry, newer


def test_the_company_uses_the_highest_version_whatever_its_origin(build_docs: Build) -> None:
    registry, newer = _registry(build_docs)
    keys = [d.key() for d in registry.adopted("company")]
    assert keys == [newer.key()]


def test_a_project_does_not_get_a_ledger_version_it_has_not_pinned(build_docs: Build) -> None:
    docs = [d for d in build_docs() if d.kind == "company"]
    registry = PackageRegistry(docs)
    registry.add(_next_company(docs), origin="ledger")
    keys = [d.key() for d in registry.adopted("project:P123")]
    assert keys == ["co.acme.engineering@3.2.0"]


def test_a_project_gets_the_version_it_pinned(build_docs: Build) -> None:
    docs = [d for d in build_docs() if d.kind == "company"]
    registry = PackageRegistry(docs)
    registry.add(_next_company(docs), origin="ledger")
    keys = [d.key() for d in registry.adopted("project:P123", {"co.acme.engineering": "3.3.0"})]
    assert keys == ["co.acme.engineering@3.3.0"]


def test_a_pin_may_name_a_directory_version_below_the_highest(build_docs: Build) -> None:
    docs = build_docs()
    registry = PackageRegistry(docs)
    registry.add(_next_company(docs, "3.1.0"), origin="directory")
    keys = [d.key() for d in registry.adopted("project:P999", {"co.acme.engineering": "3.1.0"})]
    assert keys == ["co.acme.engineering@3.1.0"]


def test_a_pin_that_disagrees_with_a_package_of_the_project_is_an_error(build_docs: Build) -> None:
    registry, _ = _registry(build_docs)
    with pytest.raises(PackageError, match="pinned at both 3.2.0 and 3.3.0"):
        registry.adopted("project:P123", {"co.acme.engineering": "3.3.0"})


def test_a_pin_that_agrees_with_a_package_of_the_project_is_fine(build_docs: Build) -> None:
    registry, _ = _registry(build_docs)
    keys = [d.key() for d in registry.adopted("project:P123", {"co.acme.engineering": "3.2.0"})]
    assert keys[0] == "co.acme.engineering@3.2.0"


def test_a_pin_to_something_that_is_not_a_registered_company_package_is_an_error(
    build_docs: Build,
) -> None:
    registry, _ = _registry(build_docs)
    with pytest.raises(PackageError, match="not a registered company package"):
        registry.adopted("project:P999", {"co.acme.engineering": "9.9.9"})
    with pytest.raises(PackageError, match="not a registered company package"):
        registry.adopted("project:P999", {"x.P123": "1.4.0"})


def test_a_ledger_extension_of_the_project_is_in_force_at_once(build_docs: Build) -> None:
    docs = build_docs()
    registry = PackageRegistry(docs)
    old = next(d for d in docs if d.package == "x.P123")
    raw = copy.deepcopy(old.model_dump(mode="json", exclude_none=True))
    raw["version"] = "1.5.0"
    registry.add(PackageDoc.model_validate(raw), origin="ledger")
    keys = [d.key() for d in registry.adopted("project:P123")]
    assert "x.P123@1.5.0" in keys and "x.P123@1.4.0" not in keys


def test_the_origin_of_a_document_is_remembered(build_docs: Build) -> None:
    registry, newer = _registry(build_docs)
    assert registry.origin("co.acme.engineering", "3.2.0") == "directory"
    assert registry.origin(newer.package, newer.version) == "ledger"
    assert registry.origin("nope", "1.0.0") is None


def _waiver(path: str = "psets.valve_data.size_in") -> WaiverDef:
    return WaiverDef(path=path, reason="Legacy valves.", approver="user:admin")


def test_extra_waivers_make_a_project_without_a_declared_mode_strict_with_waivers(
    build_docs: Build,
) -> None:
    docs = [d for d in build_docs() if d.kind == "company"]
    plain = compose(docs, "project:P999")
    assert plain.conformance.mode == "strict" and plain.conformance.waivers == []
    waived = compose(docs, "project:P999", extra_waivers=[_waiver()])
    assert waived.conformance.mode == "strict_with_waivers"
    assert [w.path for w in waived.conformance.waivers] == ["psets.valve_data.size_in"]
    assert waived.hash != plain.hash


def test_a_declared_mode_is_kept_when_waivers_are_added(build_docs: Build) -> None:
    docs = build_docs()  # x.P123 declares strict
    schema = compose(docs, "project:P123", extra_waivers=[_waiver()])
    assert schema.conformance.mode == "strict"
    assert [w.path for w in schema.conformance.waivers] == ["psets.valve_data.size_in"]


def test_a_waiver_the_package_already_holds_is_not_added_twice(build_docs: Build) -> None:
    def mutate(raw: dict[str, dict[str, Any]]) -> None:
        raw["x.P123"]["conformance"] = {
            "mode": "strict_with_waivers",
            "waivers": [
                {"path": "psets.valve_data.size_in", "reason": "In the package.", "approver": "a"}
            ],
        }

    docs = build_docs(mutate)
    schema = compose(
        docs, "project:P123", extra_waivers=[_waiver(), _waiver("psets.valve_data.tag_no")]
    )
    paths = [w.path for w in schema.conformance.waivers]
    assert paths == ["psets.valve_data.size_in", "psets.valve_data.tag_no"]
    assert schema.conformance.waivers[0].reason == "In the package."


def test_a_waiver_for_a_property_that_does_not_exist_is_refused(build_docs: Build) -> None:
    docs = [d for d in build_docs() if d.kind == "company"]
    with pytest.raises(SchemaCompileError):
        compose(docs, "project:P999", extra_waivers=[_waiver("psets.valve_data.nope")])
