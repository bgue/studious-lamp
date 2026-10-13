"""`tl admin user ...` against a temporary SQLite ledger (P1-I0-T07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auth_support import (
    GOOD,
    OTHER,
    bootstrap,
    failed_sign_ins,
    new_ledger,
    rows,
    separate_session,
    sign_in,
    signed_in_actor,
)
from auth_support import run as tl
from tl_core.auth.errors import AccountDisabledError, InvalidCredentialsError


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A ledger with the admin `root`, signed in."""
    values = new_ledger(tmp_path)
    assert bootstrap(values).exit_code == 0
    sign_in(values)
    return values


def add(env: dict[str, str], name: str, *extra: str, password: str = GOOD) -> int:
    args = ["admin", "user", "add", name, "--password-stdin", *extra]
    return tl(env, *args, stdin=password).exit_code


def events(env: dict[str, str], kind: str) -> list[tuple[str, str]]:
    found = rows(env, "SELECT actor, payload FROM events WHERE event_type = ? ORDER BY seq", kind)
    return [(str(a), str(p)) for a, p in found]


def test_ls_lists_every_account_in_creation_order(env: dict[str, str]) -> None:
    assert add(env, "amy", "--display-name", "Amy") == 0
    assert tl(env, "admin", "user", "add", "bot", "--kind", "agent").exit_code == 0
    result = tl(env, "admin", "user", "ls")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "root  person  admin  active",
        "amy  person  user  active",
        "bot  agent  user  active",
    ]


def test_ls_json_is_a_list_of_accounts_without_any_secret(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    result = tl(env, "admin", "user", "ls", "--json")
    listed = json.loads(result.stdout)
    assert [row["username"] for row in listed] == ["root", "amy"]
    assert {"account_id", "roles", "status", "locked_until"} <= set(listed[0])
    assert "scrypt" not in result.stdout and GOOD not in result.stdout


def test_show_prints_one_field_per_line_and_a_lock(env: dict[str, str], tmp_path: Path) -> None:
    assert add(env, "amy", "--display-name", "Amy A") == 0
    failed_sign_ins(env, "amy", 5)
    shown = tl(env, "admin", "user", "show", "amy")
    assert shown.exit_code == 0
    fields = dict(line.split(" ", 1) for line in shown.stdout.splitlines())
    assert fields["username"] == "amy" and fields["display_name"] == "Amy A"
    assert fields["kind"] == "person" and fields["roles"] == "user" and fields["status"] == "active"
    assert fields["locked_until"].startswith("20") and len(fields["id"]) == 26
    listed = tl(env, "admin", "user", "ls").stdout.splitlines()
    assert listed[1].startswith("amy  person  user  active  locked until 20")


def test_show_and_every_change_report_an_unknown_name(env: dict[str, str]) -> None:
    for args in (
        ["show"],
        ["disable"],
        ["enable"],
        ["roles", "--role", "user"],
        ["reset-password"],
    ):
        result = tl(env, "admin", "user", args[0], "ghost", *args[1:], stdin=GOOD)
        assert result.exit_code == 1 and result.stdout == "", args
        assert result.stderr == "error: no account named 'ghost'\n", args


def test_add_creates_a_person_who_can_sign_in_and_never_prints_the_password(
    env: dict[str, str], tmp_path: Path
) -> None:
    result = tl(env, "admin", "user", "add", "amy", "--password-stdin", stdin=GOOD)
    assert result.exit_code == 0 and result.stdout.strip() == "created amy  person  user  active"
    assert GOOD not in result.output
    sign_in(separate_session(env, tmp_path, "amy"), "amy")
    created = events(env, "Account.Created")
    assert created[-1][0] == "user:root"  # the admin who did it
    assert GOOD not in created[-1][1] and "scrypt" not in created[-1][1]


def test_add_takes_a_hidden_prompt_twice_and_stops_when_they_differ(env: dict[str, str]) -> None:
    ok = tl(env, "admin", "user", "add", "amy", stdin=f"{GOOD}\n{GOOD}\n")
    assert ok.exit_code == 0
    differ = tl(env, "admin", "user", "add", "bob", stdin=f"{GOOD}\n{OTHER}\n")
    assert differ.exit_code == 1 and "the two passwords differ" in differ.stderr
    assert "bob" not in tl(env, "admin", "user", "ls").stdout


def test_add_with_roles_kinds_and_a_display_name(env: dict[str, str]) -> None:
    assert add(env, "boss", "--role", "admin", "--role", "user", "--display-name", "The Boss") == 0
    assert add(env, "sim-1", "--kind", "sim") == 0
    out = tl(env, "admin", "user", "ls").stdout.splitlines()
    assert "boss  person  admin,user  active" in out and "sim-1  sim  user  active" in out
    assert "The Boss" in tl(env, "admin", "user", "show", "boss").stdout


def test_add_an_agent_takes_no_password_and_points_at_the_token_command(
    env: dict[str, str],
) -> None:
    result = tl(env, "admin", "user", "add", "triage", "--kind", "agent", stdin="")
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "created triage  agent  user  active",
        "next: tl admin token issue triage --label <what it is for>",
    ]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--kind", "robot"], "kind must be"),
        (["--role", "owner"], "role"),
        (["--kind", "agent", "--role", "admin"], "agent"),
    ],
)
def test_add_refuses_what_the_service_refuses(
    env: dict[str, str], extra: list[str], message: str
) -> None:
    result = tl(env, "admin", "user", "add", "x1", "--password-stdin", *extra, stdin=GOOD)
    assert result.exit_code == 1 and message in result.stderr and result.stdout == ""
    assert "x1" not in tl(env, "admin", "user", "ls").stdout


