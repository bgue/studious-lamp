"""`tl req` and `tl wo` write verbs (P2-I4A-T04e1), on a copy of a ledger built by the module's
commands: the requisitions world (people, standards editions) and one IWP made by the awp module.

``--db`` is the root option, so it goes before the group: ``tl --db X req ...``.
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
from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
IWP_TITLE = "Rack 12 piping"


def _load(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_req_world() -> ModuleType:
    """The ``req_world`` helper of the requisitions tests, loaded by path."""
    return _load(
        "req_world", ROOT / "packages" / "tl-modules" / "requisitions" / "tests" / "req_world.py"
    )


def load_awp_world() -> ModuleType:
    """The ``awp_world`` helper of the awp tests, loaded by path; it makes the IWP for ``--for``."""
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    return _load("awp_world", path)


@functools.cache
def seed_path() -> Path:
    """The ledger on SQLite, built once per process: the people, the standards, one scope item
    (``P123-ITEM-0001``) and one IWP made by ``uma``."""
    work = Path(tempfile.mkdtemp(prefix="req-cli-seed-"))
    atexit.register(shutil.rmtree, work, True)
    path = work / "seed.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_req_world().World(target)
    world.people()
    world.editions()
    world.record("materials.ProjectItem", "P123-ITEM-0001")
    load_awp_world().World(target).call("uma", "CreateIwp", discipline="PIP", title=IWP_TITLE)
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
    """``tl --db DB req|wo ...`` via CliRunner; a dev ledger file lets ``--actor`` name anyone."""

    def __init__(self, db: Path, tmp_path: Path) -> None:
        self.db = db
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str) -> Result:
        return CliRunner().invoke(app, ["--db", str(self.db), *argv], env=self.env)

    def req(self, verb: str, *argv: str, who: str = "user:uma") -> Result:
        return self.run("req", verb, *argv, "--project", PROJECT, "--actor", who)

    def wo(self, verb: str, *argv: str, who: str = "user:sue") -> Result:
        return self.run("wo", verb, *argv, "--project", PROJECT, "--actor", who)

    def ok(self, result: Result) -> list[str]:
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output
        return result.stdout.splitlines()

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(as_target(str(self.db)), readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(seed_copy(tmp_path), tmp_path)


LABOR = ("--subject", "Six pipefitters", "--craft", "Pipefitter", "--headcount", "6")
DATES = ("--start", "2026-11-02", "--end", "2026-11-13")


def raise_labor(cli: Cli) -> str:
    """Raise a labour requisition as ``uma``; returns its key."""
    line = cli.ok(cli.req("raise-labor", *LABOR, *DATES))[0]
    assert line.startswith("raised P123-REQ-LAB-0001  version ")
    return "P123-REQ-LAB-0001"


def approve_and_key(cli: Cli, key: str) -> str:
    """Approve a requisition as the superuser ``sue``; returns the work order key."""
    cli.ok(cli.req("approve", key, who="user:sue"))
    return "P123-WO-0001"


def test_raise_labor_prints_the_key_and_the_version(cli: Cli) -> None:
    lines = cli.ok(cli.req("raise-labor", *LABOR, *DATES))
    assert lines == ["raised P123-REQ-LAB-0001  version 2"]


def test_raise_material_names_its_item_by_key(cli: Cli) -> None:
    line = "P123-ITEM-0001:12:EA"
    lines = cli.ok(cli.req("raise-material", "--subject", "Pipe", "--line", line))
    assert lines == ["raised P123-REQ-MAT-0001  version 2"]


def test_raise_material_refuses_an_unknown_item_once(cli: Cli) -> None:
    result = cli.req("raise-material", "--subject", "Pipe", "--line", "NO-ITEM:1:EA")
    assert result.exit_code == 1
    assert result.stderr.splitlines() == ["error: no item NO-ITEM"]


def test_raise_general_and_scaffold_print_their_keys(cli: Cli) -> None:
    general = cli.ok(cli.req("raise-general", "--subject", "Crane", "--type", "crane_lift"))
    assert general == ["raised P123-REQ-GEN-0001  version 2"]
    scaffold = cli.ok(
        cli.req("raise-scaffold", "--subject", "Frame", "--purpose", "Tie-ins", "--days", "5")
    )
    assert scaffold == ["raised P123-REQ-SCF-0001  version 2"]


def test_for_names_an_iwp_by_its_number(cli: Cli) -> None:
    iwp = cli.scalar("SELECT key FROM cur_core_record WHERE type = 'awp.IWP'")
    cli.ok(cli.req("raise-labor", *LABOR, *DATES, "--for", iwp))
    requisition = cli.scalar("SELECT id FROM cur_core_record WHERE key = 'P123-REQ-LAB-0001'")
    iwp_id = cli.scalar("SELECT id FROM cur_core_record WHERE key = :k", k=iwp)
    linked = cli.scalar(
        "SELECT COUNT(*) FROM cur_links "
        "WHERE (from_id = :r AND to_id = :i) OR (from_id = :i AND to_id = :r)",
        r=requisition,
        i=iwp_id,
    )
    assert linked == 1


def test_an_unknown_iwp_for_a_requisition_is_one_error_line(cli: Cli) -> None:
    result = cli.req("raise-labor", *LABOR, *DATES, "--for", "NO-IWP")
    assert result.exit_code == 1
    assert result.stderr.splitlines() == ["error: no IWP NO-IWP"]


def test_approve_as_the_superuser_opens_the_work_order(cli: Cli) -> None:
    key = raise_labor(cli)
    lines = cli.ok(cli.req("approve", key, who="user:sue"))
    assert lines == [f"approve {key}  version 4"]
    assert cli.scalar("SELECT COUNT(*) FROM cur_core_record WHERE key = 'P123-WO-0001'") == 1


def test_a_plain_users_approve_is_forbidden(cli: Cli) -> None:
    key = raise_labor(cli)
    result = cli.req("approve", key, who="user:rob")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: forbidden")
    assert "Traceback" not in result.output


def test_reject_and_cancel_need_a_reason(cli: Cli) -> None:
    key = raise_labor(cli)
    assert cli.req("reject", key).exit_code == 2
    assert cli.req("cancel", key).exit_code == 2


def test_reject_with_a_reason_prints_the_version(cli: Cli) -> None:
    key = raise_labor(cli)
    lines = cli.ok(cli.req("reject", key, "--reason", "Duplicate", who="user:sue"))
    assert lines == [f"reject {key}  version 4"]


def test_a_stale_expected_version_is_refused(cli: Cli) -> None:
    key = raise_labor(cli)
    result = cli.req("approve", key, "--expected-version", "1", who="user:sue")
    assert result.exit_code == 1
    assert result.stderr.startswith("error: ")
    assert "Traceback" not in result.output


def test_an_unknown_requisition_key_is_one_error_line(cli: Cli) -> None:
    result = cli.req("approve", "P123-REQ-LAB-9999", who="user:sue")
    assert result.exit_code == 1
    assert result.stderr.splitlines() == ["error: no requisition P123-REQ-LAB-9999"]


def test_an_unknown_work_order_key_is_one_error_line(cli: Cli) -> None:
    result = cli.wo("close", "P123-WO-9999")
    assert result.exit_code == 1
    assert result.stderr.splitlines() == ["error: no work order P123-WO-9999"]


def test_edit_with_no_field_is_a_usage_error(cli: Cli) -> None:
    key = raise_labor(cli)
    result = cli.req("edit", key)
    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_edit_changes_a_field_and_prints_the_version(cli: Cli) -> None:
    key = raise_labor(cli)
    lines = cli.ok(cli.req("edit", key, "--headcount", "8"))
    assert lines == [f"edit {key}  version 3"]


def test_schedule_assign_start_complete_and_close_walk_one_work_order_to_closed(cli: Cli) -> None:
    key = raise_labor(cli)
    work = approve_and_key(cli, key)
    steps = [
        ("schedule", "--start", "2026-11-02", "--finish", "2026-11-13", "--hours", "48.0"),
        ("assign", "--to", "user:uma"),
        ("start",),
        ("complete", "--hours", "50.0"),
        ("close",),
    ]
    versions = []
    for verb, *options in steps:
        lines = cli.ok(cli.wo(verb, work, *options))
        assert len(lines) == 1
        prefix, version = lines[0].split("  version ")
        assert prefix == f"{verb} {work}"
        versions.append(int(version))
    assert versions == sorted(set(versions)), "each move bumps the version"
    assert cli.scalar("SELECT status FROM cur_core_record WHERE key = :k", k=work) == "Closed"


def test_help_lists_the_write_verbs_of_both_groups(cli: Cli) -> None:
    req_help = cli.run("req", "--help").stdout
    wo_help = cli.run("wo", "--help").stdout
    for verb in (
        "raise-labor",
        "raise-material",
        "raise-general",
        "raise-scaffold",
        "edit",
        "approve",
        "reject",
        "cancel",
    ):
        assert verb in req_help
    for verb in ("schedule", "assign", "start", "complete", "close"):
        assert verb in wo_help
