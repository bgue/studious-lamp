"""`tl punch` (P2-PUNCH-T02): the write verbs and the reads.

The ledger is made by ``punch_world.World`` (loaded by path, as ``test_cli_awp.py`` loads
``awp_world``); no projection is written. Writes run with ``--actor`` on a dev ledger file. Reads
run signed in as the person they name, so the viewer is that person's (a dev file with no session
reads as the file owner, which sees restricted items).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from auth_support import sign_in
from tl_adapters.db import as_target, create_schema
from tl_cli import punch_read
from tl_cli.main import app
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
OTHER = "P456"
PASSWORD = "correct horse battery"
IWP = "P123-IWP-0001"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")


def load_world() -> ModuleType:
    """The ``punch_world`` helper of the quality module tests, loaded by path."""
    name = "punch_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / "punch_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Cli:
    """``tl --db DB punch ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None) -> Result:
        result = CliRunner().invoke(
            app, ["--db", str(self.db), "punch", *argv], env=env or self.env
        )
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

    def read(self, name: str, *argv: str) -> Result:
        """A read as ``name``: signed in, and ``--actor`` names that same person."""
        return self.run(*argv, "--actor", f"user:{name}", env=self.as_person(name))

    def ls(self, *argv: str, who: str = "uma") -> tuple[int, list[str]]:
        """The total and the data lines of ``ls`` (the lines after the total line)."""
        result = self.read(who, "ls", "--project", PROJECT, *argv)
        assert result.exit_code == 0, result.output
        lines = result.output.splitlines()
        total = int(lines[0].removeprefix("punch items: "))
        return total, lines[1:]

    def raise_item(self, who: str = "uma", subject: str = "Guard missing", **more: str) -> str:
        """Raise an item as ``who``; the key it prints."""
        args = ["raise", "--project", PROJECT, "--subject", subject, "--actor", f"user:{who}"]
        for name, value in more.items():
            args += [f"--{name.rstrip('_').replace('_', '-')}", value]
        result = self.run(*args)
        assert result.exit_code == 0, result.output
        return result.output.split()[1]

    def state_verb(self, verb: str, key: str, who: str, *extra: str) -> Result:
        return self.run(verb, key, "--project", PROJECT, "--actor", f"user:{who}", *extra)


@pytest.fixture
def cli(tmp_path: Path) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_world().World(target)
    world.people()
    world.record("awp.IWP", IWP)
    yield Cli(path, tmp_path, world)


def show_shape(key: str, state: str, **parts: str) -> list[str]:
    """The exact `show` lines as patterns: ``parts`` override the defaults of the open item."""
    values = {
        "subject": "Guard missing",
        "category": "B",
        "area": "-",
        "system": "-",
        "due": "-",
        "assignee": "-",
        "from": "-",
        "cleared": "-  -  -",
        "verified": "-  -",
        "reopened": "0  -",
        "void": "-",
    } | parts
    return [
        f"punch item {key}",
        f"state  {state}",
        f"subject  {values['subject']}",
        f"category  {values['category']}",
        f"area  {values['area']}",
        f"system  {values['system']}",
        f"due  {values['due']}",
        f"assignee  {values['assignee']}",
        "raised by  user:uma",
        f"raised from  {values['from']}",
        f"cleared  {values['cleared']}",
        f"verified  {values['verified']}",
        f"reopened  {values['reopened']}",
        f"void  {values['void']}",
    ]


def show_lines(cli: Cli, key: str, who: str = "uma") -> list[str]:
    result = cli.read(who, "show", key, "--project", PROJECT)
    assert result.exit_code == 0, result.output
    return result.output.splitlines()


def matches(lines: list[str], patterns: list[str]) -> None:
    """Each line fully matches its pattern, and there are no more or fewer lines."""
    assert len(lines) == len(patterns), lines
    for line, pattern in zip(lines, patterns, strict=True):
        assert re.fullmatch(pattern, line), (line, pattern)


# --- raise, edit ----------------------------------------------------------------------------------


