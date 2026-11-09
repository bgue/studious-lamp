"""The CLI holds a signed-in caller to the admin word the API puts on a command (P2-FIX-ADMIN).

The API gates a command whose access is ``admin`` as ``admin.command.<Name>`` and, for ``company``
access at company scope, the same. A signed-in non-admin must be refused by the CLI too, before
anything is written. No session is allowed only on a dev, test or ci ledger *file* (the file's
owner can write it anyway, ADR-0009 sec. 7); the API has no such case, it always needs a principal.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import P, new_env, ok, refused, run, sql, write_json
from tl_adapters.db import DbTarget
from tl_api.commands import COMMANDS, effective_access

AUTO_SIGN_IN = False

PW = "correct horse battery"
ARGS: dict[str, tuple[str, ...]] = {
    "rule create": ("rule", "create", "--file", "{rule}", "--project", P),
    "rule enable": ("rule", "enable", "r1", "--project", P),
    "rule disable": ("rule", "disable", "r1", "--project", P),
    "rule mode": ("rule", "mode", "r1", "act", "--reason", "x", "--project", P),
    "action define": ("action", "define", "--file", "{rule}", "--project", P),
    "action retire": ("action", "retire", "a1", "--reason", "x"),
    "enricher register": ("enricher", "register", "e1", "--file", "{rule}", "--project", P),
    "enricher enable": ("enricher", "enable", "e1", "--project", P),
    "enricher disable": ("enricher", "disable", "e1", "--project", P),
    "endpoint create": (
        "endpoint", "create", "erp/o", "--mapping-file", "{rule}", "--allow", "PostToFeed",
        "--project", P,
    ),
    "endpoint enable": ("endpoint", "enable", "erp/o", "--project", P),
    "endpoint disable": ("endpoint", "disable", "erp/o", "--project", P),
    "endpoint mode": ("endpoint", "mode", "erp/o", "live", "--reason", "x", "--project", P),
    "integration app add": ("integration", "app", "add", "erp", "--label", "ERP", "--project", P),
    "integration app enable": ("integration", "app", "enable", "erp", "--project", P),
    "integration app disable": ("integration", "app", "disable", "erp", "--project", P),
    "delivery retry": ("delivery", "retry", "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", "--project", P),
}  # fmt: skip


def events(env: dict[str, str]) -> int:
    return int(sql(env, "SELECT COUNT(*) AS n FROM events")[0]["n"])


def seed(env: dict[str, str]) -> None:
    from tl_adapters.db import open_uow
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    with open_uow(env["TL_DB"]) as uow:
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=roles,
                password=prepare_password(PW), by="svc:test",
            )  # fmt: skip


@pytest.mark.parametrize("name", sorted(ARGS))
def test_a_signed_in_non_admin_is_refused_and_nothing_is_written(
    new_db: Callable[[], DbTarget], tmp_path: Path, name: str
) -> None:
    env = new_env(new_db, tmp_path)
    env["TL_SESSION_FILE"] = str(tmp_path / "session.json")
    seed(env)
    env = {**env, "TL_ENV": "prod"}  # not a dev setup: nobody acts on a claim
    body = write_json(tmp_path, "body.json", {"key": "r1"})
    args = tuple(a.replace("{rule}", body) for a in ARGS[name])
    ok(run(env, "login", "bob", "--password-stdin", input=PW + "\n"))
    before = events(env)
    refused(run(env, *args, "--actor", "user:bob"), "forbidden")
    assert events(env) == before


def test_a_signed_in_admin_passes_the_gate(
    new_db: Callable[[], DbTarget], tmp_path: Path
) -> None:
    env = new_env(new_db, tmp_path)
    env["TL_SESSION_FILE"] = str(tmp_path / "session.json")
    seed(env)
    env = {**env, "TL_ENV": "prod"}
    ok(run(env, "login", "boss", "--password-stdin", input=PW + "\n"))
    done = run(
        env, "integration", "app", "add", "erp", "--label", "ERP", "--project", P,
        "--actor", "user:boss",
    )  # fmt: skip
    ok(done)
    assert "app erp" in done.stdout


# --- the pin -----------------------------------------------------------------------------------

CLI_DIR = Path(__file__).resolve().parents[1] / "src" / "tl_cli"
GATES = {"admin_gate", "require_admin"}


def admin_handlers() -> set[str]:
    """Handler names of every command the API gates as admin, or as company access (which it
    raises to admin at company scope)."""
    return {
        spec.handler.__name__
        for spec in COMMANDS
        if effective_access(spec) in ("admin", "company")
    }


def test_the_pin_sees_the_admin_handlers() -> None:
    names = admin_handlers()
    assert {"handle_create_rule", "handle_register_app", "handle_add_code_value"} <= names
    assert len(names) >= 35


def test_every_cli_use_of_an_admin_handler_has_an_admin_gate_in_its_function() -> None:
    """A function that names an admin-gated handler (call or reference) calls ``admin_gate`` or
    ``require_admin`` (the publish path through ``_require_publisher``, which does, is named)."""
    names = admin_handlers()
    seen = 0
    ungated: list[tuple[str, str]] = []
    for path in sorted(CLI_DIR.rglob("*.py")):
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id in names}
            if not used:
                continue
            seen += 1
            called = {
                n.func.id
                for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            if not (called & (GATES | {"_require_publisher"})):
                ungated.append((path.name, fn.name))
    assert seen >= 25
    assert not ungated, ungated
