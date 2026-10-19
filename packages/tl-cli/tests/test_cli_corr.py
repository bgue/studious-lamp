"""`tl corr ...` on a temporary ledger (P1-I5): the register, the clocks, the controller's acts.

The letter is made by the commands: received by upload, triaged, answered, drafted and issued with
a 14-calendar-day clock. Three people sign in on one ledger (a user, a document controller and an
admin); every command that needs a controller is tried as the user first. The module signs its
people in itself, so every case runs on both adapters.
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from typer.testing import CliRunner
from typer.testing import Result as RunResult

AUTO_SIGN_IN = False
PASSWORD = "correct horse battery"
GATE = "needs the document_controller or admin role"
PROJECT = ("--project", "P123")
runner = CliRunner()


class Cast:
    """`env` per person: the same ledger, a session file of their own."""

    def __init__(self, env: dict[str, str], tmp_path: Path) -> None:
        self.base = env
        self.target = as_target(env["TL_DB"])
        with mock.patch.dict(os.environ, env):
            backend = session.open_backend(self.target)
            with backend() as uow:
                for name, roles in (
                    ("dora", ["user", "document_controller"]),
                    ("ursula", ["user"]),
                ):
                    accounts.create_account(
                        uow, username=name, display_name=name.title(), kind="person",
                        roles=roles, password=prepare_password(PASSWORD, username=name),
                        by="svc:test",
                    )  # fmt: skip
        self.dora = self._sign_in("dora", tmp_path)
        self.ursula = self._sign_in("ursula", tmp_path)

    def _sign_in(self, name: str, tmp_path: Path) -> dict[str, str]:
        mine = self.base | {"TL_SESSION_FILE": str(tmp_path / f"session-{name}.json")}
        with mock.patch.dict(os.environ, mine):
            backend = session.open_backend(self.target)
            principal, token = sessions.sign_in(backend, username=name, password=PASSWORD)
            session.save(
                session.StoredSession(
                    target=session.db_target(self.target),
                    username=name,
                    actor=principal.actor,
                    expires_at=session.expires_at_from(sessions.SESSION_TTL),
                    token=token,
                )
            )
        return mine

    def events(self) -> int:
        with open_uow(self.target, readonly=True) as uow:
            from sqlalchemy import text

            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def cast(env: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(env, tmp_path)


def run(who: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, ["corr", *args], env=who)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def receive(who: dict[str, str], tmp_path: Path, subject: str = "Drawings") -> str:
    letter = tmp_path / "letter.txt"
    letter.write_text("Dear all, the drawings follow.")
    made = run(who, "receive", *PROJECT, "--subject", subject, "--from", "Acme",
               "--file", str(letter))  # fmt: skip
    return made.stdout.split()[1]


def test_receive_by_upload_lists_and_shows(cast: Cast, tmp_path: Path) -> None:
    number = receive(cast.ursula, tmp_path)
    shown = run(cast.ursula, "show", number, *PROJECT).stdout
    assert "Received" in shown and "subject Drawings" in shown
    assert "file original letter.txt" in shown
    assert number in run(cast.ursula, "ls", *PROJECT).stdout
    run(cast.ursula, "update", number, *PROJECT, "--subject", "Drawings, revision B")
    assert "subject Drawings, revision B" in run(cast.ursula, "show", number, *PROJECT).stdout
    missing = run(cast.ursula, "show", "P123-COR-9999", *PROJECT, ok=False)
    assert missing.stderr.startswith("error: no item")


def test_receive_by_upload_then_triage_to_general_with_the_suggestion(
    cast: Cast, tmp_path: Path
) -> None:
    number = receive(cast.ursula, tmp_path)
    shown = run(cast.ursula, "show", number, *PROJECT).stdout
    assert "Received" in shown and "subject Drawings" in shown
    assert "file original letter.txt" in shown
    assert number in run(cast.ursula, "ls", *PROJECT).stdout
    assert run(cast.ursula, "suggest", number, *PROJECT).stdout.startswith("suggested ")
    triaged = run(
        cast.ursula, "triage", number, *PROJECT, "--domain", "general", "--subtype", "letter"
    ).stdout
    assert triaged.startswith(f"triaged {number} as general/")
    assert "Triaged" in run(cast.ursula, "show", number, *PROJECT).stdout
    missing = run(cast.ursula, "show", "P123-COR-9999", *PROJECT, ok=False)
    assert missing.stderr.startswith("error: no item")


def test_a_reply_is_issued_by_a_controller_with_a_fourteen_day_clock(
    cast: Cast, tmp_path: Path
) -> None:
    number = receive(cast.ursula, tmp_path)
    drafted = run(
        cast.ursula, "draft", *PROJECT, "--subject", "Re: Drawings", "--to", "Acme:site@acme.test",
        "--reply-to", number, "--body", "Received, thanks.",
        "--domain", "general", "--subtype", "letter",
    )  # fmt: skip
    reply = drafted.stdout.split()[1]
    refused = run(cast.ursula, "issue", reply, *PROJECT, ok=False)
    assert refused.stderr.startswith("error: forbidden") and GATE in refused.stderr
    issued = run(cast.dora, "issue", reply, *PROJECT).stdout
    assert f"issued {reply} on " in issued and "nothing was sent" in issued
    assert f"clock {reply}-C01" in issued
    clocks = run(cast.dora, "clock", "ls", *PROJECT).stdout
    assert f"{reply}-C01 running" in clocks and " 14 calendar " in clocks
    assert "Issued" in run(cast.dora, "show", reply, *PROJECT).stdout


def test_the_clock_commands_pause_resume_and_meet(cast: Cast, tmp_path: Path) -> None:
    number = receive(cast.ursula, tmp_path)
    started = run(cast.ursula, "clock", "start", number, *PROJECT, "--label", "Their reply",
                  "--days", "10", "--warn", "3")  # fmt: skip
    key = started.stdout.split()[1]
    run(cast.ursula, "clock", "pause", key, *PROJECT, "--reason", "waiting for the client")
    assert f"{key} paused" in run(cast.ursula, "clock", "ls", *PROJECT).stdout
    run(cast.ursula, "clock", "resume", key, *PROJECT, "--reason", "client is back")
    run(cast.ursula, "clock", "meet", key, *PROJECT)
    assert key not in run(cast.ursula, "clock", "ls", *PROJECT).stdout
    assert f"{key} met" in run(cast.ursula, "clock", "ls", *PROJECT, "--all").stdout
    assert run(cast.ursula, "clock", "pause", "P123-COR-9999-C01", *PROJECT, "--reason", "x",
               ok=False).stderr.startswith("error: no clock")  # fmt: skip


def test_the_register_csv_leaves_out_what_is_not_internal_and_quotes_formulas(
    cast: Cast, tmp_path: Path
) -> None:
    plain = receive(cast.ursula, tmp_path, "Plain letter")
    secret = receive(cast.ursula, tmp_path, '=HYPERLINK("http://evil.test")')
    run(cast.dora, "class", "set", secret, *PROJECT, "--to", "restricted", "--reason", "legal")
    out = run(cast.dora, "report", "register", *PROJECT).stdout
    rows = list(csv.DictReader(io.StringIO(out)))
    assert [r["number"] for r in rows] == [plain]
    assert secret not in out
    # a controller who names the class gets it, and a formula is written as text
    both = run(cast.dora, "report", "register", *PROJECT, "--include-class", "restricted").stdout
    got = {r["number"]: r for r in csv.DictReader(io.StringIO(both))}
    assert set(got) == {plain, secret}
    assert got[secret]["subject"].startswith("'=")
    # a user cannot name a class; the file goes where --out says
    refused = run(cast.ursula, "report", "register", *PROJECT, "--include-class", "restricted",
                  ok=False)  # fmt: skip
    assert GATE in refused.stderr
    target = tmp_path / "register.json"
    run(cast.ursula, "report", "register", *PROJECT, "--json", "--out", str(target))
    assert [r["number"] for r in json.loads(target.read_text())] == [plain]


def test_responses_due_lists_the_items_that_want_an_answer(cast: Cast, tmp_path: Path) -> None:
    number = receive(cast.ursula, tmp_path)
    due = (date.today() + timedelta(days=5)).isoformat()
    run(cast.ursula, "update", number, *PROJECT, "--response-required", "--due", due)
    out = run(cast.ursula, "report", "due", *PROJECT).stdout
    assert out.startswith(f"{number} due {due} left 5 ")
    assert run(cast.ursula, "report", "due", *PROJECT, "--within", "3").stdout == ""
    assert number in run(cast.ursula, "report", "due", *PROJECT, "--within", "5").stdout


SITES = {
    "issue": ("issue", "P123-COR-0001"),
    "supersede": ("supersede", "P123-COR-0001", "--by", "P123-COR-0002", "--reason", "x"),
    "clock sweep": ("clock", "sweep"),
    "party add": ("party", "add", "ACME", "--name", "Acme", "--role", "client"),
    "party contact-add": ("party", "contact-add", "ACME", "--contact", "Bo"),
    "party contact-end": ("party", "contact-end", "ACME", "--position", "1", "--reason", "x"),
    "party retire": ("party", "retire", "ACME", "--reason", "x"),
    "clause add": ("clause", "add", "CT-1", "20.1"),
    "clause retire": ("clause", "retire", "CT-1", "20.1", "--reason", "x"),
    "class set": ("class", "set", "P123-COR-0001", "--to", "restricted", "--reason", "x"),
    "class grant": ("class", "grant", "P123-COR-0001", "--account", "user:bo", "--reason", "x"),
    "class withdraw": (
        "class",
        "withdraw",
        "P123-COR-0001",
        "--account",
        "user:bo",
        "--reason",
        "x",
    ),
    "clearance ls": ("clearance", "ls"),
    "report register": ("report", "register", "--include-class", "restricted"),
}


@pytest.mark.parametrize("name", list(SITES))
def test_a_user_is_refused_at_every_controller_site_and_nothing_is_written(
    name: str, cast: Cast
) -> None:
    before = cast.events()
    refused = run(cast.ursula, *SITES[name], *PROJECT, ok=False)
    assert refused.stderr.startswith("error: forbidden"), refused.stderr
    assert GATE in refused.stderr
    assert cast.events() == before


def test_a_controller_lists_who_is_named_and_names_another_reader(
    cast: Cast, tmp_path: Path
) -> None:
    number = receive(cast.ursula, tmp_path)
    run(cast.dora, "class", "set", number, *PROJECT, "--to", "privileged", "--grant", "user:ursula",
        "--reason", "counsel")  # fmt: skip
    listed = run(cast.dora, "clearance", "ls", *PROJECT).stdout
    assert "user:ursula" in listed and "user:dora" in listed
    assert number not in listed  # ids and accounts, nothing of the item
    run(cast.dora, "class", "withdraw", number, *PROJECT, "--account", "user:ursula",
        "--reason", "moved")  # fmt: skip
    assert "user:ursula" not in run(cast.dora, "clearance", "ls", *PROJECT).stdout
    assert run(cast.ursula, "clearance", "ls", *PROJECT, ok=False).stderr.startswith(
        "error: forbidden"
    )
