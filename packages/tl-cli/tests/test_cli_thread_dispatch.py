"""`tl thread preview|dispatch|reminders` on a temporary ledger (P1-I7 WS-B, T09b).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from thread_cli_support import P, create, run, thread_env
from tl_adapters.db import DbTarget, open_uow
from typer.testing import Result as RunResult


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    return thread_env(new_db, monkeypatch, tmp_path)


def preview(env: dict[str, str], key: str, line: str) -> RunResult:
    return run(env, "thread", "preview", "--project", P, key, line)


def token_of(result: RunResult) -> str:
    assert result.exit_code == 0, result.output
    line = result.stdout.splitlines()[0]
    assert line.startswith("token ") and len(line) == 6 + 64, line
    return line.split()[1]


def count(env: dict[str, str], sql: str) -> int:
    with open_uow(env["TL_DB"], readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_preview_lists_the_plan_with_the_token_and_writes_nothing(env: dict[str, str]) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    events = count(env, "SELECT COUNT(*) FROM events")
    shown = preview(env, key, f"/link {other} as requires")
    token = token_of(shown)
    lines = shown.stdout.splitlines()
    assert lines[1].startswith("expires ")
    assert lines[2] == f"1. AddLink  user  ok  Link {key} to {other} (requires)"
    assert lines[-1] == "can dispatch: yes"
    assert token and count(env, "SELECT COUNT(*) FROM events") == events


def test_preview_shows_a_creation_with_its_link_and_a_refusal_with_its_problem(
    env: dict[str, str],
) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    raised = preview(env, key, f"/raise record #{other} Clash at grid C4")
    token_of(raised)
    lines = raised.stdout.splitlines()
    assert lines[2].startswith("1. CreateRecord  user  ok  Create record: Clash at grid C4")
    assert lines[3].startswith("2. AddLink  user  ok  Link the new record raised against ")
    assert f"link: new record dispatched_from {key}" in lines
    refused = preview(env, key, "/link NOPE-1")
    assert refused.exit_code == 0 and "problem: unknown_key:" in refused.stdout
    assert refused.stdout.splitlines()[-1] == "can dispatch: no"
    unavailable = preview(env, key, "/hold waiting")
    assert "problem: dispatch_unavailable:" in unavailable.stdout


def test_preview_of_a_bad_line_is_one_error_line(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    for line in ("/link", "hello", "/frobnicate"):
        result = preview(env, key, line)
        assert result.exit_code == 1 and result.stderr.startswith("error: ")
    assert "not_a_dispatch" in preview(env, key, "hello").stderr
    assert "missing_argument" in preview(env, key, "/link").stderr


def test_dispatch_runs_the_previewed_line_with_its_token(env: dict[str, str]) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    line = f"/raise record #{other} Clash at grid C4"
    token = token_of(preview(env, key, line))
    done = run(env, "thread", "dispatch", "--project", P, key, line, "--token", token)
    assert done.exit_code == 0, done.output
    lines = done.stdout.splitlines()
    assert lines[0].startswith("dispatched ") and len(lines[0].split()[1]) == 26
    assert (
        lines[1]
        == "verb raise  Create record: Clash at grid C4; Link the new record raised against "
        + other
    )
    assert lines[2].startswith("  CreateRecord  ") and lines[2].endswith("  v1")
    assert count(env, "SELECT COUNT(*) FROM cur_core_record WHERE title = 'Clash at grid C4'") == 1
    assert count(env, "SELECT COUNT(*) FROM cur_links WHERE relation = 'dispatched_from'") == 1
    shown = run(env, "thread", "show", "--project", P, key)
    assert "    -> raise: Create record: Clash at grid C4" in shown.stdout


def test_dispatch_with_yes_previews_prints_the_plan_and_runs_it(env: dict[str, str]) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    done = run(env, "thread", "dispatch", "--project", P, key, f"/link {other}", "--yes")
    assert done.exit_code == 0, done.output
    lines = done.stdout.splitlines()
    assert lines[0].startswith("token ") and any(ln.startswith("dispatched ") for ln in lines)
    assert count(env, "SELECT COUNT(*) FROM cur_links") == 1


def test_dispatch_needs_a_token_or_yes_and_refuses_a_stale_or_forged_one(
    env: dict[str, str],
) -> None:
    key, other = create(env, "Gate valve"), create(env, "Spool")
    neither = run(env, "thread", "dispatch", "--project", P, key, f"/link {other}")
    assert neither.exit_code == 1 and "--token" in neither.stderr and "--yes" in neither.stderr
    both = run(
        env,
        "thread",
        "dispatch",
        "--project",
        P,
        key,
        f"/link {other}",
        "--token",
        "0" * 64,
        "--yes",
    )
    assert both.exit_code == 1
    token = token_of(preview(env, key, f"/link {other}"))
    stale = run(
        env,
        "thread",
        "dispatch",
        "--project",
        P,
        key,
        f"/link {other} as requires",
        "--token",
        token,
    )
    assert stale.exit_code == 1 and "plan is not the one you previewed" in stale.stderr
    forged = run(
        env, "thread", "dispatch", "--project", P, key, f"/link {other}", "--token", "f" * 64
    )
    assert forged.exit_code == 1 and "previewed" in forged.stderr
    assert count(env, "SELECT COUNT(*) FROM cur_links") == 0
    assert count(env, "SELECT COUNT(*) FROM cur_thread_message") == 0


def test_a_command_that_cannot_run_is_not_dispatched(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    token = token_of(preview(env, key, "/hold waiting"))
    refused = run(env, "thread", "dispatch", "--project", P, key, "/hold waiting", "--token", token)
    assert refused.exit_code == 1 and refused.stderr.startswith("error: ")
    assert count(env, "SELECT COUNT(*) FROM cur_thread_message") == 0


def test_summarise_posts_a_counted_summary(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    run(env, "thread", "post", "--project", P, key, "Flanges short")
    done = run(env, "thread", "dispatch", "--project", P, key, "/summarise", "--yes")
    assert done.exit_code == 0, done.output
    shown = run(env, "thread", "show", "--project", P, key).stdout
    assert "Thread summary (counted by the system, no model)." in shown


def test_remind_queues_a_job_and_reminders_posts_it_when_due(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    done = run(
        env, "thread", "dispatch", "--project", P, key, "/remind +1h check the bevels", "--yes"
    )
    assert done.exit_code == 0, done.output
    assert count(env, "SELECT COUNT(*) FROM job_queue WHERE kind = 'thread.reminder'") == 1
    early = run(env, "thread", "reminders")
    assert early.exit_code == 0 and early.stdout.strip() == "ran 0 reminders"
    with open_uow(env["TL_DB"]) as uow:  # the hour has passed
        uow.conn().execute(text("UPDATE job_queue SET run_after = '2000-01-01T00:00:00.000000Z'"))
    due = run(env, "thread", "reminders")
    assert due.exit_code == 0 and due.stdout.strip() == "ran 1 reminder"
    shown = run(env, "thread", "show", "--project", P, key).stdout
    assert "Reminder from " in shown and ": check the bevels" in shown
    assert run(env, "thread", "reminders").stdout.strip() == "ran 0 reminders"
