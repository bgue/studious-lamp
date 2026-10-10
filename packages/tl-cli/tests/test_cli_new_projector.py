"""`tl new projector <module>.<name>`: a projector for a derived table, its tests and a doc page.

Provided by the supervisor (ticket P0-I8-T49 makes it pass); do not edit. The expected files for
`inspection.weld_counts --event Weld.Created` are in `tests/expected/projector/` (the `.txt`
suffix keeps them out of ruff and pyright); the supervisor ran them in a temporary tree and in the
repository (ruff, pyright and pytest all pass).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scaffold_support import generated_tests_pass, ruff_clean, tl_new

EXPECTED = Path(__file__).parent / "expected" / "projector"
FILES = {
    "packages/tl-modules/inspection/src/tl_mod_inspection/projectors/weld_counts.py": (
        "projector.py.txt"
    ),
    "packages/tl-modules/inspection/tests/test_projector_weld_counts.py": "test.py.txt",
    "docs/modules/inspection/projector-weld_counts.md": "spec.md",
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A temporary repository with the module `inspection` already scaffolded."""
    assert tl_new(tmp_path, "module", "inspection").exit_code == 0
    return tmp_path


def test_it_writes_the_three_files_exactly_as_the_expected_ones(root: Path) -> None:
    result = tl_new(root, "projector", "inspection.weld_counts", "--event", "Weld.Created")
    assert result.exit_code == 0, result.output
    created = sorted(line.removeprefix("created ") for line in result.stdout.splitlines())
    assert created == sorted(FILES)
    for path, expected in FILES.items():
        assert (root / path).read_text() == (EXPECTED / expected).read_text(), path


def test_it_tells_what_to_do_next(root: Path) -> None:
    result = tl_new(root, "projector", "inspection.weld_counts", "--event", "Weld.Created")
    assert "next: register WeldCountsProjector in the registry your application builds" in (
        result.stderr
    )
    assert "next: just check && just test" in result.stderr


def test_the_generated_files_pass_ruff_and_their_own_tests(root: Path) -> None:
    tl_new(root, "projector", "inspection.weld_counts", "--event", "Weld.Created")
    ruff_clean(root)
    assert "4 passed" in generated_tests_pass(root, "packages/tl-modules/inspection")


def test_the_longest_names_still_give_formatted_code(tmp_path: Path) -> None:
    assert tl_new(tmp_path, "module", "abcdefghijklmnopqrst").exit_code == 0
    name = "abcdefghijklmnopqrst.abcdefghij_abcdefghij_abcdefghij_abcdef"
    assert tl_new(tmp_path, "projector", name).exit_code == 0
    ruff_clean(tmp_path)
    generated_tests_pass(tmp_path, "packages/tl-modules/abcdefghijklmnopqrst")


def test_without_an_event_option_it_handles_record_created(root: Path) -> None:
    tl_new(root, "projector", "inspection.counts")
    text = (
        root / "packages/tl-modules/inspection/src/tl_mod_inspection/projectors/counts.py"
    ).read_text()
    assert 'handles = frozenset({"Record.Created"})' in text
    ruff_clean(root)
    generated_tests_pass(root, "packages/tl-modules/inspection")


def test_several_events_are_listed_sorted_and_the_tests_still_pass(root: Path) -> None:
    result = tl_new(
        root, "projector", "inspection.mix", "--event", "Weld.Created", "--event", "Pq.Approved"
    )
    assert result.exit_code == 0, result.output
    text = (
        root / "packages/tl-modules/inspection/src/tl_mod_inspection/projectors/mix.py"
    ).read_text()
    assert 'handles = frozenset({"Pq.Approved", "Weld.Created"})' in text
    doc = (root / "docs/modules/inspection/projector-mix.md").read_text()
    assert doc.index("Pq.Approved") < doc.index("Weld.Created")
    ruff_clean(root)
    generated_tests_pass(root, "packages/tl-modules/inspection")


def test_it_needs_the_module_first(tmp_path: Path) -> None:
    result = tl_new(tmp_path, "projector", "inspection.counts")
    assert result.exit_code == 1 and "tl new module inspection" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_a_second_run_overwrites_nothing(root: Path) -> None:
    tl_new(root, "projector", "inspection.weld_counts")
    doc = root / "docs/modules/inspection/projector-weld_counts.md"
    doc.write_text("my edits\n")
    result = tl_new(root, "projector", "inspection.weld_counts")
    assert result.exit_code == 1 and "refusing to overwrite" in result.stderr
    assert doc.read_text() == "my edits\n"


def test_dry_run_writes_nothing(root: Path) -> None:
    result = tl_new(root, "projector", "inspection.counts", "--dry-run")
    assert result.exit_code == 0 and result.stdout.count("would create") == 3
    assert not (root / "docs/modules/inspection/projector-counts.md").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["inspection.Counts"],
        ["inspection.c"],
        ["counts"],
        ["inspection.counts", "--event", "weld.created"],
        ["inspection.counts", "--event", "Weld"],
        ["inspection.counts", "--event", "Weld.Created; DROP TABLE x"],
    ],
)
def test_a_bad_name_or_event_is_refused_and_nothing_is_written(root: Path, args: list[str]) -> None:
    before = sorted(p.as_posix() for p in root.rglob("*") if p.is_file())
    result = tl_new(root, "projector", *args)
    assert result.exit_code != 0
    assert sorted(p.as_posix() for p in root.rglob("*") if p.is_file()) == before
