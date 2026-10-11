"""The CLI session: its file, the default `--actor`, `tl init --dev`, and the recovery commands."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import typer
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import sessions
from tl_core.auth.errors import AccountLockedError, InvalidCredentialsError
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
GOOD = "correct horse battery"


def iso(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def stored(target: str, token: str = "tls_secret", **kw: str) -> session.StoredSession:
    values = {"username": "root", "actor": "user:root", "expires_at": iso(timedelta(hours=1))}
    return session.StoredSession(target=target, token=token, **(values | kw))


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    values = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "dev"}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str, stdin: str | None = None) -> RunResult:
    return runner.invoke(app, list(args), env=env, input=stdin)


def bootstrap(env: dict[str, str], name: str = "root", password: str = GOOD) -> RunResult:
    return run(env, "admin", "bootstrap", "--username", name, "--password-stdin", stdin=password)


def last_actor(env: dict[str, str]) -> str:
    with sqlite3.connect(env["TL_DB"]) as conn:
        row = conn.execute(
            "SELECT actor FROM events WHERE event_type NOT LIKE 'Account.%' ORDER BY seq DESC"
        ).fetchone()
    return str(row[0])


def create_record(env: dict[str, str], *extra: str) -> RunResult:
    return run(env, "record", "create", "--project", "P123", "--title", "T", *extra)


def sign_in_to_file(env: dict[str, str], name: str = "root") -> str:
    """Sign in directly on the ledger and store the session as `tl login` does."""
    from tl_cli.session import open_backend

    principal, token = sessions.sign_in(
        open_backend(Path(env["TL_DB"])), username=name, password=GOOD
    )
    session.save(
        stored(
            session.db_target(Path(env["TL_DB"])),
            token,
            username=name,
            actor=principal.actor,
        )
    )
    return token


# --- the session file ------------------------------------------------------------------------


def test_a_session_round_trips_and_the_file_is_private(tmp_path: Path) -> None:
    session.save(stored("db:/a", "tls_one"))
    session.save(stored("api:http://x", "tls_two", username="amy", actor="user:amy"))
    path = session.session_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    first, second = session.load("db:/a"), session.load("api:http://x")
    assert first is not None and first.token == "tls_one" and first.actor == "user:root"
    assert second is not None and second.token == "tls_two" and second.username == "amy"
    assert session.load("db:/elsewhere") is None
    assert not list(path.parent.glob("*.tmp"))


def test_the_token_never_shows_in_a_repr_or_a_listing() -> None:
    item = stored("db:/a", "tls_very_secret")
    assert "tls_very_secret" not in repr(item) and "tls_very_secret" not in str(item)


def test_an_expired_session_is_not_used_and_forget_removes_the_entry_and_then_the_file() -> None:
    session.save(stored("db:/old", expires_at=iso(timedelta(seconds=-5))))
    session.save(stored("db:/new"))
    assert session.load("db:/old") is None and session.load("db:/new") is not None
    assert session.forget("db:/old") is not None and session.forget("db:/old") is None
    assert session.forget("db:/new") is not None
    assert not session.session_file().exists()


@pytest.mark.skipif(os.name != "posix", reason="file modes")
def test_a_session_file_open_to_other_users_is_refused_with_the_fix() -> None:
    session.save(stored("db:/a"))
    session.session_file().chmod(0o644)
    with pytest.raises(session.SessionFileError, match="chmod 600"):
        session.load("db:/a")


def test_a_damaged_session_file_is_refused_not_a_crash() -> None:
    path = session.session_file()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(session.SessionFileError, match="damaged"):
        session.load("db:/a")
    path.write_text(json.dumps({"version": 9, "sessions": {}}), encoding="utf-8")
    with pytest.raises(session.SessionFileError, match="damaged"):
        session.load("db:/a")


def test_the_file_comes_from_the_environment_or_the_config_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TL_SESSION_FILE")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert session.session_file() == tmp_path / "cfg" / "throughline" / "session.json"
    monkeypatch.setenv("TL_SESSION_FILE", str(tmp_path / "mine.json"))
    assert session.session_file() == tmp_path / "mine.json"


# --- the default --actor ---------------------------------------------------------------------


def test_in_dev_without_a_session_the_default_actor_is_user_dev(env: dict[str, str]) -> None:
    assert create_record(env).exit_code == 0
    assert last_actor(env) == "user:dev"


def test_outside_dev_the_default_actor_needs_a_sign_in_but_an_explicit_actor_is_honoured(
    env: dict[str, str],
) -> None:
    prod = env | {"TL_ENV": "prod"}
    refused = create_record(prod)
    assert refused.exit_code == 1 and refused.stdout == ""
    assert refused.stderr.startswith("error: not signed in: run `tl login")
    assert create_record(prod, "--actor", "user:ops").exit_code == 0
    assert last_actor(env) == "user:ops"


def test_a_signed_in_session_is_the_default_actor_everywhere(env: dict[str, str]) -> None:
    assert bootstrap(env).exit_code == 0
    sign_in_to_file(env)
    for mode in ("dev", "prod"):
        assert create_record(env | {"TL_ENV": mode}).exit_code == 0
        assert last_actor(env) == "user:root"
    assert create_record(env, "--actor", "user:other").exit_code == 0
    assert last_actor(env) == "user:other"  # explicit still wins (the embedded trust boundary)


def test_a_session_for_another_ledger_is_not_used(env: dict[str, str], tmp_path: Path) -> None:
    assert bootstrap(env).exit_code == 0
    sign_in_to_file(env)
    other = {"TL_DB": str(tmp_path / "other.db"), "TL_ENV": "prod"}
    assert runner.invoke(app, ["init"], env=other).exit_code == 0
    assert create_record(other).exit_code == 1


def test_an_ended_or_disabled_session_falls_back_to_the_rule_for_no_session(
    env: dict[str, str],
) -> None:
    assert bootstrap(env).exit_code == 0
    token = sign_in_to_file(env)
    from tl_cli.session import open_backend

    sessions.sign_out(open_backend(Path(env["TL_DB"])), token=token)
    assert create_record(env).exit_code == 0 and last_actor(env) == "user:dev"
    assert create_record(env | {"TL_ENV": "prod"}).exit_code == 1


def test_a_damaged_session_file_warns_and_counts_as_no_session(env: dict[str, str]) -> None:
    path = session.session_file()
    path.parent.mkdir(parents=True)
    path.write_text("nope", encoding="utf-8")
    path.chmod(0o600)
    result = create_record(env)
    assert result.exit_code == 0 and "warning: " in result.stderr and "damaged" in result.stderr
    assert last_actor(env) == "user:dev"


def test_the_help_does_not_claim_user_dev_is_the_default(env: dict[str, str]) -> None:
    result = run(env, "record", "create", "--help")
    assert "the signed-in user" in result.stdout and "user:dev" not in result.stdout


def test_require_admin_needs_a_session_with_the_admin_role(env: dict[str, str]) -> None:
    db = Path(env["TL_DB"])
    with pytest.raises(typer.Exit):
        session.require_session(db)
    assert bootstrap(env).exit_code == 0
    sign_in_to_file(env)
    assert session.require_admin(db).actor == "user:root"


# --- tl init --dev ---------------------------------------------------------------------------


def test_init_dev_creates_the_demo_account_and_warns(tmp_path: Path) -> None:
    env = {"TL_DB": str(tmp_path / "d.db"), "TL_ENV": "dev"}
    result = run(env, "init", "--dev")
    assert result.exit_code == 0 and "initialised" in result.stdout
    assert "demo/demo" in result.stderr and "tl admin user disable demo" in result.stderr
    from tl_cli.session import open_backend

    principal, _ = sessions.sign_in(
        open_backend(Path(env["TL_DB"])), username="demo", password="demo"
    )
    assert principal.is_admin and principal.actor == "user:demo"
    assert run(env, "init", "--dev").exit_code == 0  # safe to repeat


@pytest.mark.parametrize("name", ["prod", "", "staging"])
def test_init_dev_refuses_outside_dev_demo_and_test(tmp_path: Path, name: str) -> None:
    env = {"TL_DB": str(tmp_path / "d.db"), "TL_ENV": name}
    result = run(env, "init", "--dev")
    assert result.exit_code == 1 and result.stderr.startswith("error: --dev needs TL_ENV")
    assert not (tmp_path / "d.db").exists()
    assert run(env, "init").exit_code == 0  # a plain init needs no environment


def test_a_plain_init_creates_no_account(env: dict[str, str]) -> None:
    with sqlite3.connect(env["TL_DB"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cur_account").fetchone()[0] == 0


# --- tl admin bootstrap, unlock, audit -------------------------------------------------------


def test_bootstrap_creates_the_first_admin_and_never_takes_a_password_on_the_command_line(
    env: dict[str, str],
) -> None:
    result = bootstrap(env)
    assert result.exit_code == 0 and "admin root is ready" in result.stdout
    assert GOOD not in result.output
    rejected = run(env, "admin", "bootstrap", "--username", "x", "--password", GOOD)
    assert rejected.exit_code == 2 and GOOD not in rejected.output


def test_bootstrap_prompts_twice_without_echo_and_stops_on_a_mismatch(env: dict[str, str]) -> None:
    ok = run(env, "admin", "bootstrap", "--username", "root", stdin=f"{GOOD}\n{GOOD}\n")
    assert ok.exit_code == 0
    again = run(env, "admin", "bootstrap", "--username", "root", stdin=f"{GOOD}\nother-thing\n")
    assert again.exit_code == 1 and "the two passwords differ" in again.stderr


def test_bootstrap_lists_the_broken_password_rules(env: dict[str, str]) -> None:
    result = bootstrap(env, password="short")
    assert result.exit_code == 1 and result.stderr.startswith("error: ")
    assert "  - " in result.stderr and "short" not in result.stderr.replace("shorter", "")


def test_a_second_new_admin_is_refused_but_the_existing_one_can_be_reset(
    env: dict[str, str],
) -> None:
    assert bootstrap(env).exit_code == 0
    other = bootstrap(env, name="second")
    assert other.exit_code == 1 and "tl admin user add" in other.stderr
    reset = bootstrap(env, password="another long passphrase")
    assert reset.exit_code == 0 and "admin root is ready" in reset.stdout


def test_unlock_clears_a_locked_name_and_audit_shows_both(env: dict[str, str]) -> None:
    from tl_cli.session import open_backend

    assert bootstrap(env).exit_code == 0
    backend = open_backend(Path(env["TL_DB"]))
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            sessions.sign_in(backend, username="root", password="this is not the password")
    with pytest.raises(AccountLockedError):
        sessions.sign_in(backend, username="root", password=GOOD)
    result = run(env, "admin", "unlock", "root")
    assert result.exit_code == 0 and result.stdout.strip() == "unlocked root"
    sessions.sign_in(backend, username="root", password=GOOD)
    assert "no lock" in run(env, "admin", "unlock", "root").stdout
    text = run(env, "admin", "audit").stdout
    assert "unlocked" in text and "sign_in_failed" in text and "bootstrap" in text
    assert "x5" in text or "x4" in text  # repeated failures share a row with a count
    assert GOOD not in text


def test_audit_filters_limits_and_prints_json(env: dict[str, str]) -> None:
    assert bootstrap(env).exit_code == 0
    only = run(env, "admin", "audit", "--event", "bootstrap", "--json")
    rows = json.loads(only.stdout)
    assert [r["event"] for r in rows] == ["bootstrap"] and rows[0]["detail"] == "created"
    assert len(json.loads(run(env, "admin", "audit", "--limit", "1", "--json").stdout)) == 1
    bad_event = run(env, "admin", "audit", "--event", "nonsense")
    assert bad_event.exit_code == 1 and "unknown audit event" in bad_event.stderr
    bad_limit = run(env, "admin", "audit", "--limit", "0")
    assert bad_limit.exit_code == 1 and "between 1 and 1000" in bad_limit.stderr


def test_the_recovery_commands_need_a_ledger(tmp_path: Path) -> None:
    env = {"TL_DB": str(tmp_path / "missing.db"), "TL_ENV": "dev"}
    for args in (["admin", "audit"], ["admin", "unlock", "x"]):
        result = run(env, *args)
        assert result.exit_code == 1 and "no ledger" in result.stderr
    assert not (tmp_path / "missing.db").exists()
