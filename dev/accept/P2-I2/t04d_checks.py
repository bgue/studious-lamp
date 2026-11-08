"""The checks of T04d.py: the `tl awp iwp` and `tl constraint` CLI reads on the C2 seed.

Each verb runs through a throwaway Typer app with CliRunner. The constraint verbs read as a
signed-in account (``TL_SESSION_FILE`` names a temp file), so the viewer is that account's.
A hidden IWP is made with the test-only class source of the T04a checks, and a hidden
correspondence item with the awp world helper, as the T04a2 checks do.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from functools import partial
from typing import Any
from unittest import mock

import c2_checks as c2
import t04a_checks as a
import typer
from awp_world import PASSWORD, hidden_record
from sqlalchemy import event
from sqlalchemy.engine import Engine
from tl_adapters.db import DbTarget
from tl_cli import awp_iwp_read, constraint_read
from tl_cli import session as signed
from tl_core.auth import sessions
from tl_core.constraints.commands import RECORD_TYPE
from typer.testing import CliRunner, Result

ok = c2.ok
PROJECT = "P123"
HASH = re.compile(r"[0-9a-f]{64}")
IWP_KEYS = "SELECT r.key FROM cur_awp_iwp i JOIN cur_core_record r ON r.id = i.id ORDER BY r.key"
CON_KEYS = "SELECT r.key FROM cur_core_record r WHERE r.type = :t ORDER BY r.key"
SEEN: list[str] = []  # every stdout and stderr the checks read, for the Traceback check


def app() -> typer.Typer:
    root = typer.Typer()
    iwp = typer.Typer()
    con = typer.Typer()
    awp_iwp_read.register(iwp)
    constraint_read.register(con)
    root.add_typer(iwp, name="iwp")
    root.add_typer(con, name="constraint")
    return root


def cli(root: typer.Typer, db: DbTarget, *args: str) -> Result:
    result = CliRunner().invoke(root, list(args), obj=db)
    SEEN.append(result.stdout + result.stderr)
    return result


def traced(call: Callable[[], Result]) -> tuple[Result, list[str]]:
    """The result of ``call`` and the SQL statements it ran, through a listener on every engine."""
    seen: list[str] = []

    def hook(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", hook)
    try:
        got = call()
    finally:
        event.remove(Engine, "before_cursor_execute", hook)
    return got, seen


def sign_in(db: DbTarget, name: str) -> None:
    """Make ``name`` the session of this ledger (one entry per ledger: this replaces the last)."""
    principal, token = sessions.sign_in(signed.open_backend(db), username=name, password=PASSWORD)
    signed.save(
        signed.StoredSession(
            target=signed.db_target(db),
            username=name,
            actor=principal.actor,
            expires_at=signed.expires_at_from(sessions.SESSION_TTL),
            token=token,
        )
    )


def parse(result: Result) -> tuple[int, list[list[str]]]:
    """The total on the first line and the rows (fields split on two spaces) after it."""
    lines = result.stdout.splitlines()
    return int(lines[0].split(": ")[1]), [line.split("  ") for line in lines[1:]]


def iwp_checks(root: typer.Typer, w: c2.C2, db: DbTarget, hidden: str) -> None:
    expect = [r["key"] for r in w.rows(IWP_KEYS) if r["key"] != hidden]
    listed = cli(root, db, "iwp", "ls", "--project", PROJECT)
    numbers = [line.split("  ")[0] for line in listed.stdout.splitlines()[1:]]
    ok(
        "iwp ls: count line, number order, the hidden IWP absent",
        listed.exit_code == 0
        and listed.stdout.splitlines()[0] == f"iwps: {len(expect)}"
        and numbers == expect,
    )
    visible = expect[0]
    shown = cli(root, db, "iwp", "show", visible, "--project", PROJECT)
    out = shown.stdout.splitlines()
    pins_at = next(i for i, line in enumerate(out) if line.startswith("pins "))
    scope_n = int(out[9].split()[1])
    type_counts = [int(line.split("  ")[2]) for line in out[10:pins_at]]
    ok(
        "iwp show: fields in order, scope lines add up to the scope count",
        shown.exit_code == 0
        and out[0] == f"iwp {visible}"
        and out[9].startswith("scope ")
        and sum(type_counts) == scope_n,
    )
    ok(
        "iwp show: no record hash in the output",
        HASH.search(shown.stdout) is None and "record_hash" not in shown.stdout,
    )
    scoped = cli(root, db, "iwp", "scope", visible, "--project", PROJECT)
    sl = scoped.stdout.splitlines()
    ok(
        "iwp scope: count line matches the rows and the show scope total",
        scoped.exit_code == 0 and sl[0] == f"scope: {len(sl) - 1}" and len(sl) - 1 == scope_n,
    )
    unknown = cli(root, db, "iwp", "show", "P123-IWP-PIP-9999", "--project", PROJECT)
    gone = cli(root, db, "iwp", "show", hidden, "--project", PROJECT)
    gone_scope = cli(root, db, "iwp", "scope", hidden, "--project", PROJECT)
    ok(
        "unknown and hidden IWP print the same error, exit 1",
        unknown.exit_code == gone.exit_code == gone_scope.exit_code == 1
        and unknown.stderr == "error: no IWP P123-IWP-PIP-9999\n"
        and gone.stderr == f"error: no IWP {hidden}\n"
        and gone_scope.stderr == f"error: no IWP {hidden}\n"
        and not gone.stdout
        and not gone_scope.stdout,
    )


def constraint_checks(
    root: typer.Typer, w: c2.C2, db: DbTarget, hidden_con: str, secret_key: str, made_key: str
) -> None:
    everything = sorted(r["key"] for r in w.rows(CON_KEYS, t=RECORD_TYPE))
    expect = [k for k in everything if k not in (hidden_con, made_key)]
    sign_in(db, "user")
    base = cli(root, db, "constraint", "ls", "--project", PROJECT, "--actor", "user:user")
    total, rows = parse(base)
    keys = [r[0] for r in rows]
    by_key = {r[0]: r for r in rows}
    ok(
        "constraint ls: total equals the lines; hidden subject and its constraint absent",
        base.exit_code == 0 and total == len(rows) == len(expect) and keys == expect,
    )

    def listed(*more: str) -> list[str]:
        result = cli(
            root, db, "constraint", "ls", "--project", PROJECT, "--actor", "user:user", *more
        )
        return (
            [r[0] for r in parse(result)[1]] if result.exit_code == 0 else ["exit", result.stderr]
        )

    ok(
        "constraint ls filter --owner",
        listed("--owner", "user:uma") == [k for k in keys if by_key[k][5] == "user:uma"]
        and len(listed("--owner", "user:uma")) == 1,
    )
    ok(
        "constraint ls filter --state Open",
        listed("--state", "Open") == [k for k in keys if by_key[k][1] == "Open"],
    )
    ok(
        "constraint ls filter --blocking and --advisory",
        listed("--blocking") == [k for k in keys if by_key[k][2] == "blocking"]
        and listed("--advisory") == [k for k in keys if by_key[k][2] == "advisory"],
    )
    for by in ("owner", "category", "age"):
        grouped = cli(
            root,
            db,
            "constraint",
            "groups",
            "--project",
            PROJECT,
            "--by",
            by,
            "--actor",
            "user:user",
        )
        gl = grouped.stdout.splitlines()
        counts = sum(int(line.split("  ")[1]) for line in gl[1:])
        ok(
            f"groups --by {by}: count line, every filtered row in one group",
            grouped.exit_code == 0 and gl[0] == f"groups: {len(gl) - 1}" and counts == total,
        )
    bad = cli(root, db, "constraint", "groups", "--project", PROJECT, "--by", "x")
    ok("groups --by x is a usage error, exit 2", bad.exit_code == 2)
    shown = cli(
        root, db, "constraint", "show", keys[0], "--project", PROJECT, "--actor", "user:user"
    )
    ok(
        "constraint show: header and description of a visible constraint",
        shown.exit_code == 0
        and shown.stdout.startswith(f"constraint {keys[0]}\n")
        and f"description {by_key[keys[0]][8]}" in shown.stdout,
    )
    gone = cli(
        root, db, "constraint", "show", made_key, "--project", PROJECT, "--actor", "user:user"
    )
    missing = cli(
        root,
        db,
        "constraint",
        "show",
        "P123-CON-9999",
        "--project",
        PROJECT,
        "--actor",
        "user:user",
    )
    ok(
        "hidden and unknown constraint print the errors of a missing one",
        gone.exit_code == 1
        and gone.stderr == f"error: no constraint {made_key}\n"
        and missing.stderr == "error: no constraint P123-CON-9999\n",
    )
    sub = cli(
        root,
        db,
        "constraint",
        "ls",
        "--project",
        PROJECT,
        "--subject",
        secret_key,
        "--actor",
        "user:user",
    )
    ok(
        "constraint ls --subject of a hidden record: error no record",
        sub.exit_code == 1 and sub.stderr == f"error: no record {secret_key}\n",
    )
    sign_in(db, "controller")
    above = cli(root, db, "constraint", "ls", "--project", PROJECT, "--actor", "user:controller")
    ok("controller ls: the restricted constraints too", parse(above)[0] == len(everything))
    cleared = cli(
        root,
        db,
        "constraint",
        "show",
        hidden_con,
        "--project",
        PROJECT,
        "--actor",
        "user:controller",
    )
    ok(
        "controller show: cleared line for the cleared constraint",
        cleared.exit_code == 0
        and re.search(r"^cleared 2026-10-20 by ", cleared.stdout, re.M) is not None,
    )


def refusal_checks(root: typer.Typer, w: c2.C2, db: DbTarget, key: str) -> None:
    """An actor that holds no access word is refused before any read. ``svc:reader`` names no
    account, so it holds nothing; the dev environment lets the command take any actor on a file."""
    with mock.patch.dict(os.environ, {"TL_ENV": "dev"}):
        _refusals(root, db, key)


def _refusals(root: typer.Typer, db: DbTarget, key: str) -> None:
    calls = {
        "ls": ["constraint", "ls", "--project", PROJECT, "--actor", "svc:reader"],
        "show": ["constraint", "show", key, "--project", PROJECT, "--actor", "svc:reader"],
        "groups": [
            "constraint",
            "groups",
            "--project",
            PROJECT,
            "--by",
            "owner",
            "--actor",
            "svc:reader",
        ],
    }
    for name, args in calls.items():
        got, seen = traced(partial(cli, root, db, *args))
        touched = [s for s in seen if "cur_core_constraint" in s or "cur_core_record" in s]
        ok(
            f"an actor without core.constraint.view refused by {name} before any read",
            got.exit_code == 1 and got.stderr.startswith("error: forbidden: ") and not touched,
        )


def checks(w: c2.C2, db: DbTarget) -> None:
    root = app()
    ids = [r["id"] for r in w.rows("SELECT id FROM cur_awp_iwp ORDER BY id")]
    hidden_iwp = ids[2]  # the IWP the seed clears a constraint on
    hidden = w.column("cur_core_record", "key", hidden_iwp)
    hidden_con = w.rows(
        "SELECT r.key FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.subject_id = :s",
        s=hidden_iwp,
    )[0]["key"]
    secret = hidden_record(w)
    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    secret_key = w.column("cur_core_record", "key", secret)
    a.classed(w, {hidden_iwp})
    iwp_checks(root, w, db, hidden)
    constraint_checks(root, w, db, hidden_con, secret_key, made.key)
    refusal_checks(root, w, db, made.key)
    ok("no Traceback in any output", all("Traceback" not in text for text in SEEN))