def test_raise_prints_the_keys_in_order(cli: Cli) -> None:
    first = cli.run(
        "raise", "--project", PROJECT, "--subject", "Guard missing", "--actor", "user:uma"
    )
    second = cli.run("raise", "--project", PROJECT, "--subject", "Door", "--actor", "user:uma")
    assert re.fullmatch(r"raised P123-PUN-0001  version \d+\n", first.output)
    assert re.fullmatch(r"raised P123-PUN-0002  version \d+\n", second.output)


def test_raise_from_an_iwp_is_shown_as_raised_from(cli: Cli) -> None:
    result = cli.run(
        "raise", "--project", PROJECT, "--subject", "Guard", "--from", IWP, "--actor", "user:uma"
    )
    assert result.exit_code == 0, result.output
    key = result.output.split()[1]
    assert f"raised from  {IWP}" in show_lines(cli, key)


def test_raise_from_unknown_writes_nothing(cli: Cli) -> None:
    before = cli.ls()
    result = cli.run(
        "raise",
        "--project",
        PROJECT,
        "--subject",
        "Guard",
        "--from",
        "P123-IWP-9999",
        "--actor",
        "user:uma",
    )
    assert result.exit_code == 1
    assert "error: no record P123-IWP-9999" in result.output
    assert cli.ls() == before


def test_raise_from_a_hidden_source_is_no_record_for_the_writer(cli: Cli) -> None:
    hidden_id = cli.world.hidden_record()
    hidden_key = cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=hidden_id)
    result = cli.run(
        "raise",
        "--project",
        PROJECT,
        "--subject",
        "Guard",
        "--from",
        str(hidden_key),
        "--actor",
        "user:uma",
    )
    assert result.exit_code == 1
    assert f"error: no record {hidden_key}" in result.output


def test_edit_changes_fields_and_needs_one(cli: Cli) -> None:
    key = cli.raise_item()
    none = cli.state_verb("edit", key, "uma")
    assert none.exit_code == 2
    result = cli.run(
        "edit", key, "--project", PROJECT, "--subject", "Guard fitted", "--actor", "user:uma"
    )
    assert re.fullmatch(rf"edited {key}  version \d+\n", result.output)
    assert "subject  Guard fitted" in show_lines(cli, key)


def test_bad_category_is_a_usage_error(cli: Cli) -> None:
    result = cli.run(
        "raise",
        "--project",
        PROJECT,
        "--subject",
        "Guard",
        "--category",
        "Z",
        "--actor",
        "user:uma",
    )
    assert result.exit_code == 2
    assert "Traceback" not in result.output


# --- state verbs and show -------------------------------------------------------------------------


def test_the_state_verbs_follow_the_life_of_an_item(cli: Cli) -> None:
    key = cli.raise_item(area="L1")
    matches(show_lines(cli, key), show_shape(key, "Open", area="L1"))

    cleared = cli.state_verb("clear", key, "rob", "--note", "Fixed the guard")
    assert re.fullmatch(rf"cleared {key}  version \d+\n", cleared.output)
    matches(
        show_lines(cli, key),
        show_shape(key, "Cleared", area="L1", cleared=r"user:rob  \S+  Fixed the guard"),
    )

    self_verify = cli.state_verb("verify", key, "rob")
    assert self_verify.exit_code == 1
    assert "error: the person who cleared a punch item may not verify it" in self_verify.output

    refused = cli.state_verb("verify", key, "uma")
    assert refused.exit_code == 1
    assert "error: forbidden" in refused.output

    verified = cli.state_verb("verify", key, "sue")
    assert re.fullmatch(rf"verified {key}  version \d+\n", verified.output)
    matches(
        show_lines(cli, key),
        show_shape(
            key,
            "Verified",
            area="L1",
            cleared=r"user:rob  \S+  Fixed the guard",
            verified=r"user:sue  \S+",
        ),
    )


