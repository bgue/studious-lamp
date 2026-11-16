"""`tl gastest record|ls` and `tl permit export --gas-tests` (P2-PTW-T06b).

The ledger is made by ``permit_world.World``. ``record`` runs as a person (signed in, with
``--actor`` naming the same person) and the reads run as the viewer they name, so the hidden filter
is the one the reads use. The clock is ``tl_core.util.utcnow`` and stands at the world's start.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from auth_support import sign_in
from tl_adapters.db import DbTarget, as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core import util
from tl_mod_permits import views
from tl_mod_permits.iso_views import gas_export_rows, gas_tests_for
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
OTHER = "P456"
PASSWORD = "correct horse battery"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
GAS_KEY = re.compile(r"^P123-GAS-\d{4}$")


def load_world() -> ModuleType:
    """The ``permit_world`` helper of the permits module tests, loaded by path."""
    name = "permit_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "permits" / "tests" / "permit_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    """The one clock the CLI and the handlers read (``tl_core.util.utcnow``)."""

    def __init__(self, at: Any) -> None:
        self.at = at


class Cli:
    """``tl --db DB gastest|permit ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: DbTarget, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world.World(db)
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def invoke(self, group: str, argv: tuple[str, ...], env: dict[str, str]) -> Result:
        result = CliRunner().invoke(app, ["--db", str(self.db), group, *argv], env=env)
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert "Traceback" not in result.output
        assert not HEX32.search(result.output), result.output
        return result

    def as_person(self, name: str) -> dict[str, str]:
        """An environment signed in as ``name`` (its own session file)."""
        env = {
            "TL_ENV": "dev",
            "TL_DB": str(self.db),
            "TL_SESSION_FILE": str(self.tmp / f"session-{name}.json"),
        }
        sign_in(env, name, PASSWORD)
        return env

    def record(self, name: str, key: str, *argv: str) -> Result:
        """``gastest record KEY --project P --actor user:NAME ...`` signed in as ``name``."""
        return self.invoke(
            "gastest",
            ("record", key, "--project", PROJECT, "--actor", f"user:{name}", *argv),
            self.as_person(name),
        )

    def ls(self, name: str, key: str, *argv: str) -> Result:
        return self.invoke(
            "gastest",
            ("ls", key, "--project", PROJECT, "--actor", f"user:{name}", *argv),
            self.as_person(name),
        )

    def export(self, name: str, *argv: str) -> Result:
        return self.invoke(
            "permit",
            ("export", "--project", PROJECT, "--actor", f"user:{name}", *argv),
            self.as_person(name),
        )


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[Clock]:
    """The clock stands at the world's start (07:00 UTC)."""
    fixed = Clock(load_world().START)
    monkeypatch.setattr(util, "utcnow", lambda: fixed.at)
    yield fixed


@pytest.fixture
def cli(tmp_path: Path, clock: Clock) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    made = Cli(path, tmp_path, load_world())
    made.world.people()
    yield made


def key_of(cli: Cli, record: str) -> str:
    return str(cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))


def rows_of(result: Result) -> list[list[str]]:
    """The cells of each data row `ls` printed (the header is checked by the caller)."""
    lines = result.output.splitlines()
    return [line.split("  ") for line in lines[1:]]


def gas_keys(result: Result) -> list[str]:
    assert result.exit_code == 0, result.output
    return [cells[0] for cells in rows_of(result)]


def active_hot_work(cli: Cli) -> str:
    """A hot-work permit made Active: its issue needs a passing gas test first (seeded)."""
    permit = cli.world.approved("hot_work", area="A1")
    cli.world.gas_test(permit, result="pass")
    cli.world.issue(permit)
    return permit


# --- record -----------------------------------------------------------------------------------


