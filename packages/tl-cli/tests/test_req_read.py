"""`tl req ls|show` and `tl wo ls|show` (P2-I4A-T04d), on a copy of a ledger built by the module's
commands: the requisitions world (people, standards editions), one scope item and one IWP made by
the awp module. Nothing here writes a projection; the records come from the commands.

``--db`` is the root option, so it goes before the group: ``tl --db X req ...``.
"""

from __future__ import annotations

import atexit
import functools
import importlib.util
import re
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
IWP_TITLE = "Rack 12 piping"
LABOR_KEY = "P123-REQ-LAB-0001"
MATERIAL_KEY = "P123-REQ-MAT-0001"
GENERAL_KEY = "P123-REQ-GEN-0001"
WORK_ORDER_KEY = "P123-WO-0001"
HEX_ID = re.compile(r"[0-9a-f]{32}")


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
    work = Path(tempfile.mkdtemp(prefix="req-read-seed-"))
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

    def req(self, verb: str, *argv: str, who: str = "user:uma", project: str = PROJECT) -> Result:
        return self.run("req", verb, *argv, "--project", project, "--actor", who)

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


@pytest.fixture
def statements() -> Iterator[list[str]]:
    """Every SQL statement the CLI runs while the test runs (all engines)."""
    seen: list[str] = []

    def listen(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", listen)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", listen)


LABOR = ("--subject", "Six pipefitters", "--craft", "Pipefitter", "--headcount", "6")
DATES = ("--start", "2026-11-02", "--end", "2026-11-13")


def raise_labor(cli: Cli, *more: str) -> str:
    """Raise a labour requisition as ``uma``; returns its key."""
    line = cli.ok(cli.req("raise-labor", *LABOR, *DATES, *more))[0]
    assert line.startswith(f"raised {LABOR_KEY}  version ")
    return LABOR_KEY


def iwp_number(cli: Cli) -> str:
    """The number of the one IWP the seed made (``tl req ls --for`` names it)."""
    return cli.scalar("SELECT key FROM cur_core_record WHERE type = 'awp.IWP'")


def data_lines(lines: list[str]) -> list[str]:
    """The lines after the count line (``requisitions: <n>`` or ``work orders: <n>``)."""
    return lines[1:]


# --- requisitions: ls -----------------------------------------------------------------------------


def test_req_ls_count_equals_the_data_lines_and_order_is_by_key(cli: Cli) -> None:
    raise_labor(cli)
    cli.ok(cli.req("raise-material", "--subject", "Pipe", "--line", "P123-ITEM-0001:12:EA"))
    cli.ok(cli.req("raise-general", "--subject", "Crane", "--type", "crane_lift"))
    lines = cli.ok(cli.run("req", "ls", "--project", PROJECT, "--actor", "user:uma"))
    assert lines[0] == "requisitions: 3"
    rows = data_lines(lines)
    assert len(rows) == 3
    keys = [row.split("  ")[0] for row in rows]
    assert keys == sorted(keys)
    assert keys == [GENERAL_KEY, LABOR_KEY, MATERIAL_KEY]


def test_req_ls_filters_each_narrow_the_list(cli: Cli) -> None:
    iwp = iwp_number(cli)
    raise_labor(cli, "--for", iwp)
    cli.ok(cli.req("raise-general", "--subject", "Crane", "--type", "crane_lift"))
    base = ("req", "ls", "--project", PROJECT, "--actor", "user:uma")

    def count(*extra: str) -> int:
        return int(cli.ok(cli.run(*base, *extra))[0].split(": ")[1])

    assert count() == 2
    assert count("--kind", "labor") == 1
    assert count("--kind", "general") == 1
    assert count("--kind", "scaffold") == 0
    assert count("--state", "no-such-state") == 0
    assert count("--requester", "user:rob") == 0
    assert count("--requester", "user:uma") == 2
    assert count("--for", iwp) == 1
    assert count("--limit", "1") == 1
    bad = cli.run(*base, "--kind", "bogus")
    assert bad.exit_code == 2
    assert "Traceback" not in bad.output


def test_req_ls_for_an_unknown_iwp_is_one_error_line(cli: Cli) -> None:
    result = cli.run("req", "ls", "--project", PROJECT, "--actor", "user:uma", "--for", "NO-IWP")
    assert result.exit_code == 1
    assert result.output.strip() == "error: no record NO-IWP"


# --- requisitions: show ---------------------------------------------------------------------------


def test_req_show_labour_prints_its_fields_serves_and_no_work_order(cli: Cli) -> None:
    iwp = iwp_number(cli)
    raise_labor(cli, "--for", iwp)
    lines = cli.ok(cli.run("req", "show", LABOR_KEY, "--project", PROJECT, "--actor", "user:uma"))
    assert lines[0] == f"requisition {LABOR_KEY}"
    assert f"serves {iwp}" in lines
    assert "approved by -" in lines
    assert "  craft  Pipefitter" in lines
    assert "  headcount  6" in lines
    assert lines[-1] == "work order -"
    kind_fields = [line.split("  ")[1] for line in lines if line.startswith("  ")]
    assert kind_fields == sorted(kind_fields)


def test_req_show_general_prints_its_type_and_serves_none(cli: Cli) -> None:
    cli.ok(cli.req("raise-general", "--subject", "Crane", "--type", "crane_lift"))
    lines = cli.ok(cli.run("req", "show", GENERAL_KEY, "--project", PROJECT, "--actor", "user:uma"))
    assert f"requisition {GENERAL_KEY}" in lines
    assert "serves -" in lines
    assert "  general_type  crane_lift" in lines
    assert lines[-1] == "work order -"


