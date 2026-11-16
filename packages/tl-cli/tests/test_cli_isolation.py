"""`tl isolation apply|verify|remove|link|unlink|ls|show|export` (P2-PTW-T06a).

The ledger is made by ``permit_world.World`` (loaded by path, as ``test_cli_permit_write.py`` loads
it). Writes run with ``--actor`` on a dev ledger file; reads sign in as the person they name, so
the viewer is that person's. The clock stands at the world's start for every test.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from auth_support import sign_in
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core import util
from tl_core.services.queries import get_record
from tl_mod_permits import iso_views
from tl_mod_permits.handlers.isolation import MSG_HIDDEN_PERMIT, MSG_IN_USE, MSG_SELF_VERIFY
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PASSWORD = "correct horse battery"
POINT = "Pump P-101 breaker"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
HEADER = "key  point  energy  state  lock  tag  applied by  depends"


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


class Cli:
    """``tl --db DB isolation ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world.World(as_target(str(db)))
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None) -> Result:
        result = CliRunner().invoke(
            app, ["--db", str(self.db), "isolation", *argv], env=env or self.env
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

    def apply(self, who: str, *extra: str, point: str = POINT) -> Result:
        return self.run(
            "apply",
            "--project",
            PROJECT,
            "--point",
            point,
            "--energy",
            "electrical",
            "--method",
            "Lock and tag",
            "--lock",
            "L-17",
            "--tag",
            "T-204",
            "--actor",
            f"user:{who}",
            *extra,
        )

    def verb(self, verb: str, key: str, who: str, *extra: str) -> Result:
        return self.run(verb, key, "--project", PROJECT, "--actor", f"user:{who}", *extra)

    def link(self, verb: str, permit: str, isolation: str, who: str = "pam") -> Result:
        return self.run(verb, permit, isolation, "--project", PROJECT, "--actor", f"user:{who}")

    def key_of(self, result: Result) -> str:
        assert result.exit_code == 0, result.output
        return result.output.split()[1]

    def key_of_record(self, record: str) -> str:
        return str(self.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))

    def record_id(self, key: str) -> str:
        """The id of the record ``key`` names (for the state reads only; no command prints it)."""
        with open_uow(self.world.db, readonly=True) as uow:
            row = get_record(uow, SCOPE, key)
        assert row is not None, key
        return str(row["id"])

    def state(self, key: str) -> str:
        return self.world.state(self.record_id(key))


def iso_ls(result: Result) -> tuple[list[str], list[str], str]:
    """The keys, the depends counts and the last line (`n of total`) of an `ls` output."""
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == HEADER, result.output
    rows = lines[1:-1]
    return [r.split("  ")[0] for r in rows], [r.split("  ")[-1] for r in rows], lines[-1]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The clock stands at the world's start (07:00, a shift that ends at 18:00)."""
    start = load_world().START
    monkeypatch.setattr(util, "utcnow", lambda: start)
    yield


@pytest.fixture
def cli(tmp_path: Path, clock: None) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    create_schema(as_target(str(path)))
    world = load_world()
    made = Cli(path, tmp_path, world)
    made.world.people()
    made.world.person("cora", ("user", "document_controller"), grant="superuser")
    yield made


# --- the life of one isolation ---------------------------------------------------------------


def test_apply_verify_link_unlink_and_remove_print_their_line_and_move_the_state(cli: Cli) -> None:
    applied = cli.apply("pam")
    key = cli.key_of(applied)
    assert re.fullmatch(rf"applied {key}  version \d+\n", applied.output)
    assert cli.state(key) == "Applied"

    verified = cli.verb("verify", key, "sue")
    assert re.fullmatch(rf"verified {key}  version \d+\n", verified.output)
    assert cli.state(key) == "Verified"

    permit = cli.world.approved()
    permit_key = cli.key_of_record(permit)
    linked = cli.link("link", permit_key, key)
    assert re.fullmatch(rf"linked {permit_key} {key}  version \d+\n", linked.output)

    keys, depends, total = iso_ls(cli.read("uma", "ls", "--project", PROJECT))
    assert keys == [key] and depends == ["1"] and total == "1 of 1"
    shown = cli.read("uma", "show", key, "--project", PROJECT)
    assert shown.exit_code == 0, shown.output
    assert re.search(rf"^Linked permits\s+{permit_key}$", shown.output, re.M)

    unlinked = cli.link("unlink", permit_key, key)
    assert re.fullmatch(rf"unlinked {permit_key} {key}  version \d+\n", unlinked.output)
    keys, depends, _ = iso_ls(cli.read("uma", "ls", "--project", PROJECT))
    assert keys == [key] and depends == ["0"]

    removed = cli.verb("remove", key, "pam")
    assert re.fullmatch(rf"removed {key}  version \d+\n", removed.output)
    assert cli.state(key) == "Removed"


# --- refusals come from the handlers --------------------------------------------------------------


def test_the_applier_cannot_verify_and_a_needed_isolation_cannot_be_removed(cli: Cli) -> None:
    key = cli.key_of(cli.apply("pam"))
    refused = cli.verb("verify", key, "pam")
    assert refused.exit_code == 1, refused.output
    assert f"error: {MSG_SELF_VERIFY}" in refused.output
    assert cli.state(key) == "Applied"

    permit_key = cli.key_of_record(cli.world.approved())
    cli.link("link", permit_key, key)
    refused = cli.verb("remove", key, "pam")
    assert refused.exit_code == 1, refused.output
    assert f"error: {MSG_IN_USE}{permit_key}" in refused.output
    assert cli.state(key) == "Applied"

    cli.world.issue(cli.record_id(permit_key), who="pam")
    refused = cli.verb("remove", key, "pam")
    assert refused.exit_code == 1, refused.output
    assert f"error: {MSG_IN_USE}{permit_key}" in refused.output
    assert cli.state(key) == "Applied"