def test_record_prints_pass_and_fail_and_a_failing_test_suspends_an_active_permit(cli: Cli) -> None:
    permit = active_hot_work(cli)
    key = key_of(cli, permit)

    passing = cli.record("pam", key, "--instrument", "Gas meter 7", "--o2", "20.9", "--lel", "0")
    assert passing.exit_code == 0, passing.output
    assert re.fullmatch(r"recorded P123-GAS-\d{4}  pass\n", passing.output), passing.output

    failing = cli.record("pam", key, "--instrument", "Gas meter 7", "--o2", "18")
    assert failing.exit_code == 0, failing.output
    assert re.fullmatch(
        rf"recorded P123-GAS-\d{{4}}  fail\npermit {key} suspended\n", failing.output
    ), failing.output
    assert cli.world.state(permit) == "Suspended"


def test_ls_lists_the_tests_newest_first_with_their_readings(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    first = cli.record("pam", key, "--instrument", "Meter A", "--o2", "20.9", "--note", "clear")
    second = cli.record("pam", key, "--instrument", "Meter B", "--h2s", "12", "--co", "4")
    assert first.exit_code == 0 and second.exit_code == 0, second.output

    listed = cli.ls("uma", key, "--project", PROJECT)
    lines = listed.output.splitlines()
    assert lines[0] == "key  taken  instrument  tester  O2  LEL  H2S  CO  result  note", lines
    keys = gas_keys(listed)
    assert len(keys) == 3 and all(GAS_KEY.match(k) for k in keys)
    assert keys[0] > keys[1]  # the later entry, at the same taken time, is the first row
    assert "Meter B" in lines[1] and "12" in lines[1] and "4" in lines[1]
    assert "Meter A" in lines[2] and lines[2].split("  ")[-1] == "clear"


# --- time, usage and refusals ---------------------------------------------------------------------


def test_a_past_taken_at_orders_by_time_not_by_entry(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    now_test = cli.record("pam", key, "--instrument", "Meter A", "--o2", "20.9")
    assert now_test.exit_code == 0, now_test.output
    earlier = cli.record(
        "pam",
        key,
        "--instrument",
        "Meter B",
        "--o2",
        "20.9",
        "--taken-at",
        "2026-12-01T06:00:00+00:00",
    )
    assert earlier.exit_code == 0, earlier.output

    rows = rows_of(cli.ls("uma", key, "--project", PROJECT))
    # The seeded test and the first one are taken at 07:00; the past one at 06:00, so it is last.
    assert [row[2] for row in rows] == ["Meter A", "-", "Meter B"]
    assert rows[2][1] == "2026-12-01 06:00 UTC"


def test_a_naive_taken_at_is_a_usage_error(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    result = cli.record(
        "pam", key, "--instrument", "Meter", "--o2", "20.9", "--taken-at", "2026-12-01T06:00:00"
    )
    assert result.exit_code == 2, result.output
    assert "offset" in result.output


def test_a_reading_out_of_range_is_refused_and_nothing_is_stored(cli: Cli) -> None:
    permit = active_hot_work(cli)
    key = key_of(cli, permit)
    before = cli.world.count("events")
    result = cli.record("pam", key, "--instrument", "Meter", "--o2", "150")
    assert result.exit_code == 2, result.output
    assert "between 0 and 100" in result.output
    assert cli.world.count("events") == before


def test_a_test_with_no_reading_is_refused(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    result = cli.record("pam", key, "--instrument", "Meter")
    assert result.exit_code == 2, result.output
    assert "at least one reading" in result.output


def test_a_test_dated_in_the_future_is_the_handler_refusal(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    result = cli.record(
        "pam",
        key,
        "--instrument",
        "Meter",
        "--o2",
        "20.9",
        "--taken-at",
        "2026-12-02T00:00:00+00:00",
    )
    assert result.exit_code == 1, result.output
    assert result.output == "error: a gas test cannot be dated in the future\n"


def test_an_empty_list_prints_no_gas_tests(cli: Cli) -> None:
    key = key_of(cli, cli.world.request("uma", area="A1"))
    result = cli.ls("uma", key, "--project", PROJECT)
    assert result.exit_code == 0, result.output
    assert result.output == "no gas tests\n"


# --- hidden permits -------------------------------------------------------------------------------


def test_a_hidden_permit_reads_as_missing_to_a_reader_who_cannot_see_it(cli: Cli) -> None:
    secret = cli.world.hidden_record()
    hidden = cli.world.request("dora", for_record_id=secret)
    cli.world.person("cora", ("user", "document_controller"), grant="superuser")
    cli.world.call("cora", "ApprovePermit", permit=hidden)
    cli.world.issue(hidden, who="cora")
    hidden_key = key_of(cli, hidden)
    cli.world.gas_test(hidden, result="pass")

    # The cleared reader sees the permit and its test.
    seen = cli.ls("dora", hidden_key, "--project", PROJECT)
    assert len(gas_keys(seen)) == 1, seen.output

    # The reader who cannot see it gets the answer of a key that does not exist.
    missing = cli.ls("uma", hidden_key, "--project", PROJECT)
    assert missing.exit_code == 1, missing.output
    assert missing.output == f"error: no permit {hidden_key}\n"
    unknown = cli.ls("uma", "P123-PTW-0999", "--project", PROJECT)
    assert unknown.output == "error: no permit P123-PTW-0999\n"

    refused = cli.record("uma", hidden_key, "--instrument", "Meter", "--o2", "20.9")
    assert refused.exit_code == 1, refused.output
    assert refused.output == f"error: no permit {hidden_key}\n"


# --- export ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["csv", "jsonl"])
def test_export_gas_tests_is_gas_export_rows_of_the_same_permits(cli: Cli, fmt: str) -> None:
    visible = active_hot_work(cli)
    cli.world.active("general", area="A2")  # a permit with no gas test
    key = key_of(cli, visible)
    assert cli.record("pam", key, "--instrument", "Meter", "--o2", "18").exit_code == 0

    with open_uow(cli.world.db, readonly=True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:uma")
        permits = views.permit_list(
            uow.conn(), "project:P123", now=cli.world.at, viewer=viewer
        ).rows
        tests = [
            test for row in permits for test in gas_tests_for(uow.conn(), row.id, viewer=viewer)
        ]
    assert len(tests) == 2

    result = cli.export("uma", "--format", fmt, "--gas-tests")
    assert result.exit_code == 0, result.output
    assert result.output == gas_export_rows(tests, fmt)


def test_export_gas_tests_holds_no_row_of_a_hidden_permit(cli: Cli) -> None:
    active_hot_work(cli)
    secret = cli.world.hidden_record()
    hidden = cli.world.request("dora", for_record_id=secret)
    hidden_test = key_of(cli, cli.world.gas_test(hidden, result="pass"))

    as_uma = cli.export("uma", "--format", "csv", "--gas-tests")
    assert as_uma.exit_code == 0, as_uma.output
    assert hidden_test not in as_uma.output
    assert len(as_uma.output.splitlines()) == 2  # one header, one row (the seeded test)

    as_dora = cli.export("dora", "--format", "csv", "--gas-tests")
    assert hidden_test in as_dora.output


# --- access ---------------------------------------------------------------------------------------


def test_a_person_without_the_write_word_cannot_record(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    count = "SELECT count(*) FROM events WHERE event_type = 'GasTest.Recorded'"
    before = cli.world.scalar(count)
    result = cli.record("vera", key, "--instrument", "Meter", "--o2", "20.9")
    assert result.exit_code == 1, result.output
    assert result.output.startswith("error: forbidden: "), result.output
    assert cli.world.scalar(count) == before


def test_an_actor_without_permits_view_is_refused_before_any_read(cli: Cli) -> None:
    key = key_of(cli, active_hot_work(cli))
    for argv in (("record", key, "--instrument", "Meter", "--o2", "20.9"), ("ls", key)):
        result = cli.invoke(
            "gastest",
            (*argv, "--project", PROJECT, "--actor", "agent:nobody"),
            cli.env,
        )
        assert result.exit_code == 1, result.output
        assert result.output.startswith("error: forbidden: "), result.output
