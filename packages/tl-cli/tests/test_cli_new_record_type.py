"""`tl new record-type <module>.<Class>`: schema stub, handler, tests and a spec page.

Provided by the supervisor (ticket P0-I8-T48 makes it pass); do not edit. The expected files for
`inspection.WeldInspection` are in `tests/expected/record_type/` (the `.txt` suffix keeps them out
of ruff and pyright); they were run by the supervisor in a temporary tree and in the repository
(ruff, pyright and pytest all pass).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scaffold_support import (
    copy_core_schema,
    generated_tests_pass,
    ruff_clean,
    tl_new,
)

EXPECTED = Path(__file__).parent / "expected" / "record_type"
MODULE_FILES = [
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
WELD_FILES = {
    "schema/modules/inspection/weld_inspection.yaml": "weld_inspection.yaml",
    "packages/tl-mod-inspection/src/tl_mod_inspection/handlers/weld_inspection.py": (
        "handler.py.txt"
    ),
    "packages/tl-mod-inspection/tests/test_weld_inspection.py": "test.py.txt",
    "docs/modules/inspection/weld_inspection.md": "spec.md",
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A temporary repository with the core schema and the module `inspection` scaffolded."""
    copy_core_schema(tmp_path)
    assert tl_new(tmp_path, "module", "inspection").exit_code == 0
    return tmp_path


def test_it_writes_the_four_files_exactly_as_the_expected_ones(root: Path) -> None:
    result = tl_new(root, "record-type", "inspection.WeldInspection")
    assert result.exit_code == 0, result.output
    created = sorted(line.removeprefix("created ") for line in result.stdout.splitlines())
    assert created == sorted(WELD_FILES)
    for path, expected in WELD_FILES.items():
        assert (root / path).read_text() == (EXPECTED / expected).read_text(), path


def test_it_tells_what_to_do_next(root: Path) -> None:
    result = tl_new(root, "record-type", "inspection.WeldInspection")
    assert (
        "next: add `- weld_inspection` to the imports of schema/modules/inspection/module.yaml"
        in (result.stderr)
    )
    assert "next: just check && just test" in result.stderr


def test_the_generated_files_pass_ruff_and_their_own_tests(root: Path) -> None:
    tl_new(root, "record-type", "inspection.WeldInspection")
    ruff_clean(root)
    assert "4 passed" in generated_tests_pass(root, "packages/tl-mod-inspection")


@pytest.mark.parametrize(
    ("module", "cls"),
    [
        ("inspection", "NCR"),
        ("weld_quality", "WeldProcedureSpec"),
        ("docs2", "Rev2Item"),
        ("abcdefghijklmnopqrst", "AbcdefghijklmnopqrstuvwxyzAbcd"),
    ],
)
def test_other_names_work_too(tmp_path: Path, module: str, cls: str) -> None:
    copy_core_schema(tmp_path)
    assert tl_new(tmp_path, "module", module).exit_code == 0
    result = tl_new(tmp_path, "record-type", f"{module}.{cls}")
    assert result.exit_code == 0, result.output
    assert len(result.stdout.splitlines()) == 4
    ruff_clean(tmp_path)
    generated_tests_pass(tmp_path, f"packages/tl-mod-{module.replace('_', '-')}")


def test_it_needs_the_module_first(tmp_path: Path) -> None:
    result = tl_new(tmp_path, "record-type", "inspection.Weld")
    assert result.exit_code == 1
    assert "tl new module inspection" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_a_second_run_overwrites_nothing(root: Path) -> None:
    tl_new(root, "record-type", "inspection.WeldInspection")
    spec = root / "docs/modules/inspection/weld_inspection.md"
    spec.write_text("my edits\n")
    result = tl_new(root, "record-type", "inspection.WeldInspection")
    assert result.exit_code == 1 and "refusing to overwrite" in result.stderr
    assert spec.read_text() == "my edits\n"


def test_dry_run_writes_nothing(root: Path) -> None:
    result = tl_new(root, "record-type", "inspection.WeldInspection", "--dry-run")
    assert result.exit_code == 0
    assert sorted(line.removeprefix("would create ") for line in result.stdout.splitlines()) == (
        sorted(WELD_FILES)
    )
    assert not (root / "schema/modules/inspection/weld_inspection.yaml").exists()


@pytest.mark.parametrize(
    "name",
    ["inspection.weld", "Weld", "inspection.Weld_X", "inspection.", "Inspection.Weld", "a.B.C"],
)
def test_a_bad_name_is_refused_and_nothing_is_written(root: Path, name: str) -> None:
    before = sorted(p.as_posix() for p in root.rglob("*") if p.is_file())
    result = tl_new(root, "record-type", name)
    assert result.exit_code != 0
    assert sorted(p.as_posix() for p in root.rglob("*") if p.is_file()) == before
