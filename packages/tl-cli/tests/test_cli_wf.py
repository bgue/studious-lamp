"""`tl wf show` and `tl wf transition` against a temporary ledger (P0-I3-T10; brief 8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import open_uow
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A fresh ledger; the sample schema directory (workflow, expected link, numbering)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def create(env: dict[str, str], title: str) -> str:
    result = run(env, "record", "create", "--project", "P123", "--title", title)
    assert result.exit_code == 0, result.output
    return next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))


def record_id(env: dict[str, str], key: str) -> str:
    with sqlite3.connect(env["TL_DB"]) as db:
        return str(db.execute("SELECT id FROM cur_core_record WHERE key = ?", (key,)).fetchone()[0])


def link(env: dict[str, str], from_key: str, to_key: str) -> None:
    """Insert an active `references` link row directly (the link commands are another ticket)."""
    with sqlite3.connect(env["TL_DB"]) as db:
        db.execute(
            "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, source, "
            "declined, created_by, created_at, updated_at, version, last_seq) VALUES "
            "(?, 'project:P123', ?, ?, 'references', 'active', 'manual', 0, 'u', '2026', '2026', "
            "1, 1)",
            (
                f"L-{from_key}-{to_key}",
                record_id(env, from_key),
                record_id(env, to_key),
            ),
        )


def wf(env: dict[str, str], *args: str) -> RunResult:
    return run(env, "wf", *args)


# --- show ------------------------------------------------------------------------------------


def test_show_a_new_record_is_in_the_initial_state(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    result = wf(env, "show", "--project", "P123", key)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == f"key: {key}"
    assert lines[1] == "workflow: core.review v1"
    assert lines[2] == "state: Draft"
    assert lines[3].startswith("entered_at: 20")
    assert lines[4] == "version: 1"
    assert lines[5] == "option submit -> Review allowed"
    assert len(lines) == 6  # `submit` has no guards


def test_show_lists_guards_with_their_verdicts(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    assert wf(env, "transition", "--project", "P123", key, "submit").exit_code == 0
    result = wf(env, "show", "--project", "P123", key)
    lines = result.stdout.splitlines()
    assert "state: Review" in lines
    assert "option approve -> Approved blocked" in lines
    assert any(
        line.startswith("  guard expected_links FAILED missing links: supporting record (0 of 1)")
        for line in lines
    )
    assert any(line.startswith("  guard conformance ok ") for line in lines)
    assert "option reject -> Draft allowed" in lines


def test_show_takes_roles(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    other = create(env, "Support")
    link(env, key, other)
    for name in ("submit", "approve"):
        assert wf(env, "transition", "--project", "P123", key, name).exit_code == 0
    without = wf(env, "show", "--project", "P123", key).stdout
    assert "option issue -> Issued blocked" in without
    assert "guard roles FAILED needs one of the roles: manager" in without
    with_role = wf(env, "show", "--project", "P123", key, "--role", "manager").stdout
    assert "option issue -> Issued allowed" in with_role
    assert "guard roles ok role manager held" in with_role


def test_show_of_an_unknown_record_is_an_error(env: dict[str, str]) -> None:
    result = wf(env, "show", "--project", "P123", "NOPE-1")
    assert result.exit_code == 1
    assert "error: no record with key 'NOPE-1' in project 'P123'" in result.stderr


# --- transition ------------------------------------------------------------------------------


def test_transition_prints_the_new_state_and_changes_the_record(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    result = wf(env, "transition", "--project", "P123", key, "submit")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        f"transitioned {key} Draft -> Review",
        "version 2",
        "conformance ok",
    ]
    shown = run(env, "record", "show", "--project", "P123", key).stdout
    assert "status: Review" in shown
    assert "version: 2" in shown


def test_a_missing_expected_link_blocks_the_transition_until_it_exists(
    env: dict[str, str],
) -> None:
    key = create(env, "NCR")
    other = create(env, "Support")
    assert wf(env, "transition", "--project", "P123", key, "submit").exit_code == 0

    blocked = wf(env, "transition", "--project", "P123", key, "approve")
    assert blocked.exit_code == 1
    err = blocked.stderr.splitlines()
    assert err[0].startswith(f"error: cannot approve {key}:")
    assert "supporting record" in err[0]
    assert any(line.startswith("  guard expected_links FAILED ") for line in err)
    assert any(line.startswith("  guard conformance ok ") for line in err)
    assert "status: Review" in run(env, "record", "show", "--project", "P123", key).stdout

    link(env, key, other)
    allowed = wf(env, "transition", "--project", "P123", key, "approve")
    assert allowed.exit_code == 0, allowed.output
    assert allowed.stdout.splitlines()[0] == f"transitioned {key} Review -> Approved"
    assert "status: Approved" in run(env, "record", "show", "--project", "P123", key).stdout


def test_roles_come_from_the_option(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    other = create(env, "Support")
    link(env, key, other)
    for name in ("submit", "approve"):
        assert wf(env, "transition", "--project", "P123", key, name).exit_code == 0
    refused = wf(env, "transition", "--project", "P123", key, "issue", "--role", "clerk")
    assert refused.exit_code == 1
    assert "guard roles FAILED needs one of the roles: manager" in refused.stderr
    done = wf(
        env, "transition", "--project", "P123", key, "issue", "--role", "clerk", "--role", "manager"
    )
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines()[0] == f"transitioned {key} Approved -> Issued"


def test_the_transition_is_in_the_event_tail(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    wf(
        env,
        "transition",
        "--project",
        "P123",
        key,
        "submit",
        "--reason",
        "ready",
        "--actor",
        "user:ann",
    )
    tail = run(env, "events", "tail", "--project", "P123", "-n", "5").stdout
    assert "Workflow.Transitioned" in tail
    with open_uow(env["TL_DB"], readonly=True) as uow:
        row = (
            uow.conn()
            .execute(
                text(
                    "SELECT payload, actor, source FROM events "
                    "WHERE event_type = 'Workflow.Transitioned'"
                )
            )
            .one()
        )
    assert row.actor == "user:ann"
    assert row.source == "cli"
    assert '"reason":"ready"' in row.payload


def test_an_unknown_transition_lists_the_available_ones(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    result = wf(env, "transition", "--project", "P123", key, "nope")
    assert result.exit_code == 1
    assert "no transition 'nope'" in result.stderr
    assert "from Draft: submit" in result.stderr


def test_a_transition_from_another_state_is_refused(env: dict[str, str]) -> None:
    key = create(env, "NCR")
    result = wf(env, "transition", "--project", "P123", key, "issue")
    assert result.exit_code == 1
    assert "cannot start in state 'Draft'" in result.stderr


def test_an_unknown_record_is_an_error(env: dict[str, str]) -> None:
    result = wf(env, "transition", "--project", "P123", "NOPE-1", "submit")
    assert result.exit_code == 1
    assert "error: no record with key 'NOPE-1' in project 'P123'" in result.stderr


def test_a_record_with_no_workflow_is_reported(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = create(env, "NCR")
    empty = tmp_path / "empty-schema"
    empty.mkdir()
    monkeypatch.setenv("TL_SCHEMA_DIR", str(empty))
    result = wf(env, "show", "--project", "P123", key)
    assert result.exit_code == 1
    assert "no workflow applies" in result.stderr
    result = wf(env, "transition", "--project", "P123", key, "submit")
    assert result.exit_code == 1
    assert "no workflow applies" in result.stderr
