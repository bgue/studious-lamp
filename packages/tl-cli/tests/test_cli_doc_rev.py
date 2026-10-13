"""`tl doc rev create|issue|supersede|void|ls` on a temporary ledger (P1-I2-T09b).

Documents, files and links are made with the module's own test world (`doccli_support.world`);
the revisions under test are made with the CLI.
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
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
TODAY = datetime.now(UTC).date().isoformat()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def rev(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "doc", "rev", *args, ok=ok)


def lines(env: dict[str, str], number: str = "ISO-1234") -> list[str]:
    return rev(env, "ls", number, "--project", "P123").stdout.splitlines()


def draft(env: dict[str, str], tmp_path: Path) -> object:
    """ISO-1234 registered, with no revision yet; returns the test world on the same ledger."""
    made = world(env, tmp_path)
    made.register("ISO-1234")
    return made


# --- create and ls --------------------------------------------------------------------------------


def test_create_starts_the_next_revision_as_a_draft(env: dict[str, str], tmp_path: Path) -> None:
    draft(env, tmp_path)
    result = rev(env, "create", "ISO-1234", "--project", "P123", "--purpose", "First draft")
    assert result.stdout.strip() == "created revision A Draft"
    assert lines(env) == ["revision A Draft - - -"]


def test_a_second_open_revision_and_a_bad_code_are_refused(
    env: dict[str, str], tmp_path: Path
) -> None:
    draft(env, tmp_path)
    rev(env, "create", "ISO-1234", "--project", "P123")
    again = rev(env, "create", "ISO-1234", "--project", "P123", ok=False)
    assert again.stderr.strip() == (
        "error: revision A of ISO-1234 is still Draft; issue or void it before starting another"
    )
    assert lines(env) == ["revision A Draft - - -"]
    other = rev(env, "create", "NOPE-1", "--project", "P123", ok=False)
    assert other.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"


def test_create_takes_a_code_and_checks_it_against_the_scheme(
    env: dict[str, str], tmp_path: Path
) -> None:
    draft(env, tmp_path)
    bad = rev(env, "create", "ISO-1234", "--project", "P123", "--code", "7", ok=False)
    assert "is not a code of the alpha scheme" in bad.stderr
    assert lines(env) == []
    ok = rev(env, "create", "ISO-1234", "--project", "P123", "--code", "A")
    assert ok.stdout.strip() == "created revision A Draft"


def test_ls_of_an_unknown_document_is_an_error(env: dict[str, str]) -> None:
    result = rev(env, "ls", "NOPE-1", "--project", "P123", ok=False)
    assert result.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"


# --- issue ----------------------------------------------------------------------------------------


def test_issue_is_for_an_admin_and_needs_a_rendition(env: dict[str, str], tmp_path: Path) -> None:
    made = draft(env, tmp_path)
    rev(env, "create", "ISO-1234", "--project", "P123")
    can_refuse = admin_session(env)
    if can_refuse:
        amy = ordinary_env(env, tmp_path)
        refused = rev(
            amy, "issue", "ISO-1234", "A", "--project", "P123", "--status", "IFR", ok=False
        )
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    bare = rev(env, "issue", "ISO-1234", "A", "--project", "P123", "--status", "IFR", ok=False)
    assert "has no PDF or native rendition" in bare.stderr
    assert lines(env) == ["revision A Draft - - -"]
    made.attach("ISO-1234", "A")  # type: ignore[attr-defined]
    unknown = rev(env, "issue", "ISO-1234", "A", "--project", "P123", "--status", "XYZ", ok=False)
    assert "'XYZ' is not an issue status" in unknown.stderr
    done = rev(env, "issue", "ISO-1234", "A", "--project", "P123", "--status", "IFR")
    assert done.stdout.splitlines() == [f"issued ISO-1234@A as IFR on {TODAY}"]
    assert lines(env) == [f"revision A Issued IFR review {TODAY} current"]


def test_issue_dates_are_today_unless_a_reason_backs_an_earlier_one(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = draft(env, tmp_path)
    rev(env, "create", "ISO-1234", "--project", "P123")
    made.attach("ISO-1234", "A")  # type: ignore[attr-defined]
    admin_session(env)
    base = ("issue", "ISO-1234", "A", "--project", "P123", "--status", "IFR")
    future = rev(env, *base, "--date", "2999-01-01", ok=False)
    assert "future" in future.stderr
    early = rev(env, *base, "--date", "2026-01-05", ok=False)
    assert "reason" in early.stderr
    assert lines(env) == ["revision A Draft - - -"]
    done = rev(env, *base, "--date", "2026-01-05", "--date-reason", "issued by post on the 5th")
    assert done.stdout.splitlines() == ["issued ISO-1234@A as IFR on 2026-01-05"]


def test_issuing_a_new_revision_flags_the_links_pinned_to_the_old_one(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")  # type: ignore[attr-defined]
    link = made.link(made.tag(), "ISO-1234", "A")  # type: ignore[attr-defined]
    rev(env, "create", "ISO-1234", "--project", "P123", "--purpose", "For construction")
    made.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")  # type: ignore[attr-defined]
    admin_session(env)
    done = rev(env, "issue", "ISO-1234", "B", "--project", "P123", "--status", "IFC")
    assert done.stdout.splitlines() == [
        f"issued ISO-1234@B as IFC on {TODAY}",
        "flagged 1 link stale",
    ]
    assert made.link_status(link) == "stale"  # type: ignore[attr-defined]
    assert lines(env) == [
        f"revision A Issued IFR review {TODAY} current",
        f"revision B Issued IFC construction {TODAY} current",
    ]


# --- supersede and void ---------------------------------------------------------------------------


def test_supersede_is_for_an_admin_and_names_the_revision_that_replaces_it(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")  # type: ignore[attr-defined]
    rev(env, "create", "ISO-1234", "--project", "P123")
    made.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")  # type: ignore[attr-defined]
    can_refuse = admin_session(env)
    rev(env, "issue", "ISO-1234", "B", "--project", "P123", "--status", "IFC")
    args = ("supersede", "ISO-1234", "A", "--by", "B", "--project", "P123", "--reason", "re-drawn")
    if can_refuse:
        refused = rev(ordinary_env(env, tmp_path), *args, ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    done = rev(env, *args)
    assert done.stdout.strip() == "superseded ISO-1234@A by B"
    assert lines(env)[0].startswith("revision A Superseded IFR review")
    ghost = rev(
        env,
        "supersede",
        "ISO-1234",
        "A",
        "--by",
        "Z",
        "--project",
        "P123",
        "--reason",
        "x",
        ok=False,
    )
    assert ghost.stderr.strip() == "error: no revision 'Z' of ISO-1234"


def test_void_ends_a_draft_and_an_issued_revision_cannot_be_voided(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = world(env, tmp_path)
    made.issued_document("ISO-1234", "IFR")  # type: ignore[attr-defined]
    rev(env, "create", "ISO-1234", "--project", "P123")
    done = rev(env, "void", "ISO-1234", "B", "--project", "P123", "--reason", "started in error")
    assert done.stdout.strip() == "voided ISO-1234@B"
    assert lines(env)[1].startswith("revision B Void")
    issued = rev(env, "void", "ISO-1234", "A", "--project", "P123", "--reason", "x", ok=False)
    assert issued.stderr.startswith("error: ")
    assert lines(env)[0].startswith("revision A Issued")