def test_removing_while_a_hidden_permit_needs_it_prints_the_fixed_text_and_no_key(cli: Cli) -> None:
    key = cli.key_of(cli.apply("pam"))
    secret = cli.world.hidden_record()
    hidden_permit = cli.world.request("dora", for_record_id=secret)
    cli.world.call("cora", "ApprovePermit", permit=hidden_permit)
    hidden_key = cli.key_of_record(hidden_permit)
    linked = cli.link("link", hidden_key, key, who="dora")
    assert linked.exit_code == 0, linked.output

    refused = cli.verb("remove", key, "pam")
    assert refused.exit_code == 1, refused.output
    assert f"error: {MSG_IN_USE}{MSG_HIDDEN_PERMIT}" in refused.output
    assert hidden_key not in refused.output
    assert cli.state(key) == "Applied"


# --- visibility -----------------------------------------------------------------------------------


def test_a_hidden_point_record_leaves_no_row_and_no_count_and_show_answers_as_missing(
    cli: Cli,
) -> None:
    plain = cli.key_of(cli.apply("pam"))
    secret = cli.world.hidden_record()
    secret_key = cli.key_of_record(secret)
    hidden = cli.key_of(cli.apply("dora", "--point-record", secret_key, point="Motor M-7"))

    keys, _, total = iso_ls(cli.read("uma", "ls", "--project", PROJECT))
    assert keys == [plain] and total == "1 of 1"

    missing = cli.read("uma", "show", hidden, "--project", PROJECT)
    unknown = cli.read("uma", "show", "P123-ISL-9999", "--project", PROJECT)
    assert missing.exit_code == 1 and unknown.exit_code == 1
    assert missing.output.replace(hidden, "<KEY>") == unknown.output.replace(
        "P123-ISL-9999", "<KEY>"
    )
    assert f"error: no isolation {hidden}" in missing.output

    keys, _, total = iso_ls(cli.read("dora", "ls", "--project", PROJECT))
    assert set(keys) == {plain, hidden} and total == "2 of 2"
    seen = cli.read("dora", "show", hidden, "--project", PROJECT)
    assert seen.exit_code == 0 and seen.output.startswith(f"isolation {hidden}\n"), seen.output


# --- export ---------------------------------------------------------------------------------------


def test_export_is_the_views_export_of_the_same_list(cli: Cli) -> None:
    cli.apply("pam")
    cli.apply("pam", point="Valve V-2")
    with open_uow(cli.world.db, readonly=True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:uma")
        page = iso_views.isolation_list(uow.conn(), SCOPE, limit=iso_views.MAX_LIMIT, viewer=viewer)
        expected_csv = iso_views.isolation_export_rows(page.rows, "csv")
        expected_jsonl = iso_views.isolation_export_rows(page.rows, "jsonl")
    assert len(page.rows) == 2

    csv_out = cli.read("uma", "export", "--project", PROJECT, "--format", "csv")
    assert csv_out.exit_code == 0 and csv_out.output == expected_csv
    jsonl_out = cli.read("uma", "export", "--project", PROJECT, "--format", "jsonl")
    assert jsonl_out.exit_code == 0 and jsonl_out.output == expected_jsonl


def test_a_bad_export_format_and_a_bad_state_are_usage_errors(cli: Cli) -> None:
    cli.apply("pam")
    xml = cli.read("uma", "export", "--project", PROJECT, "--format", "xml")
    assert xml.exit_code == 2, xml.output
    state = cli.read("uma", "ls", "--project", PROJECT, "--state", "Nope")
    assert state.exit_code == 2, state.output
    energy = cli.read("uma", "export", "--project", PROJECT, "--format", "csv", "--energy", "x")
    assert energy.exit_code == 2, energy.output


# --- access words --------------------------------------------------------------------------------


def test_a_person_without_the_write_word_is_refused_by_require_command(cli: Cli) -> None:
    # vera reads permits as a viewer; the viewer role does not hold permits.isolation.apply.
    result = cli.apply("vera")
    assert result.exit_code == 1, result.output
    assert "error: forbidden:" in result.output
    keys, _, total = iso_ls(cli.read("uma", "ls", "--project", PROJECT))
    assert keys == [] and total == "0 of 0"


def test_an_actor_without_permits_view_is_refused_before_any_read(cli: Cli) -> None:
    key = cli.key_of(cli.apply("pam"))
    reads = [
        ("ls",),
        ("show", key),
        ("export", "--format", "csv"),
    ]
    for argv in reads:
        result = cli.run(*argv, "--project", PROJECT, "--actor", "agent:nobody")
        assert result.exit_code == 1, result.output
        assert result.output.startswith("error: forbidden: "), result.output


def test_help_lists_the_eight_verbs(cli: Cli) -> None:
    result = cli.run("--help")
    assert result.exit_code == 0, result.output
    for verb in ("apply", "verify", "remove", "link", "unlink", "ls", "show", "export"):
        assert re.search(rf"│\s+{verb}\s", result.output), result.output