def test_add_lists_the_broken_password_rules_and_creates_nothing(env: dict[str, str]) -> None:
    result = tl(env, "admin", "user", "add", "amy", "--password-stdin", stdin="short")
    assert result.exit_code == 1 and result.stderr.startswith("error: ")
    assert "  - " in result.stderr
    assert "amy" not in tl(env, "admin", "user", "ls").stdout


def test_add_refuses_a_name_that_is_taken_and_one_that_cannot_exist(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    taken = tl(env, "admin", "user", "add", "AMY", "--password-stdin", stdin=GOOD)
    assert taken.exit_code == 1 and "taken" in taken.stderr
    for bad in ("a b", "x" * 70, "a\x00b"):
        result = tl(env, "admin", "user", "add", bad, "--password-stdin", stdin=GOOD)
        assert result.exit_code == 1 and result.stderr.startswith("error: "), bad


def test_roles_changes_them_and_records_who_and_why(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    result = tl(env, "admin", "user", "roles", "amy", "--role", "admin", "--reason", "promoted")
    assert result.exit_code == 0 and result.stdout.strip() == "amy  person  admin  active"
    actor, payload = events(env, "Account.RolesSet")[-1]
    assert actor == "user:root" and "promoted" in payload


def test_document_controller_is_granted_and_taken_back_with_add_and_remove(
    env: dict[str, str],
) -> None:
    assert add(env, "amy") == 0
    granted = tl(env, "admin", "user", "roles", "amy", "--add", "document_controller",
                 "--reason", "takes over document control")  # fmt: skip
    assert granted.exit_code == 0, granted.stderr
    assert granted.stdout.strip() == "amy  person  document_controller,user  active"
    actor, payload = events(env, "Account.RolesSet")[-1]
    assert actor == "user:root" and "document_controller" in payload and "takes over" in payload
    back = tl(env, "admin", "user", "roles", "amy", "--remove", "document_controller")
    assert back.exit_code == 0 and back.stdout.strip() == "amy  person  user  active"
    # replace works with the new name too, and a controller may stand alone
    only = tl(env, "admin", "user", "roles", "amy", "--role", "document_controller")
    assert only.exit_code == 0 and only.stdout.strip() == "amy  person  document_controller  active"
    shown = tl(env, "admin", "user", "show", "amy")
    assert "roles document_controller" in shown.stdout


def test_roles_takes_replace_or_add_and_remove_and_never_both(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    both = tl(env, "admin", "user", "roles", "amy", "--role", "user", "--add", "admin")
    assert both.exit_code == 2
    nothing = tl(env, "admin", "user", "roles", "amy")
    assert nothing.exit_code == 2
    unknown = tl(env, "admin", "user", "roles", "amy", "--add", "controller")
    assert unknown.exit_code == 1 and "unknown role controller" in unknown.stderr
    assert "document_controller" in unknown.stderr
    emptied = tl(env, "admin", "user", "roles", "amy", "--remove", "user")
    assert emptied.exit_code == 1 and "at least one role" in emptied.stderr
    same = tl(env, "admin", "user", "roles", "amy", "--add", "user")
    assert same.exit_code == 1 and "already" in same.stderr
    assert tl(env, "admin", "user", "ls").stdout.count("amy  person  user  active") == 1


def test_an_agent_account_is_refused_the_role_by_the_command(env: dict[str, str]) -> None:
    made = tl(env, "admin", "user", "add", "triage", "--kind", "agent")
    assert made.exit_code == 0, made.stderr
    refused = tl(env, "admin", "user", "roles", "triage", "--add", "document_controller")
    assert refused.exit_code == 1
    assert "agent account cannot hold the document_controller role" in refused.stderr
    again = tl(
        env, "admin", "user", "add", "bot2", "--kind", "agent", "--role", "document_controller"
    )
    assert again.exit_code == 1 and "document_controller" in again.stderr
    assert "triage  agent  user  active" in tl(env, "admin", "user", "ls").stdout


def test_a_sim_account_may_be_a_document_controller(env: dict[str, str]) -> None:
    made = tl(env, "admin", "user", "add", "sim-dc", "--kind", "sim", "--role", "user",
              "--role", "document_controller", "--password-stdin", stdin=GOOD)  # fmt: skip
    assert made.exit_code == 0, made.stderr
    assert "sim-dc  sim  document_controller,user  active" in tl(env, "admin", "user", "ls").stdout


def test_the_last_admin_cannot_be_demoted_or_disabled_and_a_no_op_is_refused(
    env: dict[str, str],
) -> None:
    demote = tl(env, "admin", "user", "roles", "root", "--role", "user")
    assert demote.exit_code == 1 and "last active admin" in demote.stderr
    disable = tl(env, "admin", "user", "disable", "root")
    assert disable.exit_code == 1 and "last active admin" in disable.stderr
    same = tl(env, "admin", "user", "roles", "root", "--role", "admin")
    assert same.exit_code == 1 and "already" in same.stderr
    assert tl(env, "admin", "user", "roles", "root").exit_code == 2  # a change is required


def test_disable_ends_sessions_and_blocks_sign_in_until_enabled(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert add(env, "amy") == 0
    amy = separate_session(env, tmp_path, "amy")
    sign_in(amy, "amy")
    assert signed_in_actor(amy) == "user:amy"
    off = tl(env, "admin", "user", "disable", "amy", "--reason", "left")
    assert off.exit_code == 0 and off.stdout.strip() == "amy  person  user  disabled"
    assert signed_in_actor(amy) is None
    with pytest.raises(AccountDisabledError):
        sign_in(amy, "amy")
    on = tl(env, "admin", "user", "enable", "amy")
    assert on.exit_code == 0 and on.stdout.strip() == "amy  person  user  active"
    sign_in(amy, "amy")
    assert signed_in_actor(amy) == "user:amy"
    assert events(env, "Account.Disabled")[-1][0] == "user:root"


def test_disabling_twice_is_an_error(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    assert tl(env, "admin", "user", "disable", "amy").exit_code == 0
    again = tl(env, "admin", "user", "disable", "amy")
    assert again.exit_code == 1 and again.stderr.startswith("error: ")


def test_reset_password_ends_sessions_clears_a_lock_and_sets_the_new_password(
    env: dict[str, str], tmp_path: Path
) -> None:
    assert add(env, "amy") == 0
    amy = separate_session(env, tmp_path, "amy")
    sign_in(amy, "amy")
    failed_sign_ins(env, "amy", 5)
    assert (
        "locked until"
        in tl(env, "admin", "user", "show", "amy").stdout + tl(env, "admin", "user", "ls").stdout
    )
    result = tl(env, "admin", "user", "reset-password", "amy", "--password-stdin", stdin=OTHER)
    assert result.exit_code == 0 and OTHER not in result.output
    assert result.stdout.strip() == (
        "password reset for amy; their sessions ended and any lock is cleared"
    )
    assert signed_in_actor(amy) is None  # the old session ended
    with pytest.raises(InvalidCredentialsError):
        sign_in(amy, "amy", GOOD)  # the old password is gone
    sign_in(amy, "amy", OTHER)  # and the lock is cleared
    assert signed_in_actor(amy) == "user:amy"
    forced = events(env, "Account.PasswordChanged")[-1]
    assert forced[0] == "user:root" and '"forced":true' in forced[1].replace(" ", "")


def test_reset_password_prompts_twice_and_refuses_a_weak_one(env: dict[str, str]) -> None:
    assert add(env, "amy") == 0
    assert (
        tl(env, "admin", "user", "reset-password", "amy", stdin=f"{OTHER}\n{OTHER}\n").exit_code
        == 0
    )
    differ = tl(env, "admin", "user", "reset-password", "amy", stdin=f"{GOOD}\nnope\n")
    assert differ.exit_code == 1 and "the two passwords differ" in differ.stderr
    weak = tl(env, "admin", "user", "reset-password", "amy", "--password-stdin", stdin="short")
    assert weak.exit_code == 1 and "  - " in weak.stderr


def test_reset_password_for_an_agent_is_refused(env: dict[str, str]) -> None:
    assert tl(env, "admin", "user", "add", "bot", "--kind", "agent").exit_code == 0
    result = tl(env, "admin", "user", "reset-password", "bot", "--password-stdin", stdin=GOOD)
    assert result.exit_code == 1 and "agent" in result.stderr


COMMANDS = [
    ["ls"],
    ["show", "root"],
    ["add", "zed", "--password-stdin"],
    ["roles", "root", "--role", "admin"],
    ["disable", "root"],
    ["enable", "root"],
    ["reset-password", "root", "--password-stdin"],
]


@pytest.mark.parametrize("args", COMMANDS)
def test_every_command_needs_a_signed_in_admin(
    env: dict[str, str], tmp_path: Path, args: list[str]
) -> None:
    assert add(env, "amy") == 0
    amy = separate_session(env, tmp_path, "amy")
    sign_in(amy, "amy")
    user = tl(amy, "admin", "user", *args, stdin=GOOD)
    assert user.exit_code == 1 and user.stdout == ""
    assert user.stderr == "error: forbidden: this command needs the admin role\n"
    nobody = tl(separate_session(env, tmp_path, "nobody"), "admin", "user", *args, stdin=GOOD)
    assert nobody.exit_code == 1 and nobody.stdout == ""
    assert nobody.stderr == "error: not signed in: run `tl login <username>`\n"
    assert "zed" not in tl(env, "admin", "user", "ls").stdout


def test_dev_mode_does_not_stand_in_for_an_admin_sign_in(
    env: dict[str, str], tmp_path: Path
) -> None:
    nobody = separate_session(env, tmp_path, "nobody")  # TL_ENV=dev: user:dev is the default actor
    result = tl(nobody, "admin", "user", "ls")  # ...but it is not an admin
    assert result.exit_code == 1 and result.stderr.startswith("error: not signed in")


def test_a_password_is_never_an_option(env: dict[str, str]) -> None:
    for args in (["add", "x1", "--password", GOOD], ["reset-password", "root", "--password", GOOD]):
        result = tl(env, "admin", "user", *args)
        assert result.exit_code == 2 and GOOD not in result.output


def test_help_lists_the_seven_commands(env: dict[str, str]) -> None:
    out = tl(env, "admin", "user", "--help").stdout
    for name in ("ls", "show", "add", "roles", "disable", "enable", "reset-password"):
        assert f" {name} " in out


def test_add_and_remove_start_from_the_roles_the_write_sees_not_from_an_earlier_read(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another admin gave amy the controller role between the lookup and the change."""
    from tl_cli import admin_user
    from tl_cli.admin import find_account as real

    assert add(env, "amy") == 0
    assert tl(env, "admin", "user", "roles", "amy", "--add", "document_controller").exit_code == 0

    def stale(backend: object, username: str):  # type: ignore[no-untyped-def]
        found = real(backend, username)  # type: ignore[arg-type]
        return found.model_copy(update={"roles": ["user"]})  # the list as it was before

    monkeypatch.setattr(admin_user, "find_account", stale)
    result = tl(env, "admin", "user", "roles", "amy", "--add", "admin")
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "amy  person  admin,document_controller,user  active"
    gone = tl(env, "admin", "user", "roles", "amy", "--remove", "user")
    assert gone.stdout.strip() == "amy  person  admin,document_controller  active"
