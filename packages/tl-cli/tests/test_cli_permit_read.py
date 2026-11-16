"""`tl permit ls|show|board|export` (P2-PTW-T05): the reads, the viewer and the access word.

The ledger is made by ``permit_world.World`` (loaded by path, as ``test_cli_punch.py`` loads
``punch_world``). Reads run signed in as the person they name. The clock is ``tl_core.util.utcnow``
and stands at the world's start for every read; the lapse test moves it forward.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from auth_support import sign_in
from tl_adapters.db import DbTarget, as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core import util
from tl_mod_permits import views
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
OTHER = "P456"
PASSWORD = "correct horse battery"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
HEADER = "key  subject  state  type  area  holder  valid until  for"


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

    def __init__(self, at: datetime) -> None:
        self.at = at


class Cli:
    """``tl --db DB permit ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: DbTarget, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world.World(db)
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None) -> Result:
        result = CliRunner().invoke(
            app, ["--db", str(self.db), "permit", *argv], env=env or self.env
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


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[Clock]:
    """The clock stands at the world's start (07:00, a shift that ends at 18:00)."""
    start = load_world().START
    fixed = Clock(start)
    monkeypatch.setattr(util, "utcnow", lambda: fixed.at)
    yield fixed


@pytest.fixture
def cli(tmp_path: Path, clock: Clock) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_world()
    made = Cli(path, tmp_path, world)
    made.world.people()
    yield made


def key_of(cli: Cli, record: str) -> str:
    return str(cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))


def ls_keys(result: Result) -> tuple[list[str], str]:
    """The keys of the rows `ls` printed, and its last line (`n of total`)."""
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == HEADER, result.output
    return [line.split("  ")[0] for line in lines[1:-1]], lines[-1]


# --- ls -----------------------------------------------------------------------------------------


def test_ls_shows_both_keys_and_the_total(cli: Cli) -> None:
    requested = cli.world.request("rob", area="A1", holder="Rob")
    issued = cli.world.active("work_at_height", area="A2", holder="Pam Crew")
    both = {key_of(cli, requested), key_of(cli, issued)}

    keys, total = ls_keys(cli.read("uma", "ls", "--project", PROJECT))
    assert set(keys) == both and total == "2 of 2"


def test_ls_filters_by_state_type_area_and_holder_and_limits(cli: Cli) -> None:
    requested = key_of(cli, cli.world.request("rob", area="A1", holder="Rob"))
    issued = key_of(cli, cli.world.active("work_at_height", area="A2", holder="Pam Crew"))
    cases = [
        (("--state", "Active"), [issued]),
        (("--state", "Requested"), [requested]),
        (("--type", "general"), [requested]),
        (("--type", "work_at_height"), [issued]),
        (("--area", "A1"), [requested]),
        (("--area", "A2"), [issued]),
        (("--holder", "Rob"), [requested]),
        (("--holder", "Pam Crew"), [issued]),
    ]
    for argv, expected in cases:
        keys, total = ls_keys(cli.read("uma", "ls", "--project", PROJECT, *argv))
        assert keys == expected and total == f"{len(expected)} of {len(expected)}", argv

    keys, total = ls_keys(cli.read("uma", "ls", "--project", PROJECT, "--limit", "1"))
    assert len(keys) == 1 and total == "1 of 2"


# --- lapse ----------------------------------------------------------------------------------------


def test_a_lapsed_permit_is_shown_lapsed_and_leads_the_board(cli: Cli, clock: Clock) -> None:
    first = key_of(cli, cli.world.active("general", area="A1"))  # valid to 18:00
    clock.at = cli.world.at + timedelta(hours=12)  # 19:00: past that validity
    second = key_of(cli, cli.world.active("general", area="A1"))  # valid to the next shift

    keys, total = ls_keys(cli.read("uma", "ls", "--project", PROJECT, "--state", "Lapsed"))
    assert keys == [first] and total == "1 of 1"

    shown = cli.read("uma", "show", first, "--project", PROJECT)
    assert shown.exit_code == 0, shown.output
    assert re.search(r"^State\s+Lapsed$", shown.output, re.MULTILINE), shown.output

    board = cli.read("uma", "board", "--project", PROJECT).output.splitlines()
    assert board[0] == "Lapsed 1  Suspended 0  Active 1"
    assert board[1] == "area A1"
    assert board[2].startswith(f"{first}  ") and board[2].endswith("  Lapsed")
    assert board[3].startswith(f"{second}  ") and board[3].endswith("  Active")


