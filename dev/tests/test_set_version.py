"""dev/release/set_version.sh on a fixture tree in tmp_path (P2-REL-T01). No network."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "release" / "set_version.sh"


def _pyproject(version: str | None, extra: str = "") -> str:
    lines = ["[project]", 'name = "pkg"']
    if version is not None:
        lines.append(f'version = "{version}"')
    lines.append('requires-python = ">=3.12"')
    text = "\n".join(lines) + "\n"
    return text + extra


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A repo-shaped tree: the script under dev/release/, two packages, one tl-module."""
    root = tmp_path / "repo"
    (root / "dev" / "release").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "dev" / "release" / "set_version.sh")
    for rel in ("packages/tl-core", "packages/tl-cli", "packages/tl-modules/awp"):
        (root / rel).mkdir(parents=True)
        extra = '\n[tool.demo]\nversion = "keep-me"\n'
        (root / rel / "pyproject.toml").write_text(_pyproject("0.0.1", extra))
    return root


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "dev" / "release" / "set_version.sh"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _versions(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.glob("packages/**/pyproject.toml")):
        out[str(path.parent.relative_to(root))] = path.read_text()
    return out


def test_rewrites_project_version_in_every_package(tree: Path) -> None:
    result = _run(tree, "0.1.0")
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3  # one line per pyproject
    for rel in ("packages/tl-core", "packages/tl-cli", "packages/tl-modules/awp"):
        text = (tree / rel / "pyproject.toml").read_text()
        assert 'version = "0.1.0"' in text
        assert 'version = "0.0.1"' not in text
        # only the [project] table is touched: the tool table keeps its own version line
        assert '[tool.demo]\nversion = "keep-me"' in text


def test_refuses_a_bad_version_and_writes_nothing(tree: Path) -> None:
    before = _versions(tree)
    for bad in ("0.1", "1.2.3.4", "v1.2.3", "1.2.3-rc1", ""):
        result = _run(tree, bad)
        assert result.returncode == 2, bad
    assert _versions(tree) == before


def test_bad_usage_exits_2(tree: Path) -> None:
    assert _run(tree).returncode == 2
    assert _run(tree, "0.1.0", "extra").returncode == 2


def test_refuses_a_missing_version_line_and_writes_nothing(tree: Path) -> None:
    (tree / "packages" / "tl-cli" / "pyproject.toml").write_text(_pyproject(None))
    before = _versions(tree)
    result = _run(tree, "0.1.0")
    assert result.returncode == 1
    assert "packages/tl-cli" in result.stderr
    assert _versions(tree) == before  # the other files were not rewritten either
