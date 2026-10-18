"""`tl thread show|post|edit|retract` on a temporary ledger (P1-I7 WS-B, T09a).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from thread_cli_support import P, create, run, thread_env
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_cli.thread import message_lines
from tl_core.integration.contract import RecordRef
from tl_core.threads.contract import DispatchOutcome, ThreadMessageView
from tl_core.threads.queries import ThreadPage
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    return thread_env(new_db, monkeypatch, tmp_path)


def posted_id(result: RunResult) -> str:
    first = result.stdout.splitlines()[0].split()
    assert first[0] == "posted" and len(first[1]) == 26, result.stdout
    return first[1]


def test_the_thread_group_is_in_the_help() -> None:
    assert "thread" in runner.invoke(app, ["--help"]).stdout
    helped = runner.invoke(app, ["thread", "--help"]).stdout
    for name in ("show", "post", "edit", "retract", "preview", "dispatch", "reminders"):
        assert name in helped


def test_post_prints_the_id_the_mentions_and_the_refs(env: dict[str, str]) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    plain = run(env, "thread", "post", "--project", P, key, "just a note")
    assert plain.exit_code == 0, plain.output
    assert len(plain.stdout.splitlines()) == 1 and posted_id(plain)
    rich = run(env, "thread", "post", "--project", P, key, f"see #{other} @lchen @party:acme")
    assert rich.exit_code == 0, rich.output
    assert posted_id(rich)
    assert rich.stdout.splitlines()[1:] == ["mentions @lchen, @party:acme", "refs 1"]


def test_show_lists_the_messages_oldest_first_with_the_header(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    first = posted_id(run(env, "thread", "post", "--project", P, key, "Flanges short\nfor W019"))
    second = posted_id(run(env, "thread", "post", "--project", P, key, "On it @lchen"))
    shown = run(env, "thread", "show", "--project", P, key)
    assert shown.exit_code == 0, shown.output
    lines = shown.stdout.splitlines()
    assert lines[0] == f"thread {key}  threads on  dispatch on  2 messages"
    assert lines[1].startswith("participants ") and "creator" in lines[1]
    assert lines[2].startswith(f"{first}  ") and lines[2].endswith("  Flanges short")
    assert lines[3].startswith(f"{second}  ") and lines[3].endswith("  On it @lchen")
    assert len(lines) == 4


def test_show_of_a_record_with_no_thread_and_with_threads_off(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    empty = run(env, "thread", "show", "--project", P, key)
    assert empty.exit_code == 0 and empty.stdout.splitlines()[0] == (
        f"thread {key}  threads on  dispatch on  0 messages"
    )


def test_show_pages_back_with_older(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    for n in range(4):
        run(env, "thread", "post", "--project", P, key, f"m{n}")
    newest = run(env, "thread", "show", "--project", P, key, "--limit", "2")
    lines = newest.stdout.splitlines()
    assert lines[-1].startswith("older: --before ")
    assert lines[-2].endswith("  m3") and lines[-3].endswith("  m2")
    cursor = lines[-1].split()[-1]
    older = run(env, "thread", "show", "--project", P, key, "--limit", "2", "--before", cursor)
    assert older.stdout.splitlines()[-1].endswith("  m1") and "older:" not in older.stdout


def test_edit_and_retract_are_the_authors_and_show_marks_them(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    mid = posted_id(run(env, "thread", "post", "--project", P, key, "first"))
    edited = run(env, "thread", "edit", "--project", P, key, mid, "second")
    assert edited.exit_code == 0 and edited.stdout.strip() == f"edited {mid}"
    assert (
        run(env, "thread", "show", "--project", P, key)
        .stdout.splitlines()[-1]
        .endswith("  second  (edited)")
    )
    again = run(env, "thread", "edit", "--project", P, key, mid, "second")
    assert again.exit_code == 1 and again.stderr.startswith("error: ")
    gone = run(env, "thread", "retract", "--project", P, key, mid, "--reason", "oops")
    assert gone.exit_code == 0 and gone.stdout.strip() == f"retracted {mid}"
    assert (
        run(env, "thread", "show", "--project", P, key)
        .stdout.splitlines()[-1]
        .endswith("  [retracted]")
    )


def test_a_slash_post_is_text_and_dispatches_nothing(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    result = run(env, "thread", "post", "--project", P, key, "/raise record Something")
    assert result.exit_code == 0, result.output
    assert "/raise record Something" in run(env, "thread", "show", "--project", P, key).stdout
    assert "Something" not in run(env, "record", "ls", "--project", P).stdout


def test_errors_are_one_error_line_and_exit_1(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    for args in (
        ["thread", "post", "--project", P, "NOPE-1", "hello"],
        ["thread", "post", "--project", P, key, "   "],
        ["thread", "show", "--project", P, "NOPE-1"],
        ["thread", "edit", "--project", P, key, "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "x"],
        ["thread", "retract", "--project", P, key, "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "--reason", "r"],
    ):
        result = run(env, *args)
        assert result.exit_code == 1, args
        assert result.stderr.startswith("error: ") and "Traceback" not in result.output


def test_threads_off_is_refused_with_the_reason(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(new_db())}
    assert run(values, "init").exit_code == 0
    key = create(values, "Gate valve")
    refused = run(values, "thread", "post", "--project", P, key, "hello")
    assert refused.exit_code == 1 and "threads are not switched on" in refused.stderr


def test_post_takes_an_actor(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    result = run(env, "thread", "post", "--project", P, key, "found a leak", "--actor", "user:kim")
    assert result.exit_code == 0, result.output
    assert " kim  found a leak" in run(env, "thread", "show", "--project", P, key).stdout


def test_a_dispatch_message_shows_its_outcome_on_the_next_line() -> None:
    def message(summary: str) -> ThreadMessageView:
        outcome = DispatchOutcome(message_id="M1", verb="status", summary=summary)
        return ThreadMessageView(
            message_id="M1",
            record_id="R1",
            author="user:rgarcia",
            body="/status done",
            posted_at="2026-01-02T03:04:05Z",
            dispatch=outcome,
        )

    record = RecordRef(id="R1", key="REC-1", record_type="core.Record")
    for summary, shown in (("moved to Done", "moved to Done"), ("", "done")):
        page = ThreadPage(
            record=record, enabled=True, dispatch_enabled=True, messages=[message(summary)]
        )
        assert message_lines(page) == [
            "M1  2026-01-02 03:04  rgarcia  /status done",
            f"    -> status: {shown}",
        ]