# --- show -----------------------------------------------------------------------------------------


def test_show_prints_the_detail_lines_and_no_record_id(cli: Cli) -> None:
    key = key_of(cli, cli.world.active("work_at_height", area="A1", holder="Rob"))
    result = cli.read("uma", "show", key, "--project", PROJECT)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == f"permit {key}"
    assert re.search(r"^Area\s+A1$", result.output, re.MULTILINE), result.output
    assert re.search(r"^Holder\s+Rob$", result.output, re.MULTILINE), result.output
    assert re.search(r"^Location\s+Pump room$", result.output, re.MULTILINE), result.output
    assert re.search(r"^Precautions\s+fall_protection, exclusion_zone", result.output, re.MULTILINE)


def test_unknown_hidden_and_other_project_keys_print_the_same_text(cli: Cli) -> None:
    visible = key_of(cli, cli.world.request("uma", area="A1"))
    secret = cli.world.hidden_record()
    hidden = key_of(cli, cli.world.request("dora", for_record_id=secret))

    texts = []
    for key, project in ((hidden, PROJECT), ("P123-PTW-0999", PROJECT), (visible, OTHER)):
        result = cli.read("uma", "show", key, "--project", project)
        assert result.exit_code == 1, result.output
        assert result.output == f"error: no permit {key}\n"
        texts.append(result.output.replace(key, "<KEY>"))
    assert len(set(texts)) == 1

    # The restricted reader sees the same permit as a row of the list, so it is not missing.
    dora = cli.read("dora", "show", hidden, "--project", PROJECT)
    assert dora.exit_code == 0, dora.output


def test_a_hidden_permit_leaves_no_row_and_no_count(cli: Cli) -> None:
    visible = key_of(cli, cli.world.request("uma", area="A1"))
    secret = cli.world.hidden_record()
    # dora requests and cora (a second restricted reader) approves and issues: no self-approval.
    cli.world.person("cora", ("user", "document_controller"), grant="superuser")
    hidden = cli.world.request("dora", for_record_id=secret)
    cli.world.call("cora", "ApprovePermit", permit=hidden)
    cli.world.issue(hidden, who="cora")
    hidden_key = key_of(cli, hidden)

    keys, total = ls_keys(cli.read("uma", "ls", "--project", PROJECT))
    assert keys == [visible] and total == "1 of 1"
    board = cli.read("uma", "board", "--project", PROJECT)
    assert board.exit_code == 0, board.output
    assert board.output.splitlines()[0] == "Lapsed 0  Suspended 0  Active 0"
    assert hidden_key not in board.output

    keys, total = ls_keys(cli.read("dora", "ls", "--project", PROJECT))
    assert set(keys) == {visible, hidden_key} and total == "2 of 2"


# --- export ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["csv", "jsonl"])
def test_export_is_export_rows_of_the_same_list(cli: Cli, fmt: str) -> None:
    cli.world.request("rob", area="A1")
    cli.world.active("work_at_height", area="A2")
    with open_uow(cli.world.db, readonly=True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:uma")
        rows = views.permit_list(uow.conn(), "project:P123", now=cli.world.at, viewer=viewer).rows

    result = cli.read("uma", "export", "--project", PROJECT, "--format", fmt)
    assert result.exit_code == 0, result.output
    assert result.output == views.export_rows(rows, fmt)


def test_a_bad_export_format_is_a_usage_error(cli: Cli) -> None:
    cli.world.request("rob")
    result = cli.read("uma", "export", "--project", PROJECT, "--format", "xml")
    assert result.exit_code == 2, result.output
    assert "csv or jsonl" in result.output


# --- access ---------------------------------------------------------------------------------------


def test_an_actor_without_permits_view_is_refused_before_any_read(cli: Cli) -> None:
    # An actor with no account holds no module word (every account role grants read).
    key = key_of(cli, cli.world.request("rob"))
    reads = [
        ("ls",),
        ("show", key),
        ("show", "P123-PTW-0999"),
        ("board",),
        ("export", "--format", "csv"),
    ]
    for argv in reads:
        result = cli.run(*argv, "--project", PROJECT, "--actor", "agent:nobody")
        assert result.exit_code == 1, result.output
        assert result.output.startswith("error: forbidden: "), result.output
