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
from tl_core.services.errors import InvalidScopeError, ServiceError
from tl_schema.compile import SchemaCompileError
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


# --- review follow-ups -------------------------------------------------------------------------


def restore_mtime(path: Path, mtime_ns: int) -> None:
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_a_same_size_edit_with_the_old_mtime_is_noticed(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    before = provider.effective("project:P123")
    path = directory / "x.P123@1.4.0.yaml"
    stat = path.stat()
    path.write_text(path.read_text().replace("Shutdown window", "Shutdown Window"))
    restore_mtime(path, stat.st_mtime_ns)
    after = path.stat()
    assert (after.st_size, after.st_mtime_ns) == (stat.st_size, stat.st_mtime_ns)
    assert provider.effective("project:P123").hash != before.hash


def test_a_changed_size_alone_is_noticed(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    before = provider.effective("project:P123").hash
    path = directory / "x.P123@1.4.0.yaml"
    stat = path.stat()
    path.write_text(path.read_text().replace("Shutdown window", "Shutdown window of the plant"))
    restore_mtime(path, stat.st_mtime_ns)
    assert provider.effective("project:P123").hash != before


def test_a_changed_mtime_alone_is_not_a_change(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    before = provider.effective("project:P123")
    path = directory / "x.P123@1.4.0.yaml"
    restore_mtime(path, path.stat().st_mtime_ns + 5_000_000_000)
    assert provider.effective("project:P123") is before  # content unchanged: cache kept


def test_reload_reports_an_edit_that_effective_noticed_first(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    provider.reload()
    old = provider.effective("project:P123").hash
    path = directory / "x.P123@1.4.0.yaml"
    path.write_text(path.read_text().replace("Shutdown window reference", "Shutdown window ref"))
    new = provider.effective("project:P123").hash  # picks the edit up on its own
    assert new != old
    changes = provider.reload()
    assert [(c.scope, c.old_hash, c.new_hash) for c in changes] == [("project:P123", old, new)]
    assert provider.reload() == []


def test_a_failed_reload_changes_nothing(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    provider.reload()
    old = provider.effective("project:P123").hash
    path = directory / "x.P123@1.4.0.yaml"
    good = path.read_text()
    path.write_text(good.replace("tighten:", "tighten:\n      size_in: {minimum: 0.1}\n    #"))
    with pytest.raises(SchemaCompileError):
        provider.reload()
    path.write_text(good.replace("Shutdown window reference", "Shutdown window ref"))
    changes = provider.reload()
    assert [c.scope for c in changes] == ["project:P123"]
    assert changes[0].old_hash == old  # the failed attempt reported nothing and kept old state


@pytest.mark.parametrize("scope", ["P123", "", "projects:P123", "project:", "Company"])
def test_a_malformed_scope_is_a_service_error(directory: Path, scope: str) -> None:
    provider = DirectorySchemaProvider(directory)
    with pytest.raises(InvalidScopeError) as caught:
        provider.effective(scope)
    assert isinstance(caught.value, ServiceError)


def test_a_project_without_packages_gets_the_company_set_rescoped(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    other = provider.effective("project:P999")
    assert other.scope == "project:P999"
    assert list(other.psets) == ["valve_data"]  # mandatory psets only
    assert other.psets["valve_data"].extension is None
    assert other.hash != provider.effective("company").hash
    assert other.hash != provider.effective("project:P123").hash


def test_effective_by_hash_finds_schemas_composed_earlier(directory: Path) -> None:
    provider = DirectorySchemaProvider(directory)
    first = provider.effective("project:P123")
    path = directory / "x.P123@1.4.0.yaml"
    path.write_text(path.read_text().replace("Shutdown window reference", "Shutdown window ref"))
    second = provider.effective("project:P123")
    assert second.hash != first.hash
    assert provider.effective_by_hash(first.hash) == first
    assert provider.effective_by_hash(second.hash) == second
    assert provider.effective_by_hash("nope") is None
