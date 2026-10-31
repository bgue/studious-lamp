"""The offline class of an extension type (OC-S2): ``tl:offline`` in ``type.yaml``.

Read at compile time (missing is ``none``, a bad value is a compile ``TypeIssue``), kept out of
``schema_hash``, and answered by ``offline_class`` from the attached source without any IO.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from extworld import LIFT, World
from tl_core import offline
from tl_core.extypes import provider as ext_provider
from tl_core.extypes.compile import compile_type
from tl_core.extypes.names import parse_type_ref

FIXTURE = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types"
LIFT_PACKAGE = FIXTURE / "co.acme" / "LiftPlan" / "1.0.0"
ANCHOR = "      tl:storage_mode: object-backed\n"
COORDS = parse_type_ref("co.acme.LiftPlan@1.0.0")


def package(tmp_path: Path, annotation: str | None) -> Path:
    """A copy of the LiftPlan package with ``tl:offline: <annotation>`` (or none) on its class."""
    target = tmp_path / ("missing" if annotation is None else annotation.replace(" ", "_"))
    shutil.copytree(LIFT_PACKAGE, target)
    if annotation is not None:
        path = target / "type.yaml"
        text = path.read_text(encoding="utf-8")
        assert text.count(ANCHOR) == 1
        path.write_text(
            text.replace(ANCHOR, f"{ANCHOR}      tl:offline: {annotation}\n"), encoding="utf-8"
        )
    return target


@pytest.mark.parametrize("value", ["full", "draft_only", "none"])
def test_each_declared_value_is_read(tmp_path: Path, value: str) -> None:
    compiled, issues = compile_type(package(tmp_path, value), COORDS, lint=False)
    assert issues == []
    assert compiled is not None and compiled.offline == value


def test_a_missing_annotation_defaults_to_none(tmp_path: Path) -> None:
    compiled, issues = compile_type(package(tmp_path, None), COORDS, lint=False)
    assert issues == []
    assert compiled is not None and compiled.offline == "none"


def test_the_shipped_example_packages_default_to_none() -> None:
    compiled, _ = compile_type(LIFT_PACKAGE, COORDS, lint=False)
    assert compiled is not None and compiled.offline == "none"


@pytest.mark.parametrize("value", ["sometimes", "Full", "draft"])
def test_a_bad_value_is_a_compile_issue_naming_the_annotation(tmp_path: Path, value: str) -> None:
    compiled, issues = compile_type(package(tmp_path, value), COORDS, lint=False)
    assert compiled is None
    assert [i.kind for i in issues][:1] == ["compile"]
    assert "tl:offline" in issues[0].detail and value in issues[0].detail
    assert "full, draft_only, none" in issues[0].detail


def test_the_offline_class_is_not_part_of_the_schema_hash(tmp_path: Path) -> None:
    hashes = {
        value: compile_type(package(tmp_path, value), COORDS, lint=False)[0]
        for value in ("full", "none")
    }
    missing = compile_type(package(tmp_path, None), COORDS, lint=False)[0]
    assert missing is not None and all(c is not None for c in hashes.values())
    assert {c.schema_hash() for c in hashes.values() if c} == {missing.schema_hash()}


@pytest.fixture
def attached(world: World) -> Iterator[World]:
    """``world`` with the process-wide attached source forgotten again afterwards."""
    yield world
    ext_provider._attached = None  # pyright: ignore[reportPrivateUsage]


def test_an_unregistered_extension_type_is_unknown_so_none_and_refused_as_unknown(
    attached: World,
) -> None:
    attached.source.documents()
    assert offline.offline_class("co.acme.Other") == "none"
    decision = offline.capture_allowed("co.acme.Other", "CreateRecord", node="site")
    assert (decision.allowed, decision.reason) == (False, "unknown_type")


def test_a_registered_type_without_the_key_is_none_and_online_only(attached: World) -> None:
    attached.sync()
    attached.source.documents()
    assert attached.source.offline_class(LIFT) == "none"
    assert offline.offline_class(LIFT) == "none"
    decision = offline.capture_allowed(LIFT, "CreateRecord", node="site")
    assert (decision.allowed, decision.reason) == (False, "online_only")


def test_a_registered_type_that_declares_its_class_is_answered_from_the_source(
    attached: World,
) -> None:
    attached.edit(attached.package(), "type.yaml", ANCHOR, f"{ANCHOR}      tl:offline: full\n")
    attached.sync()
    attached.source.documents()
    assert offline.offline_class(LIFT) == "full"
    decision = offline.capture_allowed(LIFT, "CreateRecord", node="device")
    assert (decision.allowed, decision.reason) == (True, "full")
    # the authority still allows everything, and a type the source never read stays unknown
    assert offline.capture_allowed(LIFT, "CreateRecord", node="authority").reason == "authority"
    assert offline.offline_class("co.acme.Other") == "none"


def test_a_draft_only_extension_type_lists_no_drafting_command(attached: World) -> None:
    attached.edit(
        attached.package(), "type.yaml", ANCHOR, f"{ANCHOR}      tl:offline: draft_only\n"
    )
    attached.sync()
    attached.source.documents()
    assert offline.offline_class(LIFT) == "draft_only"
    decision = offline.capture_allowed(LIFT, "CreateRecord", node="site")
    assert (decision.allowed, decision.reason) == (False, "not_drafting")


def test_a_core_type_is_not_overridden_by_the_extension_source(attached: World) -> None:
    attached.sync()
    attached.source.documents()
    assert offline.offline_class("core.Record") == "full"
    assert offline.offline_class("cost.CostCode") == "none"
