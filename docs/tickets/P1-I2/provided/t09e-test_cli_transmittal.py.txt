"""`tl transmittal create|issue|answer|close|void|ls|show` on a temporary ledger (P1-I2-T09e).

Documents and revisions are made with the module's own test world (`doccli_support.world`); the
transmittals under test are made and moved by the commands.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from doccli_support import admin_session, docs_env, world
from engcli_support import ordinary_env
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_mod_documents.testing import DocumentsWorld
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
TODAY = datetime.now(UTC).date().isoformat()
FIRST = "P123-TRN-0001"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def issued(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """ISO-1234 and PID-0001 with revision A issued; SPC-0001 with a draft A only."""
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")
    made.issued_document("PID-0001", "IFC")
    made.register("SPC-0001")
    made.create_revision("SPC-0001")
    return made


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def trn(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "transmittal", *args, ok=ok)


def create(env: dict[str, str], *more: str, ok: bool = True) -> RunResult:
    base = ("create", "--project", "P123", "--subject", "Isometrics for site")
    base += ("--purpose", "for_construction", "--to", "Site:Acme:site@acme.test")
    items = ("--revision", "ISO-1234@A", "--revision", "PID-0001@A")
    return trn(env, *base, *(more or items), ok=ok)


def fields(env: dict[str, str], number: str = FIRST) -> dict[str, str]:
    out = trn(env, "show", number, "--project", "P123").stdout.splitlines()
    return dict(line.split(": ", 1) for line in out if ": " in line)


# --- create and show ------------------------------------------------------------------------------


def test_create_drafts_a_transmittal_with_an_allocated_number(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    result = create(env)
    assert result.stdout.splitlines() == [f"created transmittal {FIRST}", "items 2"]
    shown = trn(env, "show", FIRST, "--project", "P123").stdout.splitlines()
    assert shown == [
        f"number: {FIRST}",
        "title: Isometrics for site",
        "state: Draft",
        "direction: outgoing",
        "purpose: for_construction",
        "issued: -",
        "due: -",
        "response: -",
        "responded: -",
        "recipient Site, Acme <site@acme.test>",
        "item ISO-1234@A IFR",
        "item PID-0001@A IFC",
    ]
    second = create(env, "--revision", "ISO-1234@A")
    assert second.stdout.splitlines()[0] == "created transmittal P123-TRN-0002"


def test_create_takes_a_number_a_direction_a_date_and_several_recipients(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    result = create(
        env,
        "--revision",
        "ISO-1234@A",
        "--number",
        "P123-TRN-0042",
        "--direction",
        "incoming",
        "--due",
        "2026-12-01",
        "--to",
        "Ana",
        "--notes",
        "see the markup",
    )
    assert result.stdout.splitlines()[0] == "created transmittal P123-TRN-0042"
    got = fields(env, "P123-TRN-0042")
    assert (got["direction"], got["due"]) == ("incoming", "2026-12-01")
    lines = trn(env, "show", "P123-TRN-0042", "--project", "P123").stdout.splitlines()
    assert "recipient Site, Acme <site@acme.test>" in lines and "recipient Ana" in lines


def test_create_refuses_what_the_module_refuses(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    bad_item = create(env, "--revision", "ISO-1234", ok=False)
    assert bad_item.stderr.strip() == (
        "error: revision 'ISO-1234' must be written NUMBER@CODE, for example ISO-1234@B"
    )
    ghost = create(env, "--revision", "ISO-1234@Z", ok=False)
    assert ghost.stderr.strip() == "error: no revision 'Z' of ISO-1234"
    nodoc = create(env, "--revision", "NOPE-1@A", ok=False)
    assert nodoc.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"
    draft = create(env, "--revision", "SPC-0001@A", ok=False)
    assert "carries issued revisions only" in draft.stderr
    wrong = create(env, "--revision", "ISO-1234@A", "--number", "TRN-0001", ok=False)
    assert "does not fit" in wrong.stderr
    purpose = trn(
        env,
        *("create", "--project", "P123", "--subject", "s", "--purpose", "for_fun"),
        *("--to", "Site", "--revision", "ISO-1234@A"),
        ok=False,
    )
    assert purpose.stderr.startswith("error: purpose:")
    assert trn(env, "ls", "--project", "P123").stdout == ""


def test_show_of_an_unknown_number_is_an_error(env: dict[str, str]) -> None:
    result = trn(env, "show", "NOPE-1", "--project", "P123", ok=False)
    assert result.stderr.startswith("error: ") and "NOPE-1" in result.stderr


# --- issue, answer, close, void -------------------------------------------------------------------


def test_issue_is_for_an_admin_and_dates_are_today_unless_a_reason_backs_them(
    env: dict[str, str], issued: DocumentsWorld, tmp_path: Path
) -> None:
    create(env)
    can_refuse = admin_session(env)
    if can_refuse:
        refused = trn(ordinary_env(env, tmp_path), "issue", FIRST, "--project", "P123", ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
        assert fields(env)["state"] == "Draft"
    future = trn(env, "issue", FIRST, "--project", "P123", "--date", "2999-01-01", ok=False)
    assert "future" in future.stderr
    early = trn(env, "issue", FIRST, "--project", "P123", "--date", "2026-01-05", ok=False)
    assert "reason" in early.stderr
    assert fields(env)["state"] == "Draft"
    done = trn(env, "issue", FIRST, "--project", "P123")
    assert done.stdout.strip() == f"issued {FIRST} on {TODAY}"
    assert fields(env)["state"] == "Issued" and fields(env)["issued"] == TODAY
    again = trn(env, "issue", FIRST, "--project", "P123", ok=False)
    assert "only be issued while Draft" in again.stderr


def test_a_backdated_issue_keeps_its_reason(env: dict[str, str], issued: DocumentsWorld) -> None:
    create(env)
    admin_session(env)
    args = ("issue", FIRST, "--project", "P123", "--date", "2026-01-05")
    done = trn(env, *args, "--date-reason", "sent by post on the 5th")
    assert done.stdout.strip() == f"issued {FIRST} on 2026-01-05"


def test_the_answer_acknowledges_an_issued_transmittal_and_close_ends_it(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    create(env)
    early = trn(env, "answer", FIRST, "--project", "P123", "--code", "approved", ok=False)
    assert "only be answered while Issued" in early.stderr
    admin_session(env)
    trn(env, "issue", FIRST, "--project", "P123")
    bad = trn(env, "answer", FIRST, "--project", "P123", "--code", "maybe", ok=False)
    assert bad.stderr.startswith("error: response_code:")
    done = trn(
        env,
        *("answer", FIRST, "--project", "P123", "--code", "approved_with_comments"),
        *("--note", "see markup"),
    )
    assert done.stdout.strip() == f"answered {FIRST}: approved_with_comments"
    got = fields(env)
    assert (got["state"], got["response"], got["responded"]) == (
        "Acknowledged",
        "approved_with_comments",
        TODAY,
    )
    closed = trn(env, "close", FIRST, "--project", "P123", "--reason", "all answered")
    assert closed.stdout.strip() == f"closed {FIRST}"
    assert fields(env)["state"] == "Closed"
    after = trn(env, "close", FIRST, "--project", "P123", ok=False)
    assert after.stderr.startswith("error: ")


def test_only_a_draft_is_voided(env: dict[str, str], issued: DocumentsWorld) -> None:
    create(env)
    create(env, "--revision", "ISO-1234@A")
    done = trn(env, "void", FIRST, "--project", "P123", "--reason", "drafted in error")
    assert done.stdout.strip() == f"voided {FIRST}"
    admin_session(env)
    trn(env, "issue", "P123-TRN-0002", "--project", "P123")
    sent = trn(env, "void", "P123-TRN-0002", "--project", "P123", "--reason", "x", ok=False)
    assert "only be voided while Draft" in sent.stderr


# --- ls -------------------------------------------------------------------------------------------


def test_ls_lists_by_number_and_filters_and_leaves_out_the_void(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    create(env)
    create(env, "--revision", "ISO-1234@A", "--direction", "incoming")
    create(env, "--revision", "PID-0001@A")
    trn(env, "void", "P123-TRN-0003", "--project", "P123", "--reason", "x")
    out = trn(env, "ls", "--project", "P123").stdout.splitlines()
    assert out == [
        f"{FIRST}  Draft  outgoing  for_construction  items=2  Isometrics for site",
        "P123-TRN-0002  Draft  incoming  for_construction  items=1  Isometrics for site",
    ]
    only = trn(env, "ls", "--project", "P123", "--direction", "incoming").stdout.splitlines()
    assert [line.split("  ")[0] for line in only] == ["P123-TRN-0002"]
    assert trn(env, "ls", "--project", "P123", "--state", "Issued").stdout == ""
    voided = trn(env, "ls", "--project", "P123", "--state", "Void").stdout.splitlines()
    assert [line.split("  ")[:2] for line in voided] == [["P123-TRN-0003", "Void"]]
