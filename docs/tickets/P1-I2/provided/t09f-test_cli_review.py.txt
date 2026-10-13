"""`tl review open|answer|on-behalf|close|override|ls` on a temporary ledger (P1-I2-T09f).

Documents, revisions and the reviewers' accounts are made with the module's own test world
(`doccli_support.world`); the review cycles under test are opened, answered and closed by the
commands. A reviewer answers as themselves: the tests pass `--actor user:<name>`.
"""

from __future__ import annotations

from collections.abc import Callable
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
CYCLE = "ISO-1234@A/RC1"


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def draft(env: dict[str, str], tmp_path: Path) -> DocumentsWorld:
    """ISO-1234 with a draft revision A and a PDF; accounts for u (the author), ana and bo."""
    made = world(env, tmp_path)
    made.people("u", "ana", "bo", password="correct horse battery")
    made.register("ISO-1234")
    made.create_revision("ISO-1234")
    made.attach("ISO-1234", "A")
    return made


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def review(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "review", *args, ok=ok)


def open_cycle(env: dict[str, str], *more: str, ok: bool = True) -> RunResult:
    base = ("open", "ISO-1234", "A", "--project", "P123")
    reviewers = ("--reviewer", "user:ana", "--reviewer", "user:bo")
    return review(env, *base, *(more or reviewers), ok=ok)


def answer(env: dict[str, str], who: str, outcome: str, *more: str, ok: bool = True) -> RunResult:
    args = ("answer", CYCLE, "--project", "P123", "--outcome", outcome, "--actor", f"user:{who}")
    return review(env, *args, *more, ok=ok)


def listing(env: dict[str, str]) -> list[str]:
    return review(env, "ls", "ISO-1234", "A", "--project", "P123").stdout.splitlines()


# --- open and ls ----------------------------------------------------------------------------------


def test_open_starts_a_round_and_ls_shows_the_reviewers(
    env: dict[str, str], draft: DocumentsWorld
) -> None:
    result = open_cycle(
        env, "--reviewer", "user:ana", "--reviewer", "user:bo", "--due", "2026-10-20"
    )
    assert result.stdout.splitlines() == [f"opened {CYCLE} round 1", "reviewers 2"]
    assert listing(env) == [
        f"{CYCLE}  round=1  open  due=2026-10-20  outcome=-",
        "  user:ana  pending  -  -",
        "  user:bo  pending  -  -",
    ]
    assert draft.revision("ISO-1234", "A").state == "In Review"


def test_open_refuses_what_the_module_refuses(env: dict[str, str], draft: DocumentsWorld) -> None:
    nobody = open_cycle(env, "--reviewer", "user:nobody", ok=False)
    assert "not an active person account" in nobody.stderr
    author = open_cycle(env, "--reviewer", "user:u", ok=False)
    assert "at least one other reviewer" in author.stderr
    twice = open_cycle(env, "--reviewer", "user:ana", "--reviewer", "user:ana", ok=False)
    assert "only once" in twice.stderr
    ghost = review(
        env, "open", "ISO-1234", "Z", "--project", "P123", "--reviewer", "user:ana", ok=False
    )
    assert ghost.stderr.strip() == "error: no revision 'Z' of ISO-1234"
    assert listing(env) == []
    open_cycle(env)
    again = open_cycle(env, ok=False)
    assert "only a draft can be sent for review" in again.stderr


# --- answer and close -----------------------------------------------------------------------------


def test_a_reviewer_answers_for_themselves_and_close_takes_the_worst(
    env: dict[str, str], draft: DocumentsWorld
) -> None:
    open_cycle(env)
    first = answer(env, "ana", "approved_with_comments", "--comment", "check the weld map")
    assert first.stdout.strip() == f"answered {CYCLE}: approved_with_comments by user:ana"
    again = answer(env, "ana", "approved", ok=False)
    assert "already answered" in again.stderr
    stranger = answer(env, "u", "approved", ok=False)
    assert "is not a reviewer" in stranger.stderr
    early = review(env, "close", CYCLE, "--project", "P123", ok=False)
    assert "user:bo have not answered" in early.stderr
    answer(env, "bo", "approved")
    done = review(env, "close", CYCLE, "--project", "P123")
    assert done.stdout.strip() == f"closed {CYCLE}: approved_with_comments"
    assert listing(env)[0] == f"{CYCLE}  round=1  closed  due=-  outcome=approved_with_comments"
    assert "  user:ana  approved_with_comments" in listing(env)[1]
    assert draft.revision("ISO-1234", "A").state == "Draft"
    bad = review(env, "close", CYCLE, "--project", "P123", ok=False)
    assert "already closed" in bad.stderr


