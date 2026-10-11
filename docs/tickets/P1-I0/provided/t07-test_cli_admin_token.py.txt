"""`tl admin token ...` against a temporary SQLite ledger (P1-I0-T07)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from auth_support import GOOD, bootstrap, new_ledger, rows, separate_session, sign_in
from auth_support import run as tl
from tl_cli.session import open_backend
from tl_core.auth import sessions
from tl_core.auth.errors import InvalidCredentialsError

TOKEN = re.compile(r"^tla_[A-Za-z0-9_-]{43}$")
ID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A ledger with the admin `root` (signed in) and the agent account `triage`."""
    values = new_ledger(tmp_path)
    assert bootstrap(values).exit_code == 0
    sign_in(values)
    assert tl(values, "admin", "user", "add", "triage", "--kind", "agent").exit_code == 0
    return values


def issue(env: dict[str, str], *extra: str, name: str = "triage", label: str = "mcp") -> str:
    result = tl(env, "admin", "token", "issue", name, "--label", label, *extra)
    assert result.exit_code == 0, result.output
    return result.stdout.strip()


def events(env: dict[str, str], kind: str) -> list[tuple[str, str]]:
    found = rows(env, "SELECT actor, payload FROM events WHERE event_type = ? ORDER BY seq", kind)
    return [(str(a), str(p)) for a, p in found]


def test_issue_prints_the_token_alone_on_stdout_and_the_facts_on_stderr(
    env: dict[str, str],
) -> None:
    result = tl(env, "admin", "token", "issue", "triage", "--label", "mcp")
    assert result.exit_code == 0
    assert TOKEN.fullmatch(result.stdout.strip()) and result.stdout.count("\n") == 1
    assert result.stderr.startswith("issued token ") and "agent:triage" in result.stderr
    assert "only time it is shown" in result.stderr and result.stdout.strip() not in result.stderr


def test_the_token_authenticates_as_the_agent_and_is_not_kept_anywhere(
    env: dict[str, str],
) -> None:
    token = issue(env)
    principal = sessions.principal_for_bearer(open_backend(Path(env["TL_DB"])), token)
    assert principal.actor == "agent:triage" and principal.via == "agent_token"
    created = events(env, "AgentToken.Issued")
    assert created[-1][0] == "user:root" and token not in created[-1][1]
    listed = tl(env, "admin", "token", "ls")
    assert token not in listed.output
    assert token not in tl(env, "admin", "audit").output


def listed(env: dict[str, str]) -> dict[str, list[str]]:
    """``tl admin token ls`` as {label: [id, agent, label, expires, state]}."""
    lines = tl(env, "admin", "token", "ls").stdout.splitlines()
    return {line.split("  ")[2]: line.split("  ") for line in lines}


def days_left(expires: str) -> float:
    return (datetime.fromisoformat(expires) - datetime.now(UTC)).total_seconds() / 86400


def test_by_default_a_token_expires_in_about_ninety_days(env: dict[str, str]) -> None:
    issue(env)
    token_id, agent, label, expires, state = listed(env)["mcp"]
    assert ID.fullmatch(token_id) and (agent, label, state) == ("triage", "mcp", "active")
    assert 89.9 < days_left(expires) < 90.1


def test_days_and_no_expiry_choose_the_lifetime(env: dict[str, str]) -> None:
    issue(env, "--days", "7", label="week")
    issue(env, "--no-expiry", label="forever")
    tokens = listed(env)
    assert tokens["forever"][3] == "never"
    assert 6.9 < days_left(tokens["week"][3]) < 7.1


@pytest.mark.parametrize("extra", [["--days", "0"], ["--days", "4000"], ["--days", "x"]])
def test_days_outside_the_limits_is_a_usage_error(env: dict[str, str], extra: list[str]) -> None:
    result = tl(env, "admin", "token", "issue", "triage", "--label", "x", *extra)
    assert result.exit_code == 2 and result.stdout == ""


def test_days_and_no_expiry_together_are_refused(env: dict[str, str]) -> None:
    result = tl(
        env, "admin", "token", "issue", "triage", "--label", "x", "--days", "5", "--no-expiry"
    )
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr == "error: use --days or --no-expiry, not both\n"


def test_an_explicit_default_number_of_days_does_not_slip_past_no_expiry(
    env: dict[str, str],
) -> None:
    result = tl(
        env, "admin", "token", "issue", "triage", "--label", "x", "--days", "90", "--no-expiry"
    )
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr == "error: use --days or --no-expiry, not both\n"
    assert tl(env, "admin", "token", "ls").stdout == ""  # nothing was issued


