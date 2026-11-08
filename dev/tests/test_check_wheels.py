"""dev/release/check_wheels.py on fixture wheels in tmp_path (P2-REL-T03).

No real build, no network.
"""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev" / "release" / "check_wheels.py"

CORE_YAML = "tl_schema/_data/schema/core/core.yaml"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_wheels", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_wheels = _load()


def _repo(root: Path, names: tuple[str, ...]) -> Path:
    """A repo-shaped tree: one workspace member per name, packages/<name>/pyproject.toml."""
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )
    for name in names:
        (root / "packages" / name).mkdir(parents=True)
        (root / "packages" / name / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return root


def _wheel(
    directory: Path,
    dist: str,
    version: str,
    drop: tuple[str, ...] = (),
    extra: dict[str, bytes] | None = None,
) -> None:
    """Write a tiny wheel with the members the real build ships for `dist`.

    `drop` removes members from that set and `extra` adds members to it.
    """
    members: dict[str, bytes] = {
        f"{dist}/__init__.py": b"",
        f"{dist}-{version}.dist-info/METADATA": (
            f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n".encode()
        ),
    }
    if dist == "tl_schema":
        members[CORE_YAML] = b"name: core\n"
    if dist == "tl_cli":
        members["tl_cli/main.py"] = b"def main():\n    pass\n"
    for name in drop:
        del members[name]
    members.update(extra or {})
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(directory / f"{dist}-{version}-py3-none-any.whl", "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _clean(directory: Path) -> None:
    _wheel(directory, "tl_schema", "0.1.0")
    _wheel(directory, "tl_cli", "0.1.0")
    _wheel(directory, "tl_core", "0.1.0")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _repo(tmp_path / "repo", ("tl-schema", "tl-cli", "tl-core"))


@pytest.fixture
def wheels(tmp_path: Path) -> Path:
    directory = tmp_path / "release-0.1.0"
    _clean(directory)
    return directory


def test_clean_directory_passes(wheels: Path, repo: Path) -> None:
    count, problems = check_wheels.check(wheels, repo)
    assert count == 3
    assert problems == []


def test_forbidden_file_name_is_reported(wheels: Path, repo: Path) -> None:
    _wheel(wheels, "tl_core", "0.1.0", extra={"tl_core/tokens.json": b"{}"})
    _, problems = check_wheels.check(wheels, repo)
    assert problems == [
        "tl_core-0.1.0-py3-none-any.whl: tl_core/tokens.json: secret-like file name"
    ]


def test_forbidden_path_is_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    _wheel(wheels, "tl_core", "0.1.0", extra={"tl_core/dev/data/notes.txt": b"x\n"})
    _, problems = check_wheels.check(wheels, repo)
    assert problems == [
        "tl_core-0.1.0-py3-none-any.whl: tl_core/dev/data/notes.txt: path under dev/data/ or .gate/"
    ]


def test_tl_schema_without_core_yaml_is_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_schema-0.1.0-py3-none-any.whl").unlink()
    _wheel(wheels, "tl_schema", "0.1.0", drop=(CORE_YAML,))
    _, problems = check_wheels.check(wheels, repo)
    assert problems == [f"tl_schema-0.1.0-py3-none-any.whl: missing {CORE_YAML}"]


def test_tl_cli_without_main_is_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_cli-0.1.0-py3-none-any.whl").unlink()
    _wheel(wheels, "tl_cli", "0.1.0", drop=("tl_cli/main.py",))
    _, problems = check_wheels.check(wheels, repo)
    assert problems == ["tl_cli-0.1.0-py3-none-any.whl: missing tl_cli/main.py"]


def test_version_mismatch_is_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    _wheel(wheels, "tl_core", "0.2.0")
    _, problems = check_wheels.check(wheels, repo)
    assert problems == [
        "version mismatch: tl_cli-0.1.0-py3-none-any.whl is 0.1.0, "
        "tl_core-0.2.0-py3-none-any.whl is 0.2.0, "
        "tl_schema-0.1.0-py3-none-any.whl is 0.1.0"
    ]


def test_wheel_count_must_match_workspace(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    _, problems = check_wheels.check(wheels, repo)
    assert problems == ["wheel count: 2 wheels, workspace has 3 members"]


def test_demo_and_password_on_one_line_is_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    _wheel(
        wheels,
        "tl_core",
        "0.1.0",
        extra={"tl_core/defaults.py": b"# Demo Account PASSWORD: demo\n"},
    )
    _, problems = check_wheels.check(wheels, repo)
    assert problems == [
        "tl_core-0.1.0-py3-none-any.whl: tl_core/defaults.py: line mentions demo and password"
    ]


def test_demo_and_password_on_different_lines_is_not_reported(wheels: Path, repo: Path) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    text = b"demo accounts are listed in the docs\npassword hashing is argon2\n"
    _wheel(wheels, "tl_core", "0.1.0", extra={"tl_core/defaults.py": text})
    _, problems = check_wheels.check(wheels, repo)
    assert problems == []


def test_cli_prints_ok_and_exits_zero(
    wheels: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check_wheels.main([str(wheels), "--repo", str(repo)]) == 0
    assert capsys.readouterr().out == "OK 3 wheels\n"


def test_cli_prints_problems_and_exits_one(
    wheels: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wheels.joinpath("tl_core-0.1.0-py3-none-any.whl").unlink()
    assert check_wheels.main([str(wheels), "--repo", str(repo)]) == 1
    assert capsys.readouterr().out == "wheel count: 2 wheels, workspace has 3 members\n"