def test_reopen_and_void_need_their_reason_and_void_is_final(cli: Cli) -> None:
    key = cli.raise_item()
    cli.state_verb("clear", key, "rob", "--note", "Fixed")
    assert cli.state_verb("reopen", key, "sue").exit_code == 2
    reopened = cli.state_verb("reopen", key, "sue", "--reason", "Still wet")
    assert reopened.exit_code == 0, reopened.output
    matches(show_lines(cli, key), show_shape(key, "Open", reopened="1  Still wet"))

    assert cli.state_verb("void", key, "sue").exit_code == 2
    voided = cli.state_verb("void", key, "sue", "--reason", "Duplicate")
    assert re.fullmatch(rf"voided {key}  version \d+\n", voided.output)
    matches(
        show_lines(cli, key),
        show_shape(key, "Void", reopened="1  Still wet", void="Duplicate"),
    )
    after = cli.state_verb("clear", key, "rob", "--note", "Late")
    assert after.exit_code == 1
    assert "error: a void punch item accepts no further change" in after.output


def test_a_stale_expected_version_is_refused(cli: Cli) -> None:
    key = cli.raise_item()
    result = cli.state_verb("clear", key, "rob", "--note", "Fixed", "--expected-version", "999")
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Open" in show_lines(cli, key)[1]


def test_an_unknown_key_and_another_projects_key_print_the_same_error(cli: Cli) -> None:
    other = cli.run(
        "raise", "--project", OTHER, "--subject", "Elsewhere", "--actor", "user:uma"
    ).output.split()[1]
    unknown = cli.read("uma", "show", "P123-PUN-0999", "--project", PROJECT)
    foreign = cli.read("uma", "show", other, "--project", PROJECT)
    assert unknown.exit_code == foreign.exit_code == 1
    assert unknown.output == "error: no punch item P123-PUN-0999\n"
    assert foreign.output == f"error: no punch item {other}\n"


# --- reads ----------------------------------------------------------------------------------------


def test_ls_filters_narrow_and_count_the_data_lines(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Frozen(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 6, 1)

    monkeypatch.setattr(punch_read, "date", Frozen)
    cli.raise_item(
        "uma",
        "Guard missing",
        area="L1",
        system="HVAC",
        category="A",
        assignee="user:rob",
        due="2026-01-01",
        from_=IWP,
    )
    cli.raise_item("uma", "Door sealant", area="L2", system="Fire", category="B", due="2099-01-01")
    cli.raise_item("uma", "Paint", area="L1", category="C")

    for argv, expected in (
        ((), 3),
        (("--area", "L1"), 2),
        (("--system", "Fire"), 1),
        (("--category", "A"), 1),
        (("--assignee", "user:rob"), 1),
        (("--overdue",), 1),
        (("--state", "Open"), 3),
        (("--state", "Cleared"), 0),
    ):
        total, rows = cli.ls(*argv)
        assert total == expected, argv
        assert len(rows) == expected, argv
    total, rows = cli.ls("--limit", "2")
    assert (total, len(rows)) == (3, 2)

    assert (
        cli.run("ls", "--project", PROJECT, "--state", "Bogus", "--actor", "user:uma").exit_code
        == 2
    )


def test_ls_hides_a_restricted_source_from_the_reader(cli: Cli) -> None:
    hidden_id = cli.world.hidden_record()
    item = cli.world.raise_item("dora", "Secret follow-up", from_record_id=hidden_id)
    key = cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=item)
    hidden_key = cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=hidden_id)
    listed = cli.read("uma", "ls", "--project", PROJECT)
    assert str(key) not in listed.output
    shown = cli.read("uma", "show", str(key), "--project", PROJECT)
    missing = cli.read("uma", "show", "P123-PUN-0999", "--project", PROJECT)
    assert shown.exit_code == missing.exit_code == 1
    assert shown.output == f"error: no punch item {key}\n"
    assert missing.output == "error: no punch item P123-PUN-0999\n"
    assert str(hidden_key) not in listed.output


def test_no_output_holds_a_hex_id_or_a_traceback(cli: Cli) -> None:
    key = cli.raise_item()
    _, rows = cli.ls()
    for line in [*show_lines(cli, key), *rows]:
        assert not HEX32.search(line)
        assert "Traceback" not in line
