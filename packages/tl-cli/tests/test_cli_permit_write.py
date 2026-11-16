"""`tl permit` write verbs (P2-PTW-T04): request, approve, reject, issue, revalidate, suspend,
resume, handback, close, cancel.

The ledger is made by ``permit_world.World`` (loaded by path, as ``test_cli_punch.py`` loads
``punch_world``); writes run with ``--actor`` on a dev ledger file. The stored state is read with
the world's helpers, since the write verbs print keys and versions only.
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
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core.services.queries import get_record
from tl_mod_permits import cli_permit_write
from tl_mod_permits.handlers.permit import MSG_SELF_APPROVE
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
IWP = "P123-IWP-0001"
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")


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
    """``tl --db DB permit ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: ModuleType) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str) -> Result:
        result = CliRunner().invoke(app, ["--db", str(self.db), "permit", *argv], env=self.env)
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert "Traceback" not in result.output
        assert not HEX32.search(result.output), result.output
        return result

    def verb(self, verb: str, key: str, who: str, *extra: str) -> Result:
        return self.run(verb, key, "--project", PROJECT, "--actor", f"user:{who}", *extra)

    def request(self, who: str = "rob", *extra: str) -> Result:
        return self.run(
            "request",
            "--project",
            PROJECT,
            "--type",
            "general",
            "--area",
            "A1",
            "--location",
            "Pump room",
            "--description",
            "Weld repair, rack 12",
            "--holder",
            "Rob",
            "--from",
            "2026-12-01",
            "--until",
            "2026-12-31",
            "--actor",
            f"user:{who}",
            *extra,
        )

    def key_of(self, result: Result) -> str:
        assert result.exit_code == 0, result.output
        return result.output.split()[1]

    def record_id(self, key: str) -> str:
        """The id of the permit ``key`` names (for the state reads only; no command prints it)."""
        with open_uow(self.world.db, readonly=True) as uow:
            row = get_record(uow, SCOPE, key)
        assert row is not None, key
        return str(row["id"])

    def state(self, key: str) -> str:
        return self.world.state(self.record_id(key))


@pytest.fixture
def cli(tmp_path: Path) -> Iterator[Cli]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    world = load_world().World(target)
    world.people()
    world.record("awp.IWP", IWP)
    yield Cli(path, tmp_path, world)


# --- the walk -------------------------------------------------------------------------------------


def test_walk_one_permit_through_its_life(cli: Cli) -> None:
    key = cli.key_of(cli.request("rob"))
    assert cli.state(key) == "Requested"

    approved = cli.verb("approve", key, "sue")
    assert re.fullmatch(rf"approved {key}  version \d+\n", approved.output)
    assert cli.state(key) == "Approved"

    issued = cli.verb("issue", key, "pam", "--tick", "jha_attached")
    assert re.fullmatch(rf"issued {key}  version \d+\n", issued.output)
    assert cli.state(key) == "Active"

    revalidated = cli.verb("revalidate", key, "pam")
    assert re.fullmatch(rf"revalidated {key}  version \d+\n", revalidated.output)
    assert cli.state(key) == "Active"

    suspended = cli.verb("suspend", key, "pam", "--reason", "Gate check")
    assert re.fullmatch(rf"suspended {key}  version \d+\n", suspended.output)
    assert cli.state(key) == "Suspended"

    resumed = cli.verb("resume", key, "pam")
    assert re.fullmatch(rf"resumed {key}  version \d+\n", resumed.output)
    assert cli.state(key) == "Active"

    handed = cli.verb("handback", key, "pam", "--note", "Site is safe")
    assert re.fullmatch(rf"handed back {key}  version \d+\n", handed.output)
    assert cli.state(key) == "Handed back"

    closed = cli.verb("close", key, "pam")
    assert re.fullmatch(rf"closed {key}  version \d+\n", closed.output)
    assert cli.state(key) == "Closed"


def test_request_with_for_resolves_the_record_and_prints_the_line(cli: Cli) -> None:
    result = cli.request("rob", "--for", IWP)
    assert re.fullmatch(r"requested P123-PTW-0001  version \d+\n", result.output)


# --- reject and cancel, and the missing reason ----------------------------------------------------


def test_reject_with_reason_moves_to_rejected(cli: Cli) -> None:
    key = cli.key_of(cli.request("rob"))
    result = cli.verb("reject", key, "sue", "--reason", "Missing JHA")
    assert re.fullmatch(rf"rejected {key}  version \d+\n", result.output)
    assert cli.state(key) == "Rejected"


def test_cancel_with_reason_moves_to_cancelled(cli: Cli) -> None:
    key = cli.key_of(cli.request("rob"))
    result = cli.verb("cancel", key, "pam", "--reason", "Scope changed")
    assert re.fullmatch(rf"cancelled {key}  version \d+\n", result.output)
    assert cli.state(key) == "Cancelled"


