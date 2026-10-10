"""Helpers for the `tl new` tests: run a scaffolder into a temp tree and check what it wrote.

A scaffold's output must pass the repository's own gates, so ``check_generated`` runs ruff (lint
and format check, with the repository's configuration) over the new files and runs the new
package's tests in a child process with the new package on ``PYTHONPATH``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tl_cli.main import app
from typer.testing import CliRunner, Result

REPO = Path(__file__).resolve().parents[3]
runner = CliRunner()


def tl_new(root: Path, *args: str) -> Result:
    """``tl new <args> --root <root>`` in process."""
    result = runner.invoke(app, ["new", *args, "--root", str(root)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def files_under(root: Path) -> list[str]:
    """Posix paths of every file below ``root``, sorted."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def ruff_clean(root: Path) -> None:
    """Fail if ruff lint or ruff format --check finds anything in ``root``."""
    config = str(REPO / "pyproject.toml")
    for command in (["check"], ["format", "--check"]):
        done = subprocess.run(
            [sys.executable, "-m", "ruff", *command, "--config", config, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, f"ruff {' '.join(command)}:\n{done.stdout}\n{done.stderr}"


def generated_tests_pass(root: Path, package_dir: str) -> str:
    """Run ``<root>/<package_dir>/tests`` in a child process; fail on any failure; return output."""
    package = root / package_dir
    env = {**os.environ, "PYTHONPATH": str(package / "src")}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(root),
            str(package / "tests"),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, f"generated tests failed:\n{done.stdout}\n{done.stderr}"
    return done.stdout
