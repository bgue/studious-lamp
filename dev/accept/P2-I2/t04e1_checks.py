"""The checks of dev/accept/P2-I2/T04e1.py: the `tl awp iwp` write verbs on a SQLite ledger."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import typer
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/awp/tests"))
import s3_checks as s3  # noqa: E402
from awp_world import SCOPE, World  # noqa: E402
from tl_cli.awp_iwp_write import register  # noqa: E402

PROJECT = "P123"
HASH_LINE = re.compile(r"^record hash ([0-9a-f]{64})$", re.M)


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def run(app: typer.Typer, target, *argv: str, who: str | None = "user:sue"):
    """One `tl awp iwp` invocation on the ledger ``target``, as ``who``."""
    args = [*argv, "--project", PROJECT]
    if who is not None:
        args += ["--actor", who]
    return CliRunner().invoke(app, args, obj=target)


def made(result, verb: str) -> str:
    """The number or key a create verb printed (empty when it did not)."""
    found = re.search(rf"^{verb} (\S+)$", result.stdout, re.M)
    return found.group(1) if found and result.exit_code == 0 else ""


def printed(name: str, result, pattern: str) -> None:
    ok(name, result.exit_code == 0 and re.search(pattern, result.stdout, re.M) is not None)


def refused(name: str, result, text: str) -> None:
    clean = result.exit_code == 1 and text in result.stderr and "Traceback" not in result.output
    ok(name, clean)


def _item(description: str, hours: str) -> list[str]:
    """The options of one piping scope item, 1 m, with its hours."""
    return ["--commodity", "piping", "--description", description, "--qty", "1", "--uom", "m",
            "--hours", hours]  # fmt: skip


def iwp_id(w: World, number: str) -> str:
    row = w.scalar(
        "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k", s=SCOPE, k=number
    )
    return str(row)


def checks(w: World, work: Path) -> None:
    os.environ["TL_ENV"] = "dev"
    os.environ["TL_SESSION_FILE"] = str(work / "session.json")
    target = w.db
    app = typer.Typer()
    register(app)

    def create(who: str, *argv: str) -> str:
        return made(run(app, target, "create", *argv, who=who), "created IWP")

    n = create("user:uma", "--discipline", "PIP", "--title", "Rack secret", "--crew", "Crew A",
               "--planned-start", "2026-12-01", "--foreman", "user:uma")  # fmt: skip
    ok("create an IWP", n != "")
    keys = []
    for k in range(3):
        item = run(app, target, "item-create", *_item(f"Spool {k}", "10"), who="user:uma")
        keys.append(made(item, "created scope item"))
    ok("create three scope items", all(keys))
    printed("add three items", run(app, target, "add-scope", n, *keys, who="user:uma"),
            rf"^add-scope {n}  3 items  version \d+$")  # fmt: skip
    printed("remove one item", run(app, target, "remove-scope", n, keys[2], who="user:uma"),
            rf"^remove-scope {n}  1 items")  # fmt: skip
    run(app, target, "add-scope", n, keys[2], who="user:uma")
    docs = w.documents(work / "objects", "ISO-1")
    dkey = w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=docs["ISO-1"])
    printed("pin the current revision", run(app, target, "pin", n, str(dkey), who="user:uma"),
            rf"^pin {n}  version \d+$")  # fmt: skip
    w.set_status(iwp_id(w, n), "Ready")
    s3.readiness(w, iwp_id(w, n), True)
    shown = run(app, target, "hash", n, who=None)
    found = HASH_LINE.search(shown.stdout)
    ok("hash prints the record hash", shown.exit_code == 0 and found is not None)
    h = found.group(1) if found else ""
    sign = ["sign-off", n, "--hash", h]
    refused("plain user refused", run(app, target, *sign, who="user:uma"), "error: forbidden")
    refused("wrong hash refused", run(app, target, "sign-off", n, "--hash", "0" * 64), "error:")
    printed("first signer", run(app, target, *sign), rf"^sign-off {n}  version \d+$")
    refused("same signer twice refused", run(app, target, *sign), "error:")
    printed("second signer", run(app, target, *sign, who="user:sam"), rf"^sign-off {n}  version")
    printed("issue to the foreman", run(app, target, "issue", n, "--hash", h, "--foreman",
            "user:sam"), rf"^issue {n}  version")  # fmt: skip
    printed("hold", run(app, target, "hold", n, "--reason", "Waiting"), rf"^hold {n}  version")
    printed("release hold", run(app, target, "release-hold", n, "--reason", "ok"),
            rf"^release-hold {n}  version")  # fmt: skip
    refused(
        "unknown number prints one error",
        run(app, target, "hash", "NOPE", who=None),
        "error: no IWP NOPE",
    )
    big = create("user:uma", "--discipline", "PIP", "--title", "Big")
    bkeys = []
    for k in range(3):
        item = run(app, target, "item-create", *_item(f"Big {k}", "500"), who="user:uma")
        bkeys.append(made(item, "created scope item"))
    run(app, target, "add-scope", big, *bkeys, who="user:uma")
    printed("split by hours on an oversize IWP",
            run(app, target, "split", big, "--by-hours", "--reason", "Oversize", who="user:uma"),
            rf"^split {big}$")  # fmt: skip
    ok("split source is Split", w.state(iwp_id(w, big)) == "Split")
    both = run(app, target, "split", big, "--by-hours", "--group", "a,b", "--reason", "r")
    ok("split forms are exclusive (exit 2)", both.exit_code == 2)
