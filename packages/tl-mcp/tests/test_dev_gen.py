"""``gen``: the codegen drift report (brief 25.4), over the real repository and over copies."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_mcp.dev.guard import find_repo_root
from tl_mcp.dev.tool_gen import GenOutput, gen_report
from tl_schema.generate import GENERATED_DIR, SCHEMA_DIR

REPO = find_repo_root()
EDITED = "models.py"
DELETED = "ddl/sqlite/wh_health.sql"
MARKER = "# drift marker (test_dev_gen)"


@pytest.fixture(scope="module", autouse=True)
def real_tree_is_untouched() -> Iterator[None]:
    yield
    status = subprocess.run(
        ["git", "status", "--porcelain", "packages/tl-schema"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status == ""


@pytest.fixture
def copy_of_generated(tmp_path: Path) -> Path:
    copy = tmp_path / "generated"
    shutil.copytree(GENERATED_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.relative_to(root).parts
    }


def _edit(copy: Path, relative: str) -> None:
    target = copy / relative
    target.write_text(target.read_text(encoding="utf-8") + MARKER + "\n", encoding="utf-8")


def test_the_real_repository_is_in_sync(dev_env: DevHarness) -> None:
    result = dev_env.structured("gen")
    assert result["in_sync"] is True
    assert result["drift"] == []
    assert result["applied"] is False
    assert result["diff"] == ""
    assert result["file_count"] > 50


def test_drift_is_reported_and_nothing_is_written(copy_of_generated: Path) -> None:
    _edit(copy_of_generated, EDITED)
    (copy_of_generated / DELETED).unlink()
    (copy_of_generated / "extra.txt").write_text("stray\n", encoding="utf-8")
    before = _tree(copy_of_generated)

    result = gen_report(SCHEMA_DIR, copy_of_generated, apply=False)

    assert result.in_sync is False
    assert result.applied is False
    assert {(item.kind, item.path) for item in result.drift} == {
        ("differs", EDITED),
        ("missing", DELETED),
        ("stale", "extra.txt"),
    }
    assert f"--- a/{EDITED}" in result.diff
    assert f"-{MARKER}" in result.diff  # a is the file on disk, b what the generators produce
    assert _tree(copy_of_generated) == before


def test_apply_rewrites_the_copy(copy_of_generated: Path) -> None:
    _edit(copy_of_generated, EDITED)
    (copy_of_generated / DELETED).unlink()
    (copy_of_generated / "extra.txt").write_text("stray\n", encoding="utf-8")

    result = gen_report(SCHEMA_DIR, copy_of_generated, apply=True)

    assert result.in_sync is True
    assert result.drift == []
    assert result.diff == ""
    assert result.applied is True
    assert _tree(copy_of_generated) == _tree(GENERATED_DIR)

    again = gen_report(SCHEMA_DIR, copy_of_generated, apply=True)
    assert again.in_sync is True
    assert again.applied is False


def test_the_diff_shows_at_most_five_files_and_is_capped(copy_of_generated: Path) -> None:
    paths = sorted(_tree(copy_of_generated))[:10]
    for path in paths:
        _edit(copy_of_generated, path)

    result = gen_report(SCHEMA_DIR, copy_of_generated, apply=False)

    assert len(result.drift) == 10
    assert all(item.kind == "differs" for item in result.drift)
    shown = [line for line in result.diff.splitlines() if line.startswith("--- a/")]
    assert len(shown) == 5
    assert len(result.diff) <= 20000 + 20


def test_a_long_diff_is_cut_at_20000_characters(copy_of_generated: Path) -> None:
    target = copy_of_generated / EDITED
    block = "".join(f"added line {number:06d}\n" for number in range(4000))
    target.write_text(block + target.read_text(encoding="utf-8"), encoding="utf-8")

    result = gen_report(SCHEMA_DIR, copy_of_generated, apply=False)

    assert result.diff.endswith("... (cut)\n")
    assert len(result.diff) <= 20000 + 20


def test_two_calls_at_once_both_return_and_agree(copy_of_generated: Path) -> None:
    _edit(copy_of_generated, EDITED)
    results: list[GenOutput] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(gen_report(SCHEMA_DIR, copy_of_generated, apply=False))
        except BaseException as exc:  # reported by the main thread below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert results[0] == results[1]
    assert [item.path for item in results[0].drift] == [EDITED]


def test_the_tool_is_audited_and_writes_nothing_without_apply(dev_env: DevHarness) -> None:
    before = _tree(GENERATED_DIR)

    result = dev_env.structured("gen", apply=False)

    assert result["in_sync"] is True
    gen_lines = [line for line in dev_env.audit_lines() if line["tool"] == "gen"]
    assert gen_lines[-1]["outcome"] == "ok"
    assert gen_lines[-1]["detail"] == {"apply": "false"}
    assert _tree(GENERATED_DIR) == before


def test_apply_is_refused_when_the_generated_directory_leaves_the_repository(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    package = repo / "packages" / "tl-schema" / "src" / "tl_schema"
    package.mkdir(parents=True)
    (package / "generated").symlink_to(outside, target_is_directory=True)
    root = tmp_path / "root"
    root.mkdir()
    dev_env = DevHarness.build(root, repo_root=repo)

    with pytest.raises(ToolError, match="refused"):
        dev_env.call("gen", apply=True)

    assert list(outside.iterdir()) == []
    gen_lines = [line for line in dev_env.audit_lines() if line["tool"] == "gen"]
    assert gen_lines[-1]["outcome"] == "refused"