def test_req_show_after_approve_names_the_work_order(cli: Cli) -> None:
    raise_labor(cli)
    cli.ok(cli.req("approve", LABOR_KEY, who="user:sue"))
    lines = cli.ok(cli.run("req", "show", LABOR_KEY, "--project", PROJECT, "--actor", "user:uma"))
    assert lines[-1] == f"work order {WORK_ORDER_KEY}"
    assert "approved by user:sue" in lines


def test_an_unknown_and_another_projects_requisition_print_the_same_error(cli: Cli) -> None:
    raise_labor(cli)
    other_key = "P999-REQ-GEN-0001"
    cli.ok(cli.req("raise-general", "--subject", "Crane", "--type", "crane_lift", project="P999"))
    shown = cli.run("req", "show", other_key, "--project", "P999", "--actor", "user:uma")
    assert shown.exit_code == 0 and shown.output.splitlines()[0] == f"requisition {other_key}"
    unknown_key = "P123-REQ-LAB-9999"
    unknown = cli.run("req", "show", unknown_key, "--project", PROJECT, "--actor", "user:uma")
    other = cli.run("req", "show", other_key, "--project", PROJECT, "--actor", "user:uma")
    assert unknown.exit_code == 1 and other.exit_code == 1
    assert unknown.output == f"error: no requisition {unknown_key}\n"
    assert other.output == f"error: no requisition {other_key}\n"
    assert unknown.output.replace(unknown_key, "KEY") == other.output.replace(other_key, "KEY")


# --- work orders: ls and show ---------------------------------------------------------------------


def approve_and_schedule(cli: Cli) -> None:
    raise_labor(cli)
    cli.ok(cli.req("approve", LABOR_KEY, who="user:sue"))
    cli.ok(
        cli.wo(
            "schedule",
            WORK_ORDER_KEY,
            "--start",
            "2026-11-02",
            "--finish",
            "2026-11-13",
            "--hours",
            "48.0",
        )
    )


def test_wo_ls_after_approve_and_schedule(cli: Cli) -> None:
    approve_and_schedule(cli)
    lines = cli.ok(cli.run("wo", "ls", "--project", PROJECT, "--actor", "user:sue"))
    assert lines[0] == "work orders: 1"
    rows = data_lines(lines)
    assert len(rows) == 1
    fields = rows[0].split("  ")
    assert fields[0] == WORK_ORDER_KEY
    assert fields[4:] == ["2026-11-02", "2026-11-13", "48.0"]


def test_wo_ls_filters_narrow(cli: Cli) -> None:
    approve_and_schedule(cli)
    base = ("wo", "ls", "--project", PROJECT, "--actor", "user:sue")
    assert cli.ok(cli.run(*base, "--assigned", "user:uma"))[0] == "work orders: 0"
    assert cli.ok(cli.run(*base, "--state", "no-such-state"))[0] == "work orders: 0"
    assert cli.ok(cli.run(*base, "--limit", "1"))[0] == "work orders: 1"


def test_wo_show_after_approve_and_schedule(cli: Cli) -> None:
    approve_and_schedule(cli)
    lines = cli.ok(
        cli.run("wo", "show", WORK_ORDER_KEY, "--project", PROJECT, "--actor", "user:sue")
    )
    assert lines[0] == f"work order {WORK_ORDER_KEY}"
    assert f"requisition {LABOR_KEY}" in lines
    assert "planned 2026-11-02 to 2026-11-13" in lines
    assert "actual - to -" in lines
    assert "hours 48.0 planned  - actual" in lines


def test_wo_show_an_unknown_key_is_one_error_line(cli: Cli) -> None:
    result = cli.run("wo", "show", "P123-WO-9999", "--project", PROJECT, "--actor", "user:sue")
    assert result.exit_code == 1
    assert result.output == "error: no work order P123-WO-9999\n"


# --- access and output ----------------------------------------------------------------------------


def test_an_actor_without_the_view_word_is_refused_before_any_requisition_is_read(
    cli: Cli, statements: list[str]
) -> None:
    raise_labor(cli)
    statements.clear()
    refused = cli.run("req", "ls", "--project", PROJECT, "--actor", "agent:nobody")
    assert refused.exit_code == 1
    assert refused.output.startswith("error: forbidden: ")
    touched = [s for s in statements if "cur_requisitions_" in s or "v_requisitions_" in s]
    assert touched == [], "no requisition table is read before the access check"


def test_no_read_output_holds_an_id_or_a_traceback(cli: Cli) -> None:
    iwp = iwp_number(cli)
    raise_labor(cli, "--for", iwp)
    cli.ok(cli.req("approve", LABOR_KEY, who="user:sue"))
    outputs = [
        cli.run("req", "ls", "--project", PROJECT, "--actor", "user:uma").output,
        cli.run("req", "show", LABOR_KEY, "--project", PROJECT, "--actor", "user:uma").output,
        cli.run("wo", "ls", "--project", PROJECT, "--actor", "user:sue").output,
        cli.run("wo", "show", WORK_ORDER_KEY, "--project", PROJECT, "--actor", "user:sue").output,
        cli.run("req", "show", "P123-REQ-LAB-9999", "--project", PROJECT).output,
    ]
    for text_out in outputs:
        assert "Traceback" not in text_out
        assert HEX_ID.search(text_out) is None, text_out