@pytest.mark.parametrize("verb", ["reject", "suspend", "cancel"])
def test_a_missing_reason_is_a_usage_error(cli: Cli, verb: str) -> None:
    key = cli.key_of(cli.request("rob"))
    result = cli.verb(verb, key, "sue")
    assert result.exit_code == 2, result.output
    assert "--reason" in result.output


def test_handback_without_a_note_is_a_usage_error(cli: Cli) -> None:
    key = cli.key_of(cli.request("rob"))
    result = cli.verb("handback", key, "pam")
    assert result.exit_code == 2, result.output
    assert "--note" in result.output


# --- refusals -------------------------------------------------------------------------------------


def test_the_requester_cannot_approve(cli: Cli) -> None:
    key = cli.key_of(cli.request("sue"))
    result = cli.verb("approve", key, "sue")
    assert result.exit_code == 1, result.output
    assert f"error: {MSG_SELF_APPROVE}" in result.output
    assert cli.state(key) == "Requested"


def test_an_actor_without_the_word_is_refused_by_require_command(cli: Cli) -> None:
    key = cli.key_of(cli.request("uma"))
    result = cli.verb("approve", key, "rob")
    assert result.exit_code == 1, result.output
    assert "error: forbidden:" in result.output
    assert cli.state(key) == "Requested"


def test_an_unknown_key_and_a_key_of_another_type_print_the_same_text(cli: Cli) -> None:
    isolation = "P123-ISL-0001"
    cli.world.isolation()
    unknown = cli.verb("approve", "P123-PTW-9999", "sue")
    other = cli.verb("approve", isolation, "sue")
    assert unknown.exit_code == 1 and other.exit_code == 1
    assert "error: no permit P123-PTW-9999" in unknown.output
    assert f"error: no permit {isolation}" in other.output


def test_an_unknown_for_key_prints_no_record(cli: Cli) -> None:
    result = cli.request("rob", "--for", "P123-XYZ-0001")
    assert result.exit_code == 1, result.output
    assert "error: no record P123-XYZ-0001" in result.output


def test_a_for_key_the_actor_cannot_see_prints_the_same_text_as_an_unknown_key(cli: Cli) -> None:
    secret = cli.world.hidden_record()
    secret_key = str(cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=secret))
    unknown_key = "P123-XYZ-0001"
    hidden = cli.request("rob", "--for", secret_key)
    unknown = cli.request("rob", "--for", unknown_key)
    assert hidden.exit_code == 1 and unknown.exit_code == 1
    assert f"error: no record {secret_key}" in hidden.output
    # the same text apart from the key the reader typed
    assert hidden.output.replace(secret_key, "<KEY>") == unknown.output.replace(
        unknown_key, "<KEY>"
    )


def test_a_restricted_permit_answers_as_missing_to_a_reader_who_cannot_see_it(cli: Cli) -> None:
    secret = cli.world.hidden_record()
    permit = cli.world.request("dora", for_record_id=secret)
    key = str(cli.world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=permit))
    result = cli.verb("approve", key, "sue")
    assert result.exit_code == 1, result.output
    assert f"error: no permit {key}" in result.output
    assert cli.world.state(permit) == "Requested"


def test_a_permit_write_runs_its_handler_as_the_acting_person(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No T04 refusal names a record (blockers are codes), so the test spies on the viewer the
    # handler runs under: it must be the actor's, not the process's (LOWEST on a dev ledger).
    seen: list[cf.Viewer] = []
    original = cli_permit_write._handler

    def spy(model: Any) -> Any:
        handler = original(model)

        def run(uow: Any, command: Any) -> Any:
            seen.append(cf.current_viewer())
            return handler(uow, command)

        return run

    monkeypatch.setattr(cli_permit_write, "_handler", spy)
    cli.key_of(cli.request("rob"))
    with open_uow(cli.world.db, readonly=True) as uow:
        expected = cf.viewer_for_actor(uow.conn(), "user:rob")
    assert seen == [expected]
    assert expected != cf.LOWEST


# --- help -----------------------------------------------------------------------------------------


def test_help_lists_the_ten_write_verbs(cli: Cli) -> None:
    result = CliRunner().invoke(app, ["permit", "--help"], env=cli.env)
    assert result.exit_code == 0, result.output
    for verb in (
        "request",
        "approve",
        "reject",
        "issue",
        "revalidate",
        "suspend",
        "resume",
        "handback",
        "close",
        "cancel",
    ):
        # the help is a Rich panel: each command line starts with the border and its name
        assert re.search(rf"^[│ ]*{verb}\s", result.output, re.MULTILINE), verb