def test_a_token_is_only_for_an_agent_account_that_exists_and_is_enabled(
    env: dict[str, str],
) -> None:
    person = tl(env, "admin", "token", "issue", "root", "--label", "x")
    assert person.exit_code == 1 and "agent" in person.stderr and person.stdout == ""
    ghost = tl(env, "admin", "token", "issue", "ghost", "--label", "x")
    assert ghost.exit_code == 1 and ghost.stderr == "error: no account named 'ghost'\n"
    assert tl(env, "admin", "user", "disable", "triage").exit_code == 0
    off = tl(env, "admin", "token", "issue", "triage", "--label", "x")
    assert off.exit_code == 1 and "disabled" in off.stderr and off.stdout == ""
    blank = tl(env, "admin", "token", "issue", "triage")
    assert blank.exit_code == 2  # --label is required


def test_ls_hides_revoked_tokens_unless_asked_and_can_filter_by_agent(env: dict[str, str]) -> None:
    assert tl(env, "admin", "user", "add", "other", "--kind", "agent").exit_code == 0
    issue(env, label="keep")
    issue(env, label="drop")
    issue(env, name="other", label="theirs")
    drop_id = next(
        line.split("  ")[0]
        for line in tl(env, "admin", "token", "ls").stdout.splitlines()
        if "  drop  " in line
    )
    assert tl(env, "admin", "token", "revoke", drop_id).exit_code == 0
    labels = [line.split("  ")[2] for line in tl(env, "admin", "token", "ls").stdout.splitlines()]
    assert labels == ["keep", "theirs"]
    everything = tl(env, "admin", "token", "ls", "--all").stdout.splitlines()
    assert [line.split("  ")[2] for line in everything] == ["keep", "drop", "theirs"]
    assert everything[1].endswith("  revoked")
    mine = tl(env, "admin", "token", "ls", "--user", "other").stdout.splitlines()
    assert [line.split("  ")[1] for line in mine] == ["other"]
    assert tl(env, "admin", "token", "ls", "--user", "ghost").exit_code == 1


def test_revoke_stops_the_token_at_once_and_records_who_and_why(env: dict[str, str]) -> None:
    token = issue(env)
    token_id = tl(env, "admin", "token", "ls").stdout.split("  ")[0]
    backend = open_backend(Path(env["TL_DB"]))
    assert sessions.principal_for_bearer(backend, token).actor == "agent:triage"
    result = tl(env, "admin", "token", "revoke", token_id, "--reason", "leaked")
    assert result.exit_code == 0 and result.stdout.strip() == f"revoked {token_id}"
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(backend, token)
    actor, payload = events(env, "AgentToken.Revoked")[-1]
    assert actor == "user:root" and "leaked" in payload and token not in payload


def test_revoking_twice_or_an_unknown_id_is_an_error(env: dict[str, str]) -> None:
    issue(env)
    token_id = tl(env, "admin", "token", "ls").stdout.split("  ")[0]
    assert tl(env, "admin", "token", "revoke", token_id).exit_code == 0
    again = tl(env, "admin", "token", "revoke", token_id)
    assert again.exit_code == 1 and "already revoked" in again.stderr
    for bad in ("nope", "a\x00b", "\ud800", "x" * 70_000):
        result = tl(env, "admin", "token", "revoke", bad)
        assert result.exit_code == 1 and result.stderr.startswith("error: "), repr(bad)


def test_the_tokens_of_a_disabled_agent_stop_working(env: dict[str, str]) -> None:
    token = issue(env)
    assert tl(env, "admin", "user", "disable", "triage").exit_code == 0
    with pytest.raises(InvalidCredentialsError):
        sessions.principal_for_bearer(open_backend(Path(env["TL_DB"])), token)


COMMANDS = [
    ["ls"],
    ["issue", "triage", "--label", "x"],
    ["revoke", "someid"],
]


@pytest.mark.parametrize("args", COMMANDS)
def test_every_command_needs_a_signed_in_admin(
    env: dict[str, str], tmp_path: Path, args: list[str]
) -> None:
    assert tl(env, "admin", "user", "add", "amy", "--password-stdin", stdin=GOOD).exit_code == 0
    amy = separate_session(env, tmp_path, "amy")
    sign_in(amy, "amy")
    user = tl(amy, "admin", "token", *args)
    assert user.exit_code == 1 and user.stdout == ""
    assert user.stderr == "error: forbidden: this command needs the admin role\n"
    nobody = tl(separate_session(env, tmp_path, "nobody"), "admin", "token", *args)
    assert nobody.exit_code == 1 and nobody.stdout == ""
    assert nobody.stderr == "error: not signed in: run `tl login <username>`\n"
    assert rows(env, "SELECT COUNT(*) FROM cur_agent_token")[0][0] == 0


def test_help_lists_the_three_commands(env: dict[str, str]) -> None:
    out = tl(env, "admin", "token", "--help").stdout
    for name in ("ls", "issue", "revoke"):
        assert f" {name} " in out
