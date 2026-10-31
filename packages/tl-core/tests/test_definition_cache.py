"""Workflow and expected-link definitions are parsed again only when a file changes (P2-PERF)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tl_core.filesig import signature
from tl_core.links.expected import default_expected_links
from tl_core.workflow.loader import default_workflows

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture
def schema_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(FIXTURES / "workflows", tmp_path / "workflows")
    shutil.copytree(FIXTURES / "links", tmp_path / "links")
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    return tmp_path


def test_signature_names_every_file_and_changes_with_an_edit(tmp_path: Path) -> None:
    assert signature(tmp_path / "missing") == ()
    (tmp_path / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    first = signature(tmp_path)
    assert [name for name, _size, _mtime in first] == ["a.yaml"]
    (tmp_path / "a.yaml").write_text("a: 22\n", encoding="utf-8")
    assert signature(tmp_path) != first


def test_workflows_are_the_same_definitions_but_each_call_has_its_own_registry(
    schema_dir: Path,
) -> None:
    first, second = default_workflows(), default_workflows()
    assert first is not second
    assert first.all() == second.all() and first.all()
    assert all(a is b for a, b in zip(first.all(), second.all(), strict=True))  # parsed once


def test_an_edited_workflow_file_is_read_again(schema_dir: Path) -> None:
    before = default_workflows()
    victim = next((schema_dir / "workflows").glob("*.yaml"))
    victim.unlink()  # a file removed is a change too
    after = default_workflows()
    assert len(after.all()) < len(before.all())


def test_expected_links_are_cached_per_edit_with_a_registry_per_call(schema_dir: Path) -> None:
    first, second = default_expected_links(), default_expected_links()
    assert first is not second
    assert first.record_types() == second.record_types()
    for record_type in first.record_types():
        assert first.for_type(record_type) == second.for_type(record_type)
