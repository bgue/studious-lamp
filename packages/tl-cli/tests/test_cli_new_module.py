"""`tl new module`: a module package, schema header and spec page that pass the repository gates."""

from __future__ import annotations

from pathlib import Path

import pytest
from scaffold_support import files_under, generated_tests_pass, ruff_clean, tl_new

EXPECTED = [
    "docs/modules/inspection/README.md",
    "packages/tl-mod-inspection/AGENTS.md",
    "packages/tl-mod-inspection/README.md",
    "packages/tl-mod-inspection/pyproject.toml",
    "packages/tl-mod-inspection/src/tl_mod_inspection/__init__.py",
    "packages/tl-mod-inspection/src/tl_mod_inspection/handlers/__init__.py",
    "packages/tl-mod-inspection/src/tl_mod_inspection/projectors/__init__.py",
    "packages/tl-mod-inspection/src/tl_mod_inspection/py.typed",
    "packages/tl-mod-inspection/tests/test_module.py",
    "schema/modules/inspection/module.yaml",
]


def test_it_creates_the_module_and_lists_the_next_steps(tmp_path: Path) -> None:
    result = tl_new(tmp_path, "module", "inspection")
    assert result.exit_code == 0, result.output
    assert files_under(tmp_path) == EXPECTED
    assert "next: uv lock" in result.stderr
    assert "next: uv run tl new record-type inspection.<Class>" in result.stderr


def test_it_lists_every_created_file_on_stdout(tmp_path: Path) -> None:
    result = tl_new(tmp_path, "module", "inspection")
    created = sorted(line.removeprefix("created ") for line in result.stdout.splitlines())
    assert created == EXPECTED


def test_the_generated_files_pass_ruff_and_their_own_tests(tmp_path: Path) -> None:
    tl_new(tmp_path, "module", "inspection")
    ruff_clean(tmp_path)
    assert "2 passed" in generated_tests_pass(tmp_path, "packages/tl-mod-inspection")


def test_the_package_is_named_for_the_workspace(tmp_path: Path) -> None:
    tl_new(tmp_path, "module", "weld_quality")
    pyproject = (tmp_path / "packages/tl-mod-weld-quality/pyproject.toml").read_text()
    assert 'name = "tl-mod-weld-quality"' in pyproject
    assert 'packages = ["src/tl_mod_weld_quality"]' in pyproject
    init = tmp_path / "packages/tl-mod-weld-quality/src/tl_mod_weld_quality/__init__.py"
    assert 'MODULE = "weld_quality"' in init.read_text()


def test_a_second_run_overwrites_nothing(tmp_path: Path) -> None:
    tl_new(tmp_path, "module", "inspection")
    readme = tmp_path / "docs/modules/inspection/README.md"
    readme.write_text("my edits\n")
    result = tl_new(tmp_path, "module", "inspection")
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.stderr
    assert readme.read_text() == "my edits\n"


def test_dry_run_prints_the_files_and_writes_nothing(tmp_path: Path) -> None:
    result = tl_new(tmp_path, "module", "inspection", "--dry-run")
    assert result.exit_code == 0
    assert sorted(line.removeprefix("would create ") for line in result.stdout.splitlines()) == (
        EXPECTED
    )
    assert files_under(tmp_path) == []


@pytest.mark.parametrize("name", ["Inspection", "core", "a", "../x", "a-b"])
def test_a_bad_module_name_is_refused_and_nothing_is_written(tmp_path: Path, name: str) -> None:
    result = tl_new(tmp_path, "module", name)
    assert result.exit_code != 0
    assert files_under(tmp_path) == []


def test_a_root_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    result = tl_new(tmp_path / "missing", "module", "inspection")
    assert result.exit_code == 1 and "not a directory" in result.stderr
