"""`tl awp` reads and groups (T04a), on a copy of the S4 seed ledger.

``--db`` is the root option, so it goes before the group: ``tl --db X awp ...``.
"""

from __future__ import annotations

import atexit
import functools
import importlib.util
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tl_adapters.db import as_target, create_schema
from tl_cli.main import app
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"


def load_world() -> ModuleType:
    """The ``awp_world`` helper of the module tests (the S4 seed ledger), loaded by path."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@functools.cache
def seed_path() -> Path:
    """The S4 seed ledger on SQLite, built once per process."""
    work = Path(tempfile.mkdtemp(prefix="awp-cli-seed-"))
    atexit.register(shutil.rmtree, work, True)
    path = work / "seed.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_world().World(target)
    world.people()
    world.editions()
    world.seed()
    return path


def seed_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "ledger.db"
    src = sqlite3.connect(seed_path())
    dst = sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return copy


class Cli:
    """``tl --db DB awp ...`` via the CliRunner; a dev ledger file lets ``--actor`` name anyone."""

    def __init__(self, db: Path, tmp_path: Path) -> None:
        self.db = db
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str) -> Result:
        return CliRunner().invoke(app, ["--db", str(self.db), "awp", *argv], env=self.env)

    def project(self, *argv: str) -> Result:
        return self.run(*argv, "--project", PROJECT)

    def write(self, *argv: str, who: str = "user:sue") -> Result:
        return self.run(*argv, "--project", PROJECT, "--actor", who)

    def ok(self, *argv: str) -> list[str]:
        result = self.project(*argv)
        assert result.exit_code == 0, result.output
        return result.stdout.splitlines()

    def scalar(self, sql: str, **params: Any) -> Any:
        from sqlalchemy import text
        from tl_adapters.db import open_uow

        with open_uow(as_target(str(self.db)), readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


def test_cwp_ls_lists_the_six_packages_with_budget_and_title(cli: Cli) -> None:
    lines = cli.ok("cwp", "ls")
    assert lines[0] == "cwps: 6"
    assert lines[1] == "P123-CWP-CIV-0001  In development  CIV  A3  3,100.0  Foundations unit 2"
    assert len(lines) == 7


@pytest.mark.parametrize(
    ("option", "value", "count"),
    [("--state", "Planned", 2), ("--discipline", "CIV", 2), ("--cwa", "A1", 2)],
)
def test_cwp_ls_filters(cli: Cli, option: str, value: str, count: int) -> None:
    lines = cli.ok("cwp", "ls", option, value)
    assert lines[0] == f"cwps: {count}"
    assert len(lines) == count + 1


def test_cwp_ls_header_prints_zero_for_no_match(cli: Cli) -> None:
    assert cli.ok("cwp", "ls", "--state", "Closed") == ["cwps: 0"]


def test_cwp_show_prints_the_fields_the_allocation_and_the_counts(cli: Cli) -> None:
    lines = cli.ok("cwp", "show", "P123-CWP-PIP-0001")
    assert lines[0] == "cwp P123-CWP-PIP-0001"
    assert "state Released for IWP development" in lines
    assert "planned 2026-11-02 to 2027-01-29" in lines
    assert "budget 4,200.0" in lines
    assert "  1.1.1  100.00" in lines
    assert "packages 0" in lines
    assert "activities 0" in lines


def test_an_unknown_cwp_or_node_exits_1_with_an_error_line(cli: Cli) -> None:
    result = cli.project("cwp", "show", "NO-SUCH-CWP")
    assert result.exit_code == 1
    assert result.stderr.splitlines() == ["error: no CWP NO-SUCH-CWP"]
    result = cli.project("wbs", "show", "9.9.9")
    assert result.exit_code == 1
    assert "error: no WBS node" in result.stderr


def test_cwa_ls_and_wbs_tree_and_node(cli: Cli) -> None:
    cwas = cli.ok("cwa", "ls")
    assert cwas[0] == "cwas: 4"
    assert cwas[1] == "A1  Area A1  North  active"
    tree = cli.ok("wbs", "tree")
    assert tree[0] == "wbs nodes: 9"
    assert tree[1].startswith("1  Plant")
    assert tree[3].startswith("1.1.1")
    node = cli.ok("wbs", "show", "1.1.1")
    assert node[:4] == ["wbs 1.1.1", "title Area 1.1.1", "parent 1.1", "depth 2"]
    assert "retired no" in node
    assert "total -" in node  # no rollup rows yet


def test_wbs_tree_depth_limits_the_levels(cli: Cli) -> None:
    lines = cli.ok("wbs", "tree", "--depth", "1")
    assert lines[0] == "wbs nodes: 1"


def test_path_show_versions_and_a_version_that_does_not_exist(cli: Cli) -> None:
    shown = cli.ok("path", "show")
    assert shown[0] == "path version 1 of 1"
    assert [line.split("  ")[:2] for line in shown[1:]] == [
        ["1", "A1"],
        ["2", "A2"],
        ["3", "A3"],
        ["4", "A4"],
    ]
    versions = cli.ok("path", "versions")
    assert len(versions) == 1
    assert versions[0].endswith("steps 4  current")
    # an unknown version prints the no-path line and exits 0 (the view returns None for both)
    result = cli.project("path", "show", "--version", "9")
    assert result.exit_code == 0
    assert result.stdout.strip() == "no path of construction in project P123"


def test_a_project_without_a_path_prints_the_line_and_exits_0(cli: Cli) -> None:
    for argv in (("path", "show"), ("path", "versions")):
        result = cli.run(*argv, "--project", "P999")
        assert result.exit_code == 0
        assert result.stdout.strip() == "no path of construction in project P999"


def test_package_ls_prints_the_header_at_zero_and_refuses_a_bad_kind(cli: Cli) -> None:
    assert cli.ok("package", "ls") == ["packages: 0"]
    result = cli.project("package", "ls", "--kind", "XYZ")
    assert result.exit_code == 1


def test_package_ls_lists_a_recorded_package_after_a_write(cli: Cli) -> None:
    done = cli.write(
        "package", "record", "--type", "ewp", "--number", "EWP-7", "--title", "Rack drawings",
        "--status", "Issued", "--constraint-source",
    )  # fmt: skip
    assert done.exit_code == 0, done.output
    lines = cli.ok("package", "ls")
    assert lines[0] == "packages: 1"
    assert lines[1].startswith("EWP-7  EWP  Issued")
    assert lines[1].endswith("  yes")
    assert cli.ok("package", "ls", "--kind", "PWP") == ["packages: 0"]
