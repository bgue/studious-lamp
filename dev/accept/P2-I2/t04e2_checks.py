"""The checks of T04e2.py: the four CLI write verbs on the C2 ledger (SQLite only).

The CLI runs through a throwaway Typer app with ``register`` and ``CliRunner``. The process
reader is the lowest clearance, as ``tl`` sets it for a person who is not signed in; the
session viewer is patched to the same, so the key lookups and the handler read alike.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest import mock

os.environ.setdefault("TL_ENV", "dev")  # a dev ledger file: any --actor, as the justfile sets it

import typer  # noqa: E402
from tl_cli import constraint_write as cw  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import c2_checks as c2  # noqa: E402
from c2_checks import ok  # noqa: E402

APP = typer.Typer()
cw.register(APP)
RUN = CliRunner()
PROJECT = ["--project", "P123"]
SEEN: list[str] = []  # every output, for the Traceback check
MISSING = "P123-NOPE-9999"


def run(w: Any, *args: str) -> Any:
    with mock.patch.object(cw, "session_viewer", return_value=cf.LOWEST), cf.use_viewer(cf.LOWEST):
        result = RUN.invoke(APP, [*args, *PROJECT], obj=w.db)
    SEEN.append(result.output)
    return result


def key_of(w: Any, record_id: str) -> str:
    return str(w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record_id))


def id_of(w: Any, key: str) -> str:
    return str(w.scalar("SELECT id FROM cur_core_record WHERE key = :k", k=key))


def status_of(w: Any, key: str) -> str:
    return str(w.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=id_of(w, key)))


def count(w: Any) -> int:
    return int(w.scalar("SELECT COUNT(*) FROM cur_core_constraint"))


def raise_args(subject: str, actor: str = "user:user", **extra: str) -> list[str]:
    args = ["raise", "--subject", subject, "--phase", "ready", "--severity", "blocking"]
    args += ["--category", "materials", "--owner", "user:user", "--actor", actor]
    for flag, value in extra.items():
        args += [f"--{flag.replace('_', '-')}", value]
    return args


def checks(w: Any, docs: dict[str, str]) -> None:
    iwp = c2.iwp_in_check(w)
    ikey = key_of(w, iwp)

    raised = run(w, *raise_args(ikey, description="Spool note", due="2026-12-01"))
    found = re.search(r"raised (\S+)  version \d+", raised.output)
    ok("raise prints the key and version", raised.exit_code == 0 and found is not None)
    key = found.group(1) if found else ""

    assigned = run(w, "assign", key, "--owner", "user:controller", "--actor", "user:user")
    ok(
        "assign prints the version",
        assigned.exit_code == 0 and f"assign {key}  version" in assigned.output,
    )
    ok("assign moves it to Assigned", status_of(w, key) == "Assigned")

    cleared = run(
        w, "clear", key, "--reason", "Issued", "--cleared-at", "2026-10-20", "--actor", "user:user"
    )
    ok("clear with reason", cleared.exit_code == 0 and status_of(w, key) == "Cleared")

    second = run(w, *raise_args(ikey, category="rfi", description="Hot work permit"))
    key2 = re.search(r"raised (\S+)  version", second.output)
    key2 = key2.group(1) if key2 else ""
    withdrawn = run(w, "withdraw", key2, "--reason", "raised in error", "--actor", "user:user")
    ok("withdraw with reason", withdrawn.exit_code == 0 and status_of(w, key2) == "Withdrawn")

    before = count(w)
    refused = run(w, *raise_args(ikey, actor="user:viewer", description="Refused text"))
    ok(
        "default-role actor refused: error forbidden, exit 1, no row written",
        refused.exit_code == 1
        and refused.output.startswith("error: forbidden")
        and count(w) == before,
    )

    secret = c2.hidden_record(w)
    skey = key_of(w, secret)
    hidden = run(w, *raise_args(skey))
    unknown = run(w, *raise_args(MISSING))
    ok(
        "hidden subject: the text of an unknown key",
        hidden.exit_code == 1
        and hidden.output.replace(skey, "KEY") == unknown.output.replace(MISSING, "KEY"),
    )

    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    mkey = key_of(w, made.stream_id)
    hidden_c = run(w, "clear", mkey, "--reason", "r", "--actor", "user:user")
    unknown_c = run(w, "clear", MISSING, "--reason", "r", "--actor", "user:user")
    ok(
        "hidden constraint: the text of an unknown constraint",
        hidden_c.exit_code == 1
        and hidden_c.output.replace(mkey, "KEY") == unknown_c.output.replace(MISSING, "KEY"),
    )

    both = run(w, *raise_args(ikey, target=ikey, target_ref="permit:P-1"))
    ok("--target with --target-ref: usage error, exit 2", both.exit_code == 2)

    gated = run(
        w,
        "raise", "--subject", ikey, "--phase", "pour", "--severity", "blocking",
        "--category", "materials", "--owner", "user:user", "--actor", "user:user",
        "--description", "Spool secret text",
    )  # fmt: skip
    ok(
        "phase not gated: keys-only message, exit 1",
        gated.exit_code == 1
        and gated.output.startswith("error: ")
        and "secret" not in gated.output,
    )
    ok("no Traceback in any output", all("Traceback" not in out for out in SEEN))
