"""`tl admin roles ...` against a temporary SQLite ledger (RM-S3).

grant, ls, effective and revoke through ``CliRunner``; a signed-in plain user is refused by each of
the four commands, and nothing is written for the refused ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auth_support import GOOD, bootstrap, new_ledger, rows, separate_session, sign_in
from auth_support import run as tl

ROLES = ("admin", "roles")
P1 = "project:P1"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A ledger with the admin `root` signed in, and the plain users `alice` and `bob`."""
    values = new_ledger(tmp_path)
    assert bootstrap(values).exit_code == 0
    sign_in(values)
    for name in ("alice", "bob"):
        assert (
            tl(values, "admin", "user", "add", name, "--password-stdin", stdin=GOOD).exit_code == 0
        )
    return values


def grant(env: dict[str, str], who: str = "alice", role: str = "superuser", **more: str):  # type: ignore[no-untyped-def]
    fields = {"project": "P1", "module": "documents", "reason": "demo"} | more
    return tl(
        env, *ROLES, "grant", who, "--project", fields["project"], "--module", fields["module"],
        "--role", role, "--reason", fields["reason"],
    )  # fmt: skip


def revoke(env: dict[str, str], who: str = "alice", role: str = "superuser", **more: str):  # type: ignore[no-untyped-def]
    fields = {"project": "P1", "module": "documents", "reason": "over"} | more
    return tl(
        env, *ROLES, "revoke", who, "--project", fields["project"], "--module", fields["module"],
        "--role", role, "--reason", fields["reason"],
    )  # fmt: skip


def held(env: dict[str, str]) -> list[tuple[str, str, str]]:
    return [
        (str(a), str(b), str(c))
        for a, b, c in rows(
            env, "SELECT project, module, role FROM cur_account_module_role ORDER BY 1, 2, 3"
        )
    ]


def test_grant_says_what_it_did_and_writes_one_row(env: dict[str, str]) -> None:
    result = grant(env)
    assert result.exit_code == 0, result.output
    assert "granted superuser on documents for project:P1 to alice" in result.output
    assert held(env) == [(P1, "documents", "superuser")]


def test_a_second_grant_says_already_held_and_writes_nothing(env: dict[str, str]) -> None:
    grant(env)
    before = rows(env, "SELECT COUNT(*) FROM events")
    again = grant(env)
    assert again.exit_code == 0 and "already held" in again.output
    assert rows(env, "SELECT COUNT(*) FROM events") == before


def test_a_project_is_written_with_or_without_the_prefix(env: dict[str, str]) -> None:
    assert grant(env, project="project:P2", module="schedule", role="user").exit_code == 0
    assert held(env) == [("project:P2", "schedule", "user")]


def test_ls_lists_one_line_per_grant_and_filters(env: dict[str, str]) -> None:
    grant(env)
    grant(env, "bob", "viewer", project="P2", module="schedule")
    listed = tl(env, *ROLES, "ls")
    assert listed.exit_code == 0, listed.output
    lines = listed.stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("alice  project:P1  documents  superuser  by user:root  20")
    assert tl(env, *ROLES, "ls", "--project", "P2", "--user", "alice").stdout.strip() == ""
    only_bob = tl(env, *ROLES, "ls", "--user", "bob").stdout.splitlines()
    assert [line.split("  ")[0] for line in only_bob] == ["bob"]
    by_module = tl(env, *ROLES, "ls", "--module", "schedule").stdout.splitlines()
    assert len(by_module) == 1 and "bob" in by_module[0]


def test_ls_json_is_a_list_of_grant_views(env: dict[str, str]) -> None:
    grant(env)
    listed = json.loads(tl(env, *ROLES, "ls", "--json").stdout)
    assert [(g["username"], g["project"], g["module"], g["role"]) for g in listed] == [
        ("alice", P1, "documents", "superuser")
    ]
    assert {"account_id", "granted_by", "granted_at"} <= set(listed[0])


def test_effective_lists_every_module_with_its_source(env: dict[str, str]) -> None:
    grant(env)
    result = tl(env, *ROLES, "effective", "alice", "--project", "P1")
    assert result.exit_code == 0, result.output
    assert "documents  superuser  granted" in result.stdout
    assert "cost  user  derived" in result.stdout
    as_json = json.loads(tl(env, *ROLES, "effective", "alice", "--project", "P1", "--json").stdout)
    assert {v["module"]: v["source"] for v in as_json}["documents"] == "granted"
    other = tl(env, *ROLES, "effective", "alice", "--project", "P2")
    assert "documents  user  derived" in other.stdout


def test_revoke_says_what_it_did_and_removes_the_row(env: dict[str, str]) -> None:
    grant(env)
    result = revoke(env)
    assert result.exit_code == 0, result.output
    assert "revoked superuser on documents for project:P1 from alice" in result.output
    assert held(env) == []


def test_revoke_of_a_role_not_held_is_an_error_exit_1(env: dict[str, str]) -> None:
    result = revoke(env)
    assert result.exit_code == 1 and "error:" in result.output
    grant(env)
    assert revoke(env).exit_code == 0
    again = revoke(env)
    assert again.exit_code == 1 and "error:" in again.output


def test_refusals_are_plain_errors_with_exit_1(env: dict[str, str]) -> None:
    assert "no company-level roles" in grant(env, project="company", role="user").output
    assert grant(env, role="overlord").exit_code == 1
    assert grant(env, module="nowhere", role="user").exit_code == 1
    assert grant(env, "ghost").exit_code == 1  # an unknown account
    assert grant(env, reason="").exit_code == 1
    assert held(env) == []


def test_a_plain_user_is_refused_every_command_and_nothing_is_written(
    env: dict[str, str], tmp_path: Path
) -> None:
    grant(env, "bob", "viewer")
    mine = separate_session(env, tmp_path, "alice")
    sign_in(mine, "alice")
    for args in (
        ("grant", "alice", "--project", "P1", "--module", "documents", "--role", "superuser",
         "--reason", "x"),
        ("revoke", "bob", "--project", "P1", "--module", "documents", "--role", "viewer",
         "--reason", "x"),
        ("ls",),
        ("effective", "alice", "--project", "P1"),
    ):  # fmt: skip
        result = tl(mine, *ROLES, *args)
        assert result.exit_code == 1 and "forbidden" in result.output, (args, result.output)
    assert held(env) == [(P1, "documents", "viewer")]


def test_with_no_session_the_commands_are_refused(env: dict[str, str], tmp_path: Path) -> None:
    nobody = separate_session(env, tmp_path, "nobody")
    for args in (("ls",), ("effective", "alice", "--project", "P1")):
        assert tl(nobody, *ROLES, *args).exit_code != 0


def test_a_grant_changes_what_effective_says_for_that_project_only(env: dict[str, str]) -> None:
    grant(env, "bob", "viewer")
    on_p1 = tl(env, *ROLES, "effective", "bob", "--project", "P1").stdout
    on_p2 = tl(env, *ROLES, "effective", "bob", "--project", "P2").stdout
    assert "documents  viewer  granted" in on_p1
    assert "documents  user  derived" in on_p2
