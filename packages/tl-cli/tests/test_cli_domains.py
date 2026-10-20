"""`tl rfi`, `tl comm` and `tl evidence` on a temporary ledger (P1-I6): from RFI to notice.

Two people sign in on one ledger, a user (Ursula) and a document controller (Dora); a third
command-line run has no session at all. Every command that needs a controller is tried as the user
first. The module signs its people in itself, so every case runs on both adapters.
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
from tl_adapters.db import DbTarget, as_target
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


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def cast(env: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(env, tmp_path)


def run(who: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=who)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def later(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def raised_rfi(cast: Cast, **more: str) -> str:
    args = ["rfi", "raise", *PROJECT, "--subject", "Beam B12 clashes", "--question",
            "The isometric clashes with beam B12; confirm the routing.",
            "--required-by", later(14), "--to", "Meridian:pm@meridian.example",
            "--discipline", "M"]  # fmt: skip
    for key, value in more.items():
        args += [f"--{key.replace('_', '-')}", value]
    made = run(cast.ursula, *args)
    assert made.stdout.startswith("raised P123-RFI-0001")
    return made.stdout.split()[1]


def answered_rfi(cast: Cast) -> str:
    number = raised_rfi(cast)
    run(cast.ursula, "rfi", "submit", number, *PROJECT)
    run(cast.dora, "rfi", "issue", number, *PROJECT)
    run(cast.ursula, "rfi", "answer", number, *PROJECT, "--answer", "Re-route above the beam.",
        "--cost-impact", "yes", "--schedule-impact", "no")  # fmt: skip
    return number


def test_an_rfi_goes_from_draft_to_awaiting_a_response(cast: Cast) -> None:
    number = raised_rfi(cast)
    shown = run(cast.ursula, "rfi", "show", number, *PROJECT).stdout
    assert "Draft" in shown and "question The isometric clashes" in shown
    run(cast.ursula, "rfi", "update", number, *PROJECT, "--required-by", later(21))
    assert f"needed by {later(21)}" in run(cast.ursula, "rfi", "show", number, *PROJECT).stdout
    run(cast.ursula, "rfi", "submit", number, *PROJECT)
    refused = run(cast.ursula, "rfi", "issue", number, *PROJECT, ok=False)
    assert GATE in refused.stderr
    issued = run(cast.dora, "rfi", "issue", number, *PROJECT).stdout
    assert f"issued {number}" in issued and "nothing was sent" in issued
    assert f"due {later(21)}" in issued  # the clock ends on the day an answer is needed
    assert "Awaiting response" in run(cast.ursula, "rfi", "show", number, *PROJECT).stdout


def test_the_log_lists_the_item_and_counts_it(cast: Cast) -> None:
    number = answered_rfi(cast)
    listing = run(cast.ursula, "rfi", "ls", *PROJECT).stdout
    assert number in listing and "cost yes schedule no" in listing
    assert "1 items, 1 answered, 0 open, 0 overdue, 1 with an impact" in listing
    as_json = json.loads(run(cast.ursula, "rfi", "ls", *PROJECT, "--json").stdout)
    assert as_json["total"] == 1 and as_json["lines"][0]["cost_impact"] == "yes"
    assert run(cast.ursula, "rfi", "ls", *PROJECT, "--overdue").stdout.startswith("0 items")


def test_an_answer_with_an_impact_points_to_the_escalation(cast: Cast) -> None:
    number = raised_rfi(cast)
    run(cast.ursula, "rfi", "submit", number, *PROJECT)
    run(cast.dora, "rfi", "issue", number, *PROJECT)
    said = run(cast.ursula, "rfi", "answer", number, *PROJECT, "--answer", "Yes, it costs.",
               "--cost-impact", "yes").stdout  # fmt: skip
    assert f"tl rfi escalate {number}" in said
    quiet = run(cast.ursula, "rfi", "review", number, *PROJECT, "--reject", ok=False)
    assert "say why" in quiet.stderr
    run(cast.ursula, "rfi", "review", number, *PROJECT, "--accept")
    run(cast.ursula, "rfi", "close", number, *PROJECT)
    assert "Closed" in run(cast.ursula, "rfi", "show", number, *PROJECT).stdout


def test_escalating_is_a_controllers_act_and_the_notice_is_not_the_users(cast: Cast) -> None:
    number = answered_rfi(cast)
    assert GATE in run(cast.ursula, "rfi", "escalate", number, *PROJECT, ok=False).stderr
    made = run(cast.dora, "rfi", "escalate", number, *PROJECT).stdout
    assert f"escalated {number} to P123-EW-0001" in made
    assert f"due {later(14)}" in made or "time bar" in made
    assert "class restricted" in made
    again = run(cast.dora, "rfi", "escalate", number, *PROJECT, ok=False)
    assert "escalated already" in again.stderr
    # the user reads the RFI, never the notice: same words as an unused number
    shown = run(cast.ursula, "rfi", "show", number, *PROJECT).stdout
    assert "escalated to" not in shown
    assert GATE in run(cast.ursula, "comm", "show", "P123-EW-0001", *PROJECT, ok=False).stderr
    assert GATE in run(cast.ursula, "comm", "ls", *PROJECT, ok=False).stderr
    assert "escalated to P123-EW-0001" in run(cast.dora, "rfi", "show", number, *PROJECT).stdout


def test_a_notice_goes_to_the_other_party_and_comes_back_assessed(cast: Cast) -> None:
    number = answered_rfi(cast)
    run(cast.dora, "rfi", "escalate", number, *PROJECT)
    notice = "P123-EW-0001"
    run(
        cast.dora,
        *("comm", "update", notice, *PROJECT, "--currency", "USD", "--value", "12500"),
        *("--to", "Meridian:pm@meridian.example", "--cost-code", "2.3.1=10000"),
        *("--schedule-days", "3"),
    )
    run(cast.dora, "comm", "submit", notice, *PROJECT)
    run(cast.dora, "comm", "review", notice, *PROJECT, "--note", "figures checked")
    issued = run(cast.dora, "comm", "issue", notice, *PROJECT).stdout
    assert "nothing was sent" in issued and "met" in issued
    run(cast.dora, "comm", "assess", notice, *PROJECT, "--status", "partially_agreed",
        "--value", "9000.5")  # fmt: skip
    listing = run(cast.dora, "comm", "ls", *PROJECT).stdout
    assert "USD est 12500.00 ass 9000.50" in listing
    assert "total USD: 1 items, estimated 12500.00, assessed 9000.50" in listing
    shown = run(cast.dora, "comm", "show", notice, *PROJECT).stdout
    assert "assessed partially_agreed 9000.50" in shown and "from P123-RFI-0001" in shown
    run(cast.dora, "comm", "close", notice, *PROJECT)


def test_every_comm_command_needs_a_controller(cast: Cast) -> None:
    for args in (
        ("ls",),
        ("show", "P123-EW-0001"),
        ("raise", "--subject", "x"),
        ("update", "P123-EW-0001", "--subject", "y"),
        ("submit", "P123-EW-0001"),
        ("review", "P123-EW-0001"),
        ("return", "P123-EW-0001", "--reason", "r"),
        ("issue", "P123-EW-0001"),
        ("assess", "P123-EW-0001", "--status", "agreed"),
        ("close", "P123-EW-0001"),
        ("legal", "P123-EW-0001", "--reason", "r"),
        ("export",),
    ):
        refused = run(cast.ursula, "comm", *args, *PROJECT, ok=False)
        assert GATE in refused.stderr, args


def test_the_export_names_its_classes_and_quotes_what_a_spreadsheet_would_run(
    cast: Cast,
) -> None:
    number = answered_rfi(cast)
    run(cast.dora, "rfi", "escalate", number, *PROJECT, "--subject", "=HYPERLINK(1)")
    notice = "P123-EW-0001"
    run(cast.dora, "comm", "update", notice, *PROJECT, "--currency", "USD", "--value", "100",
        "--to", "Meridian:pm@meridian.example")  # fmt: skip
    run(cast.dora, "comm", "submit", notice, *PROJECT)
    run(cast.dora, "comm", "review", notice, *PROJECT)
    run(cast.dora, "comm", "issue", notice, *PROJECT)
    quiet = run(cast.dora, "comm", "export", *PROJECT)
    assert quiet.stdout.strip().count("\n") == 0  # the header only
    assert (
        "1 restricted items were left out: name the class with --class restricted" in quiet.stderr
    )
    out = (
        Path(cast.base["TL_DB"]).parent / "changes.csv" if "://" not in cast.base["TL_DB"] else None
    )
    loud = run(cast.dora, "comm", "export", *PROJECT, "--class", "restricted").stdout
    [row] = list(csv.DictReader(io.StringIO(loud)))
    assert row["number"] == notice and row["cost_status"] == "pending" and row["value"] == "100.00"
    assert row["title"] == "'=HYPERLINK(1)"
    assert out is None or not out.exists()
    never = run(cast.dora, "comm", "export", *PROJECT, "--class", "privileged", ok=False)
    assert "never exported" in never.stderr


def test_the_evidence_trail_follows_the_links_as_of_a_day(cast: Cast) -> None:
    number = answered_rfi(cast)
    run(cast.dora, "rfi", "escalate", number, *PROJECT)
    today = date.today().isoformat()
    shown = run(cast.dora, "evidence", "P123-EW-0001", *PROJECT).stdout
    assert f"evidence for P123-EW-0001 as of {today}" in shown
    assert "P123-RFI-0001 [correspondence.TechnicalItem] Answered" in shown
    assert "<- derived from (active" in shown
    earlier = (date.today() - timedelta(days=3)).isoformat()
    refused = run(cast.dora, "evidence", "P123-EW-0001", *PROJECT, "--as-of", earlier, ok=False)
    assert "did not exist on" in refused.stderr
    as_json = json.loads(run(cast.dora, "evidence", "P123-EW-0001", *PROJECT, "--json").stdout)
    assert as_json["root_id"] and [n["key"] for n in as_json["nodes"]][:2] == [
        "P123-EW-0001",
        "P123-RFI-0001",
    ]
    future = (date.today() + timedelta(days=1)).isoformat()
    assert (
        "after today"
        in run(cast.dora, "evidence", "P123-RFI-0001", *PROJECT, "--as-of", future, ok=False).stderr
    )
    # the user reads the RFI's trail without the restricted notice, and cannot ask for the notice
    plain = run(cast.ursula, "evidence", "P123-RFI-0001", *PROJECT).stdout
    assert "P123-EW-0001" not in plain
    missing = run(cast.ursula, "evidence", "P123-EW-0001", *PROJECT, ok=False)
    assert missing.stderr.startswith("error: no correspondence item")
