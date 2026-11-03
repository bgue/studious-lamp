"""Acceptance for P2-I1-T04c: the `tl awp` write verbs for CWPs and packages, on a S4 seed copy.

The seed is copied to a temporary file; the verbs run through ``CliRunner`` on a local Typer app
with the root ``--db`` (as ``tl_cli.main`` passes it) and the read verbs (``awp_read``) beside them,
so each write is checked by a read. The superuser of the seed (``user:sue``) runs the writes; the
plain ``user:uma`` runs the one refused move. Refusals must exit 1 with ``error:`` on stderr.
Run: ``uv run python dev/accept/P2-I1/T04c.py --db .accept/p2-i1.db`` (the seed: ``S4.py --keep``).
One ``PASS`` per check, then ``T04c ok``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import typer
from tl_adapters.db import as_target
from tl_cli import awp_read, awp_write
from typer.testing import CliRunner, Result

PROJECT = "P123"
SUPER = "user:sue"
PLAIN = "user:uma"
EWP = "EWP-T04C-1"


def line_of(output: str, prefix: str, suffix: str) -> bool:
    """True when some line of ``output`` starts with ``prefix`` and ends with ``suffix``."""
    return any(r.startswith(prefix) and r.endswith(suffix) for r in output.splitlines())


def check(ok: bool, what: str) -> None:
    if not ok:
        sys.exit(f"FAIL {what}")
    print(f"PASS {what}")


def build_app() -> typer.Typer:
    """The `tl awp` reads and writes on a local app; the root callback takes ``--db``."""
    app = typer.Typer()

    @app.callback()
    def root(ctx: typer.Context, db: str = typer.Option(..., "--db")) -> None:
        ctx.obj = as_target(db)

    awp_read.register(app)
    awp_write.register(app)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="the S4 seed (SQLite file)")
    args = parser.parse_args()
    runner = CliRunner()
    app = build_app()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t04c.db"
        shutil.copyfile(args.db, copy)

        # a dev ledger file: --actor names any actor, and the session file stays in the temp dir
        env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(Path(tmp) / "session.json")}

        def run(*argv: str) -> Result:
            return runner.invoke(app, ["--db", str(copy), *argv], env=env)

        def shown(number: str) -> str:
            return run("cwp", "show", number, "--project", PROJECT).stdout

        # create, then the read shows it
        made = run(
            "cwp", "create", "--project", PROJECT, "--actor", SUPER,
            "--discipline", "PIP", "--title", "T04c test", "--cwa", "A2",
            "--planned-start", "2026-11-02", "--planned-finish", "2027-01-29",
            "--budget-hours", "250", "--contractor", "Acme Fab",
            "--qty", "piping:480:m", "--qty", "concrete:12.5:m3",
        )  # fmt: skip
        found = re.search(r"^created CWP (\S+)$", made.stdout, re.M)
        num = found.group(1) if found else ""
        listed = run("cwp", "ls", "--project", PROJECT).stdout
        check(
            made.exit_code == 0 and found is not None and num in listed
            and "title T04c test" in shown(num) and "state Planned" in shown(num),
            "create",
        )  # fmt: skip

        # revise changes the title and only the title
        rev = run("cwp", "revise", num, "--project", PROJECT, "--actor", SUPER,
                  "--title", "T04c renamed")  # fmt: skip
        check(
            rev.exit_code == 0 and rev.stdout.startswith(f"revise {num}  version ")
            and "title T04c renamed" in shown(num) and "budget 250.0" in shown(num),
            "revise",
        )  # fmt: skip

        # allocate: two WBS leaves (1.1 and 1.2 are parents in the seed; see the report)
        alloc = run("cwp", "allocate", num, "--project", PROJECT, "--actor", SUPER,
                    "--wbs", "1.1.1:60", "--wbs", "1.2.1:40")  # fmt: skip
        body = shown(num)
        check(
            alloc.exit_code == 0 and "allocations 2" in body
            and "  1.1.1  60.00" in body and "  1.2.1  40.00" in body,
            "allocate",
        )  # fmt: skip

        # move: start-development reaches In development
        move = run("cwp", "move", num, "start-development", "--project", PROJECT, "--actor", SUPER)
        check(
            move.exit_code == 0 and move.stdout.startswith(f"move {num}  version ")
            and "state In development" in shown(num),
            "move",
        )  # fmt: skip

        # packages: record, update, void
        rec = run(
            "package", "record", "--project", PROJECT, "--actor", SUPER, "--type", "ewp",
            "--number", EWP, "--title", "T04c EWP", "--constraint-source",
            "--status", "Issued", "--forecast", "2027-01-15",
        )  # fmt: skip
        listed = run("package", "ls", "--project", PROJECT).stdout
        upd = run(
            "package", "update", EWP, "--project", PROJECT, "--actor", SUPER,
            "--status", "IFC", "--no-constraint-source",
        )  # fmt: skip
        after = run("package", "ls", "--project", PROJECT).stdout
        gone = run(
            "package", "void", EWP, "--project", PROJECT, "--actor", SUPER, "--reason", "T04c"
        )  # fmt: skip
        left = run("package", "ls", "--project", PROJECT).stdout
        check(
            rec.exit_code == 0 and rec.stdout.startswith(f"record {EWP}  version ")
            and line_of(listed, f"{EWP}  EWP  Issued", "  yes")
            and upd.exit_code == 0 and upd.stdout.startswith(f"update {EWP}  version ")
            and line_of(after, f"{EWP}  EWP  IFC", "  no")
            and gone.exit_code == 0 and gone.stdout.startswith(f"void {EWP}  version ")
            and EWP not in left,
            "package",
        )  # fmt: skip

        # refusals: each exits 1 with `error:` on stderr
        forbidden = run("cwp", "move", num, "release", "--project", PROJECT, "--actor", PLAIN)
        check(forbidden.exit_code == 1 and "error: forbidden" in forbidden.stderr, "forbidden")
        unknown = run(
            "cwp", "move", "P123-CWP-PIP-9999", "start-development",
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        check(
            unknown.exit_code == 1
            and "error: no CWP 'P123-CWP-PIP-9999' in project P123" in unknown.stderr,
            "unknown",
        )
        parse = run("cwp", "allocate", num, "--project", PROJECT, "--actor", SUPER,
                    "--wbs", "1.1")  # fmt: skip
        check(
            parse.exit_code == 1 and "error: --wbs 1.1: expected CODE:PERCENT" in parse.stderr,
            "parse",
        )
        reason = run("cwp", "move", num, "return", "--project", PROJECT, "--actor", SUPER)
        check(reason.exit_code == 1 and "error: return needs --reason" in reason.stderr, "reason")

        # void last: the CWP is hidden from the reads afterwards
        voided = run(
            "cwp", "void", num, "--project", PROJECT, "--actor", SUPER, "--reason", "T04c clean-up"
        )  # fmt: skip
        hidden = run("cwp", "show", num, "--project", PROJECT)
        check(
            voided.exit_code == 0
            and voided.stdout.startswith(f"void {num}  version ")
            and hidden.exit_code == 1,
            "void",
        )
    print("T04c ok")


if __name__ == "__main__":
    main()
