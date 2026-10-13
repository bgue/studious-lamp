"""`tl doc link|stale|diff|repin` on a temporary ledger (P1-I2-T09d).

Documents, revisions and the tag that links are made with the module's own test world
(`doccli_support.world`); the links under test are made and moved by the commands.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from doccli_support import docs_env, world
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_mod_documents.testing import DocumentsWorld
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def doc(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "doc", *args, ok=ok)


def link(env: dict[str, str], *more: str, ok: bool = True) -> RunResult:
    return doc(env, "link", "47-FV-1001", "ISO-1234", "--project", "P123", *more, ok=ok)


def link_id(result: RunResult) -> str:
    last = result.stdout.splitlines()[-1]
    assert last.startswith("link ") and len(last.split()[1]) == 26
    return last.split()[1]


@pytest.fixture
def issued(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """ISO-1234 with revision A issued (IFR) and the tag 47-FV-1001."""
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")
    made.tag("47-FV-1001")
    return made


def issue_b(made: DocumentsWorld) -> None:
    made.create_revision("ISO-1234", purpose="For construction")
    made.attach("ISO-1234", "B", data=b"%PDF-1.7 sheet B, redrawn", name="sheet-B.pdf")
    made.issue("ISO-1234", "B", "IFC")


# --- link -----------------------------------------------------------------------------------------


def test_link_floats_or_pins_to_a_revision_or_to_the_current_one(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    pinned = link(env, "--pin", "A")
    assert pinned.stdout.splitlines()[0] == "linked 47-FV-1001 to ISO-1234 pinned A"
    issued.tag("47-FV-1002")
    current = doc(env, "link", "47-FV-1002", "ISO-1234", "--project", "P123", "--pin", "current")
    assert current.stdout.splitlines()[0] == "linked 47-FV-1002 to ISO-1234 pinned A"
    issued.tag("47-FV-1003")
    floating = doc(env, "link", "47-FV-1003", "ISO-1234", "--project", "P123")
    assert floating.stdout.splitlines()[0] == "linked 47-FV-1003 to ISO-1234 floating"
    assert issued.link_status(link_id(pinned)) == "active"


def test_link_refuses_a_bad_pin_a_missing_record_and_a_missing_document(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    bad = link(env, "--pin", "Z", ok=False)
    assert bad.stderr.startswith("error: ") and "'Z'" in bad.stderr
    no_record = doc(env, "link", "NOPE-9", "ISO-1234", "--project", "P123", ok=False)
    assert no_record.stderr.strip() == "error: no record with key 'NOPE-9' in project 'P123'"
    no_doc = doc(env, "link", "47-FV-1001", "NOPE-1", "--project", "P123", ok=False)
    assert no_doc.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"
    again = link(env, "--pin", "A")
    twice = link(env, "--pin", "A", ok=False)
    assert twice.stderr.startswith("error: ")
    assert issued.link_status(link_id(again)) == "active"


# --- stale and diff -------------------------------------------------------------------------------


def test_a_new_revision_makes_the_pinned_link_stale_and_stale_lists_it(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    pinned = link_id(link(env, "--pin", "A"))
    assert doc(env, "stale", "--project", "P123").stdout == ""
    issue_b(issued)
    out = doc(env, "stale", "--project", "P123").stdout
    assert out.splitlines() == [f"47-FV-1001  ->  ISO-1234  pin A  current B  {pinned}"]
    only = doc(env, "stale", "--project", "P123", "--document", "ISO-1234")
    assert only.stdout == out
    other = world_other_document(issued)
    assert doc(env, "stale", "--project", "P123", "--document", other).stdout == ""


def world_other_document(made: DocumentsWorld) -> str:
    made.register("ISO-2000")
    return "ISO-2000"


def test_diff_says_what_changed_between_two_revisions(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    issue_b(issued)
    out = doc(env, "diff", "ISO-1234", "A", "B", "--project", "P123").stdout.splitlines()
    assert out[0] == "ISO-1234: A (IFR) to B (IFC)"
    assert "- status IFR to IFC" in out
    assert any(line.startswith("- issued B (IFC, ") for line in out)
    assert any(line.startswith("- pdf changed: sheet.pdf") for line in out)
    bad = doc(env, "diff", "ISO-1234", "A", "Z", "--project", "P123", ok=False)
    assert bad.stderr.strip() == "error: 'Z' is not an issued revision of ISO-1234"


# --- repin ----------------------------------------------------------------------------------------


def test_repin_shows_the_diff_first_and_moves_the_pin_only_with_apply(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    pinned = link_id(link(env, "--pin", "A"))
    issue_b(issued)
    assert issued.link_status(pinned) == "stale"
    shown = doc(env, "repin", pinned, "--project", "P123")
    lines = shown.stdout.splitlines()
    assert lines[0] == "ISO-1234: A (IFR) to B (IFC)"
    assert lines[-1] == "not re-pinned; run again with --apply to confirm"
    assert issued.link_status(pinned) == "stale"
    done = doc(env, "repin", pinned, "--project", "P123", "--apply")
    assert done.stdout.splitlines()[-1] == f"re-pinned {pinned} to B"
    assert issued.link_status(pinned) == "active"
    assert doc(env, "stale", "--project", "P123").stdout == ""


def test_repin_takes_a_code_and_refuses_a_floating_or_unknown_link(
    env: dict[str, str], issued: DocumentsWorld
) -> None:
    pinned = link_id(link(env, "--pin", "A"))
    issue_b(issued)
    bad = doc(env, "repin", pinned, "--project", "P123", "--pin", "Z", "--apply", ok=False)
    assert bad.stderr.startswith("error: ")
    assert issued.link_status(pinned) == "stale"
    ok = doc(env, "repin", pinned, "--project", "P123", "--pin", "A", "--apply")
    assert ok.stdout.splitlines()[-1] == f"re-pinned {pinned} to A"
    issued.tag("47-FV-1002")
    floating = link_id(doc(env, "link", "47-FV-1002", "ISO-1234", "--project", "P123"))
    result = doc(env, "repin", floating, "--project", "P123", ok=False)
    assert result.stderr.strip() == "error: this link floats; it has no pin to move"
    ghost = doc(env, "repin", "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "--project", "P123", ok=False)
    assert ghost.stderr.strip() == "error: no link '01J9Z6Q4W3X2Y1V0T9S8R7Q6P5' in project 'P123'"
