"""Effective schema composition: adoption, hash, conformance settings, cache (brief 27.3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from tl_schema.compile import SchemaCompileError
from tl_schema.compose import EffectiveCache, compose, core_digest, project_of
from tl_schema.effective import compute_hash, resolve_path
from tl_schema.packages import PackageDoc

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]


def test_project_scope_composes_all_layers(build_docs: Build) -> None:
    schema = compose(build_docs(), "project:P123")
    assert schema.scope == "project:P123"
    assert [(p.name, p.version) for p in schema.packages] == [
        ("co.acme.engineering", "3.2.0"),
        ("prj.P123", "1.0.0"),
        ("x.P123", "1.4.0"),
    ]
    # safety_data has adoption "optional" and is not extended, so P123 does not get it.
    assert list(schema.psets) == ["prj.shutdown_tie_in", "valve_data"]
    assert len(schema.hash) == 64
    assert schema.hash == compute_hash(schema)
    assert schema.core_digest == core_digest()


def test_company_scope_keeps_every_company_pset(build_docs: Build) -> None:
    company = [d for d in build_docs() if d.kind == "company"]
    schema = compose(company, "company")
    assert list(schema.psets) == ["safety_data", "valve_data"]
    assert schema.psets["valve_data"].extension is None
    assert schema.psets["valve_data"].custom == {}


def test_hash_is_stable_and_order_independent(build_docs: Build) -> None:
    docs = build_docs()
    first = compose(docs, "project:P123")
    again = compose(list(reversed(docs)), "project:P123")
    assert first.hash == again.hash
    assert first == again


def test_hash_changes_when_a_package_changes(build_docs: Build) -> None:
    base = compose(build_docs(), "project:P123").hash

    def description(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["valve_data"]["properties"]["size_in"][
            "description"
        ] = "Changed text."

    def tighten(raw: Raw) -> None:
        raw["x.P123"]["extends"][0]["tighten"]["size_in"] = {"minimum": 1}

    def version(raw: Raw) -> None:
        raw["x.P123"]["version"] = "1.4.1"

    def reorder(raw: Raw) -> None:
        props = raw["co.acme.engineering"]["psets"]["valve_data"]["properties"]
        raw["co.acme.engineering"]["psets"]["valve_data"]["properties"] = dict(
            reversed(props.items())
        )

    hashes = {
        compose(build_docs(m), "project:P123").hash
        for m in (description, tighten, version, reorder)
    }
    assert base not in hashes
    assert len(hashes) == 4


def test_hash_depends_on_scope_and_core_release(build_docs: Build) -> None:
    docs = build_docs()
    assert compose(docs, "project:P123").hash != compose(docs, "project:P123", core="other").hash
    company = [d for d in docs if d.kind == "company"]
    assert compose(company, "company").hash != compose(docs, "project:P123").hash


def test_document_for_another_project_is_rejected(build_docs: Build) -> None:
    with pytest.raises(SchemaCompileError) as caught:
        compose(build_docs(), "project:OTHER")
    assert caught.value.rule == "invalid"


def test_conformance_settings_and_waivers(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["conformance"] = {
            "mode": "strict_with_waivers",
            "waivers": [
                {
                    "path": "psets.valve_data.size_in",
                    "reason": "Legacy valves have no size on record.",
                    "approver": "user:data-manager",
                    "expires": "2026-12-31",
                },
                {
                    "path": "psets.prj.shutdown_tie_in.window",
                    "reason": "Planned later.",
                    "approver": "user:data-manager",
                },
            ],
        }

    schema = compose(build_docs(mutate), "project:P123")
    assert schema.conformance.mode == "strict_with_waivers"
    assert [w.path for w in schema.conformance.waivers] == [
        "psets.valve_data.size_in",
        "psets.prj.shutdown_tie_in.window",
    ]
    assert str(schema.conformance.waivers[0].expires) == "2026-12-31"
    assert schema.conformance.waivers[1].expires is None


def test_waiver_must_name_a_property(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["conformance"] = {
            "mode": "strict_with_waivers",
            "waivers": [{"path": "psets.valve_data.nope", "reason": "r", "approver": "a"}],
        }

    with pytest.raises(SchemaCompileError) as caught:
        compose(build_docs(mutate), "project:P123")
    assert caught.value.rule == "unknown_property"


def test_two_packages_cannot_both_set_conformance(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["prj.P123"]["conformance"] = {"mode": "lenient"}

    with pytest.raises(SchemaCompileError) as caught:
        compose(build_docs(mutate), "project:P123")
    assert caught.value.rule == "duplicate"


def test_resolve_path(build_docs: Build) -> None:
    schema = compose(build_docs(), "project:P123")
    found = resolve_path(schema, "psets.valve_data.x.fat_witness_by")
    assert found is not None
    assert (found[0].name, found[1]) == ("valve_data", "x.fat_witness_by")
    nested = resolve_path(schema, "psets.prj.shutdown_tie_in.window")
    assert nested is not None
    assert nested[0].name == "prj.shutdown_tie_in"
    assert resolve_path(schema, "psets.valve_data.nope") is None
    assert resolve_path(schema, "psets.unknown.x") is None
    assert resolve_path(schema, "title") is None


def test_project_of() -> None:
    assert project_of("company") is None
    assert project_of("project:P123") == "P123"
    with pytest.raises(ValueError):
        project_of("P123")


def test_for_record_type(build_docs: Build) -> None:
    schema = compose(build_docs(), "project:P123")
    assert [p.name for p in schema.for_record_type("core.Record")] == [
        "prj.shutdown_tie_in",
        "valve_data",
    ]
    assert schema.for_record_type("piping.Weld") == []


def test_cache_builds_once_per_hash_and_kind(build_docs: Build) -> None:
    schema = compose(build_docs(), "project:P123")
    cache = EffectiveCache()
    calls: list[str] = []

    def build() -> list[str]:
        calls.append("built")
        return ["artefact"]

    assert cache.get_or_build(schema, "json", build) is cache.get_or_build(schema, "json", build)
    assert calls == ["built"]
    cache.get_or_build(schema, "form", build)
    assert len(cache) == 2 and len(calls) == 2
