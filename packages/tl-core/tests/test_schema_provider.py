"""The process-wide schema provider (P0-I2)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from tl_core.schema_provider import (
    DirectorySchemaProvider,
    get_provider,
    set_provider,
    use_provider,
)
from tl_schema.registry import PackageError

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    target = tmp_path / "pkgs"
    shutil.copytree(FIXTURES, target)
    return target


def test_effective_schema_for_a_project(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    schema = provider.effective("project:P123")
    assert list(schema.psets) == ["prj.shutdown_tie_in", "valve_data"]
    assert provider.effective("project:P123") is schema  # cached
    assert provider.scopes() == ["company", "project:P123"]
    assert list(provider.effective("company").psets) == ["safety_data", "valve_data"]


def test_a_changed_file_is_noticed_on_the_next_call(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    before = provider.effective("project:P123").hash
    path = directory / "x.P123@1.4.0.yaml"
    path.write_text(path.read_text().replace("Shutdown window reference", "Shutdown window ref"))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert provider.effective("project:P123").hash != before


def test_reload_reports_changed_scopes(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    old = provider.effective("project:P123").hash
    provider.reload()  # the company scope was not cached yet, so it is reported once
    assert provider.reload() == []  # no edits, no changes
    path = directory / "co.acme.engineering@3.2.0.yaml"
    path.write_text(path.read_text().replace("Nominal pipe size", "Nominal size"))
    changes = provider.reload()
    by_scope = {c.scope: c for c in changes}
    assert set(by_scope) == {"company", "project:P123"}
    assert by_scope["project:P123"].old_hash == old
    assert by_scope["project:P123"].new_hash == provider.effective("project:P123").hash
    assert provider.reload() == []


def test_reload_of_a_scope_never_asked_for_has_no_old_hash(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    changes = provider.reload()
    assert {c.scope: c.old_hash for c in changes} == {"company": None, "project:P123": None}


def test_a_broken_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(PackageError):
        DirectorySchemaProvider(tmp_path / "missing").effective("company")


def test_use_provider_restores_the_previous_one(directory: Path) -> None:
    original = get_provider()
    mine = DirectorySchemaProvider(directory)
    with use_provider(mine) as active:
        assert active is mine
        assert get_provider() is mine
    assert get_provider() is original
    previous = set_provider(mine)
    assert previous is original
    set_provider(original)
