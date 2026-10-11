"""`tl login`, `tl logout`, `tl whoami` against a temporary SQLite ledger (P1-I0-T06)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from auth_support import GOOD, WRONG, bootstrap, last_actor, live_sessions, login, new_ledger, rows
from auth_support import run as tl
from tl_cli import session


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    values = new_ledger(tmp_path)
    assert bootstrap(values).exit_code == 0
    return values


def record(env: dict[str, str], *extra: str) -> int:
    return tl(env, "record", "create", "--project", "P123", "--title", "T", *extra).exit_code


def test_login_prints_who_you_are_and_keeps_the_token_out_of_sight(env: dict[str, str]) -> None:
    result = login(env)
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "signed in as user:root (admin)" and result.stderr == ""
    stored = session.session_file().read_text(encoding="utf-8")
    token = stored.split('"token": "')[1].split('"')[0]
    assert token.startswith("tls_") and token not in result.output and GOOD not in result.output
    if os.name == "posix":
        assert stat.S_IMODE(session.session_file().stat().st_mode) == 0o600
    assert live_sessions(env) == 1


def test_login_asks_for_the_password_without_echo_when_it_is_not_on_stdin(
    env: dict[str, str],
) -> None:
    result = tl(env, "login", "root", stdin=f"{GOOD}\n")
    assert result.exit_code == 0, result.output
    assert GOOD not in result.stdout.replace("Password for root:", "")
    assert tl(env, "whoami").stdout.splitlines()[0] == "user:root"


def test_whoami_names_the_account_and_its_roles(env: dict[str, str]) -> None:
    assert login(env).exit_code == 0
    result = tl(env, "whoami")
    assert result.exit_code == 0 and result.stdout.splitlines() == ["user:root", "roles: admin"]


def test_a_wrong_password_and_an_unknown_name_fail_alike_and_store_nothing(
    env: dict[str, str],
) -> None:
    wrong = login(env, "root", WRONG)
    unknown = login(env, "nobody", WRONG)
    for result in (wrong, unknown):
        assert result.exit_code == 1 and result.stdout == ""
        assert result.stderr == "error: invalid username or password\n"
    assert not session.session_file().exists() and live_sessions(env) == 0


@pytest.mark.parametrize("name", ["a\x00b", "x" * 70_000, "\ud800"])
def test_a_name_that_cannot_exist_is_just_a_failed_sign_in(env: dict[str, str], name: str) -> None:
    result = login(env, name, WRONG)
    assert result.exit_code == 1 and result.stderr == "error: invalid username or password\n"
    assert login(env).exit_code == 0  # nothing broke


def test_five_wrong_passwords_lock_the_name_and_say_when(env: dict[str, str]) -> None:
    for _ in range(5):
        assert login(env, "root", WRONG).exit_code == 1
    locked = login(env, "root", GOOD)
    assert locked.exit_code == 1 and locked.stdout == ""
    assert locked.stderr.startswith("error: ") and "locked until 20" in locked.stderr
    assert tl(env, "admin", "unlock", "root").exit_code == 0
    assert login(env).exit_code == 0


def test_a_disabled_account_cannot_sign_in(env: dict[str, str]) -> None:
    from tl_cli.session import open_backend
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    backend = open_backend(Path(env["TL_DB"]))
    prepared = prepare_password(GOOD, username="amy")
    with backend() as uow:
        amy = accounts.create_account(
            uow, username="amy", display_name="Amy", kind="person", roles=["user"],
            password=prepared, by="svc:test",
        )  # fmt: skip
    with backend() as uow:
        accounts.disable(uow, account_id=amy.account_id, by="svc:test", reason=None)
    result = login(env, "amy")
    assert result.exit_code == 1 and "disabled" in result.stderr


def test_a_second_login_replaces_the_first_and_ends_its_session(env: dict[str, str]) -> None:
    assert login(env).exit_code == 0 and live_sessions(env) == 1
    assert login(env).exit_code == 0
    assert live_sessions(env) == 1  # the earlier session was ended, not left to expire
    assert tl(env, "whoami").exit_code == 0


def test_logout_ends_the_session_and_forgets_it(env: dict[str, str]) -> None:
    assert login(env).exit_code == 0
    result = tl(env, "logout")
    assert result.exit_code == 0 and result.stdout.strip() == "signed out root"
    assert live_sessions(env) == 0 and not session.session_file().exists()
    after = tl(env, "whoami")
    assert after.exit_code == 1 and after.stderr.startswith("error: not signed in: run `tl login")


def test_logout_when_not_signed_in_is_harmless(env: dict[str, str]) -> None:
    result = tl(env, "logout")
    assert result.exit_code == 0 and result.stdout.strip() == "not signed in"


def test_whoami_without_a_session_is_an_error(env: dict[str, str]) -> None:
    result = tl(env, "whoami")
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr == "error: not signed in: run `tl login <username>`\n"


def test_whoami_notices_a_session_the_ledger_has_ended(env: dict[str, str]) -> None:
    from tl_cli.session import open_backend
    from tl_core.auth import queries, sessions

    assert login(env).exit_code == 0
    backend = open_backend(Path(env["TL_DB"]))
    with backend(readonly=True) as uow:
        root = queries.find_account(uow.conn(), username="root")
    assert root is not None
    sessions.sign_out_all(backend, account_id=root.account_id)  # as a password change would
    assert tl(env, "whoami").exit_code == 1


def test_a_session_belongs_to_one_ledger(env: dict[str, str], tmp_path: Path) -> None:
    other = new_ledger(tmp_path, "other.db")
    assert bootstrap(other).exit_code == 0
    assert login(env).exit_code == 0
    assert tl(other, "whoami").exit_code == 1
    assert login(other).exit_code == 0 and tl(env, "whoami").exit_code == 0
    assert tl(other, "logout").exit_code == 0 and tl(env, "whoami").exit_code == 0


def test_after_login_every_command_acts_as_you_and_after_logout_it_must_be_named(
    env: dict[str, str],
) -> None:
    prod = env | {"TL_ENV": "prod"}
    assert record(prod) == 1  # nobody is signed in and prod has no default actor
    assert login(prod).exit_code == 0
    assert record(prod) == 0 and last_actor(env) == "user:root"
    assert tl(prod, "logout").exit_code == 0
    assert record(prod) == 1


def test_the_demo_account_signs_in_only_where_the_environment_allows_it(
    tmp_path: Path,
) -> None:
    env = new_ledger(tmp_path)
    assert tl(env, "init", "--dev").exit_code == 0
    assert login(env, "demo", "demo").stdout.strip() == "signed in as user:demo (admin)"
    prod = env | {"TL_ENV": "prod"}
    refused = login(prod, "demo", "demo")
    assert refused.exit_code == 1 and refused.stderr == "error: invalid username or password\n"


def test_a_session_file_open_to_others_stops_login_and_leaves_no_live_session(
    env: dict[str, str],
) -> None:
    if os.name != "posix":
        pytest.skip("file modes")
    assert login(env).exit_code == 0
    session.session_file().chmod(0o644)
    result = login(env)
    assert result.exit_code == 1 and "chmod 600" in result.stderr
    assert live_sessions(env) == 1  # the new session was ended again; the old one is untouched


def test_login_needs_a_ledger_and_a_password(tmp_path: Path, env: dict[str, str]) -> None:
    missing = {"TL_DB": str(tmp_path / "none.db"), "TL_ENV": "dev"}
    result = tl(missing, "login", "root", "--password-stdin", stdin=GOOD)
    assert result.exit_code == 1 and "no ledger" in result.stderr
    assert not (tmp_path / "none.db").exists()
    empty = tl(env, "login", "root", "--password-stdin", stdin="")
    assert empty.exit_code == 1 and "no password" in empty.stderr


def test_a_password_is_never_an_option(env: dict[str, str]) -> None:
    result = tl(env, "login", "root", "--password", GOOD)
    assert result.exit_code == 2 and GOOD not in result.output
    assert rows(env, "SELECT COUNT(*) FROM auth_session")[0][0] == 0