def test_a_bad_outcome_is_an_input_error(env: dict[str, str], draft: DocumentsWorld) -> None:
    open_cycle(env)
    bad = answer(env, "ana", "shrug", ok=False)
    assert bad.stderr.startswith("error: outcome:")
    ghost = review(
        env, "answer", "NOPE@A/RC1", "--project", "P123", "--outcome", "approved", ok=False
    )
    assert ghost.stderr.strip() == "error: no review cycle 'NOPE@A/RC1' in project 'P123'"


def test_a_person_cannot_close_milder_than_the_worst_answer(
    env: dict[str, str], draft: DocumentsWorld
) -> None:
    open_cycle(env)
    answer(env, "ana", "rejected", "--comment", "wrong line class")
    answer(env, "bo", "approved")
    milder = review(env, "close", CYCLE, "--project", "P123", "--outcome", "approved", ok=False)
    assert "only an admin can close it as approved" in milder.stderr
    stricter_still = review(env, "close", CYCLE, "--project", "P123", "--outcome", "rejected")
    assert stricter_still.stdout.strip() == f"closed {CYCLE}: rejected"


def test_an_unanswered_round_is_withdrawn(env: dict[str, str], draft: DocumentsWorld) -> None:
    open_cycle(env)
    args = ("close", CYCLE, "--project", "P123", "--reason", "review withdrawn")
    for outcome in ("approved", "rejected"):
        mild = review(env, *args, "--outcome", outcome, ok=False)
        assert "nobody has answered" in mild.stderr
    done = review(env, *args)
    assert done.stdout.strip() == f"closed {CYCLE}: withdrawn"
    assert listing(env)[0] == f"{CYCLE}  round=1  closed  due=-  outcome=withdrawn"


def test_only_the_opener_or_the_author_closes_a_cycle(
    env: dict[str, str], draft: DocumentsWorld
) -> None:
    open_cycle(env, "--reviewer", "user:ana", "--actor", "user:bo")
    answer(env, "ana", "approved")
    stranger = review(
        env, "close", CYCLE, "--project", "P123", "--reason", "x", "--actor", "user:ana", ok=False
    )
    assert "neither opened" in stranger.stderr
    author = review(env, "close", CYCLE, "--project", "P123", "--reason", "x", "--actor", "user:u")
    assert author.stdout.strip() == f"closed {CYCLE}: approved"


# --- the admin's two corrections ------------------------------------------------------------------


def test_on_behalf_and_override_are_for_an_admin(
    env: dict[str, str], draft: DocumentsWorld, tmp_path: Path
) -> None:
    open_cycle(env)
    answer(env, "ana", "rejected", "--comment", "wrong line class")
    behalf = ("on-behalf", CYCLE, "--project", "P123", "--reviewer", "user:bo")
    behalf += ("--outcome", "approved", "--comment", "Bo replied by mail on the 12th")
    over = ("override", CYCLE, "--project", "P123", "--outcome", "approved_with_comments")
    over += (
        "--reason",
        "rejection withdrawn after the call",
    )
    can_refuse = admin_session(env)
    if can_refuse:
        amy = ordinary_env(env, tmp_path)
        for args in (behalf, over):
            refused = review(amy, *args, ok=False)
            assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
    done = review(env, *behalf)
    assert done.stdout.strip().startswith(f"recorded {CYCLE}: approved for user:bo by user:")
    assert "  user:bo  approved" in listing(env)[2]
    closed = review(env, *over)
    assert closed.stdout.strip() == f"closed {CYCLE}: approved_with_comments (overridden)"
    assert listing(env)[0].endswith("outcome=approved_with_comments")
