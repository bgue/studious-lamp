"""`tl checklist` (P2-INSP-T05): the write verbs and the reads.

The ledger is made by ``insp_world.InspWorld`` (loaded by path, as ``test_cli_punch.py`` loads
``punch_world``); no projection is written. Writes run with ``--actor`` on a dev ledger file. Reads
run signed in as the person they name, so the viewer is that person's.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from auth_support import sign_in
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli import checklist_write
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
PASSWORD = "correct horse battery"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
MAX_FILE = 256 * 1024


def _load(name: str) -> ModuleType:
    """A helper of the quality module tests, loaded by path (once)."""
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_world() -> ModuleType:
    """``insp_world`` (it imports ``punch_world``, which is loaded first)."""
    _load("punch_world")
    return _load("insp_world")


QUESTIONS: list[dict[str, object]] = load_world().QUESTIONS


class Cli:
    """``tl --db DB checklist ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None) -> Result:
        result = CliRunner().invoke(
            app, ["--db", str(self.db), "checklist", *argv], env=env or self.env
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

    def ls(self, *argv: str, who: str = "uma") -> tuple[str, list[str]]:
        """The header line and the data lines of ``ls``."""
        result = self.read(who, "ls", "--project", PROJECT, *argv)
        assert result.exit_code == 0, result.output
        lines = result.output.splitlines()
        return lines[0], lines[1:]

    def keys(self, *argv: str, who: str = "uma") -> list[str]:
        _, lines = self.ls(*argv, who=who)
        return [line.split()[0] for line in lines]

    def verb(self, verb: str, key: str, who: str, *extra: str) -> Result:
        return self.run(verb, key, "--project", PROJECT, "--actor", f"user:{who}", *extra)

    def question_file(self, name: str, questions: object) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(questions), encoding="utf-8")
        return path


def _disabled_account(world: ModuleType, name: str) -> None:
    """A disabled account: it holds no module word, so its reads are refused (module_roles 1)."""
    with open_uow(world.db) as uow:
        view = accounts.create_account(
            uow,
            username=name,
            display_name=name.title(),
            kind="person",
            roles=["user"],
            password=prepare_password(PASSWORD, username=name),
            by="svc:test",
        )
    with open_uow(world.db) as uow:
        accounts.disable(uow, account_id=view.account_id, by="svc:test", reason="test")


@pytest.fixture
def cli(tmp_path: Path) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_world().InspWorld(target)
    world.people()
    _disabled_account(world, "nan")
    yield Cli(path, tmp_path, world)


# --- 1. create, edit, publish, revise, retire -----------------------------------------------------


def test_create_edit_publish_revise_retire_move_the_states(cli: Cli) -> None:
    questions = cli.question_file("q.json", QUESTIONS)
    created = cli.run(
        "create",
        "--project",
        PROJECT,
        "--title",
        "Hydrotest pre-check",
        "--discipline",
        "piping",
        "--questions-file",
        str(questions),
        "--actor",
        "user:uma",
    )
    assert created.exit_code == 0, created.output
    assert re.fullmatch(r"created P123-CHK-0001  version \d+\n", created.output)
    first = "P123-CHK-0001"

    edited = cli.verb("edit", first, "uma", "--title", "Hydrotest pre-check v2")
    assert edited.exit_code == 0, edited.output
    assert re.fullmatch(r"edited P123-CHK-0001  version \d+\n", edited.output)

    published = cli.verb("publish", first, "sue")
    assert published.exit_code == 0, published.output
    assert re.fullmatch(r"published P123-CHK-0001  version \d+\n", published.output)
    assert cli.keys("--state", "Published") == [first]

    revised = cli.verb("revise", first, "sue")
    assert revised.exit_code == 0, revised.output
    assert re.fullmatch(r"revised P123-CHK-0002  version \d+\n", revised.output)
    # the old one stays Published until the new one publishes
    assert cli.keys("--state", "Published") == [first]
    assert cli.keys("--state", "Draft") == ["P123-CHK-0002"]

    assert cli.verb("publish", "P123-CHK-0002", "sue").exit_code == 0
    assert cli.keys("--state", "Published") == ["P123-CHK-0002"]
    assert cli.keys("--state", "Retired") == [first]

    third = cli.run("create", "--project", PROJECT, "--title", "Spare", "--actor", "user:uma")
    assert third.exit_code == 0, third.output
    retired = cli.verb("retire", "P123-CHK-0003", "sue")
    assert retired.exit_code == 0, retired.output
    assert re.fullmatch(r"retired P123-CHK-0003  version \d+\n", retired.output)
    assert "P123-CHK-0003" in cli.keys("--state", "Retired")


def test_an_invalid_question_file_is_the_publish_refusal(cli: Cli) -> None:
    broken = [{"id": "q1", "text": "Gauge fitted?", "kind": "nonsense"}]
    made = cli.run(
        "create",
        "--project",
        PROJECT,
        "--title",
        "Broken",
        "--questions-file",
        str(cli.question_file("bad.json", broken)),
        "--actor",
        "user:uma",
    )
    assert made.exit_code == 0, made.output
    refused = cli.verb("publish", "P123-CHK-0001", "sue")
    assert refused.exit_code == 1
    assert refused.output.startswith("error: the question list cannot be published: ")


def test_an_oversized_question_file_is_refused_before_it_is_read(cli: Cli) -> None:
    big = cli.tmp / "big.json"
    big.write_bytes(b" " * (MAX_FILE + 1))
    result = cli.run(
        "create",
        "--project",
        PROJECT,
        "--title",
        "Big",
        "--questions-file",
        str(big),
        "--actor",
        "user:uma",
    )
    assert result.exit_code == 1
    assert "error: questions file is too large" in result.output


def test_a_published_checklist_refuses_edit(cli: Cli) -> None:
    cli.world.checklist(title="Hydrotest pre-check")
    result = cli.verb("edit", "P123-CHK-0001", "uma", "--title", "Changed")
    assert result.exit_code == 1
    assert result.output == (
        "error: a checklist that is Published does not take EditChecklist; it needs Draft\n"
    )


# --- 2. ls filters, show -----------------------------------------------------------------


def test_ls_filters_and_total(cli: Cli) -> None:
    cli.world.checklist(title="Pipe", discipline="piping")
    cli.world.checklist(title="Cable", discipline="electrical", publish=False)
    header, rows = cli.ls()
    assert header == "checklists: 2 of 2"
    assert len(rows) == 2
    assert cli.ls("--discipline", "piping")[0] == "checklists: 1 of 1"
    assert cli.ls("--state", "Draft")[0] == "checklists: 1 of 1"
    assert cli.ls("--limit", "1")[0] == "checklists: 1 of 2"
    bad = cli.read("uma", "ls", "--project", PROJECT, "--state", "Open")
    assert bad.exit_code == 2


def test_show_prints_the_question_table_and_no_id(cli: Cli) -> None:
    cli.world.checklist(title="Pipe", discipline="piping")
    result = cli.read("uma", "show", "P123-CHK-0001", "--project", PROJECT)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "checklist P123-CHK-0001"
    assert "state  Published" in lines
    header = lines.index("id  text  kind  required  fails when")
    table = lines[header + 1 :]
    assert table[0] == "q1  Gauge fitted?  yes_no_na  yes  no"
    assert table[1] == "q2  Label legible?  yes_no_na  no  no"
    assert len(table) == 3


def test_an_unknown_key_is_no_checklist(cli: Cli) -> None:
    shown = cli.read("uma", "show", "P123-CHK-9999", "--project", PROJECT)
    assert shown.exit_code == 1
    assert "error: no checklist P123-CHK-9999" in shown.output
    edited = cli.verb("edit", "P123-CHK-9999", "uma", "--title", "x")
    assert edited.exit_code == 1
    assert "error: no checklist P123-CHK-9999" in edited.output


# --- 4. access words ---------------------------------------------------------------------


def test_a_viewer_is_refused_the_write_verbs(cli: Cli) -> None:
    created = cli.run("create", "--project", PROJECT, "--title", "x", "--actor", "user:vera")
    assert created.exit_code == 1
    assert created.output.startswith("error: forbidden: ")


def test_a_user_is_refused_publish_and_retire(cli: Cli) -> None:
    cli.world.checklist(publish=False)
    for verb in ("publish", "retire"):
        result = cli.verb(verb, "P123-CHK-0001", "uma")
        assert result.exit_code == 1, verb
        assert result.output.startswith("error: forbidden: "), verb


def test_an_actor_without_quality_view_is_refused_the_reads(cli: Cli) -> None:
    cli.world.checklist()
    listed = cli.run("ls", "--project", PROJECT, "--actor", "user:nan")
    assert listed.exit_code == 1
    assert listed.output.startswith("error: forbidden: ")
    shown = cli.run("show", "P123-CHK-0001", "--project", PROJECT, "--actor", "user:nan")
    assert shown.exit_code == 1
    assert shown.output.startswith("error: forbidden: ")


def test_a_checklist_write_runs_its_handler_as_the_acting_person(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No refusal names a record here, so the test spies on the viewer the handler runs under: it
    # must be the actor's, not the process's (LOWEST on a dev ledger).
    seen: list[cf.Viewer] = []
    original = checklist_write._handler

    def spy(model: Any) -> Any:
        handler = original(model)

        def run(uow: Any, command: Any) -> Any:
            seen.append(cf.current_viewer())
            return handler(uow, command)

        return run

    monkeypatch.setattr(checklist_write, "_handler", spy)
    created = cli.run("create", "--project", PROJECT, "--title", "Spy", "--actor", "user:uma")
    assert created.exit_code == 0, created.output
    with open_uow(cli.world.db, readonly=True) as uow:
        expected = cf.viewer_for_actor(uow.conn(), "user:uma")
    assert seen == [expected]
    assert expected != cf.LOWEST


# --- 5. help ------------------------------------------------------------------------------


def test_tl_help_lists_checklist() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert re.search(r"^[│ ]*checklist\s", result.output, re.MULTILINE), result.output
