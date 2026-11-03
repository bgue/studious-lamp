"""Acceptance for P2-I1-T04d: the `tl awp` write verbs for the WBS, the CWAs and the path of
construction, on a S4 seed copy.

The seed is copied to a temporary file; the verbs run through ``CliRunner`` on a local Typer app
with the root ``--db`` (as ``tl_cli.main`` passes it) and the read verbs (``awp_read``) beside them.
Reads back use ``tl_mod_awp.views`` on the copy. The superuser of the seed (``user:sue``) runs the
writes; the plain ``user:uma`` runs the one refused write. Refusals must exit 1 with ``error:`` on
stderr. The WBS view shows budget rollups, not allocations, so a map is checked by its exit status
and the version it prints.
Run: ``uv run python dev/accept/P2-I1/T04d.py --db .accept/p2-i1.db`` (the seed: ``S4.py --keep``).
One ``PASS`` per check, then ``T04d ok``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from tl_adapters.db import as_target, open_uow
from tl_cli import awp_read, awp_write2
from tl_mod_awp import views
from typer.testing import CliRunner, Result

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
SUPER = "user:sue"
PLAIN = "user:uma"
COST = "4210-PIP-WLD"  # a cost code the seed loads
SEED_CWA = "A2"  # an area of the seed's path
REASON = "Access"  # a PathReason code the seed uses


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
    awp_write2.register(app)
    return app


def version_of(result: Result) -> int:
    """The ``n`` of a ``<verb> <code>  version n`` line, or -1 when the line has another shape."""
    head, sep, tail = result.stdout.strip().rpartition("  version ")
    return int(tail) if sep and tail.isdigit() else -1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="the S4 seed (SQLite file)")
    args = parser.parse_args()
    runner = CliRunner()
    app = build_app()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t04d.db"
        shutil.copyfile(args.db, copy)
        target = as_target(str(copy))

        # a dev ledger file: --actor names any actor, and the session file stays in the temp dir
        env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(Path(tmp) / "session.json")}

        def run(*argv: str) -> Result:
            return runner.invoke(app, ["--db", str(copy), *argv], env=env)

        def read(view: Callable[..., Any], *args: Any) -> Any:
            with open_uow(target, readonly=True) as uow:
                return view(uow.conn(), SCOPE, *args)

        # wbs: define a root node and a leaf under it, then read the leaf back
        root = run("wbs", "define", "9", "--title", "Spare", "--project", PROJECT, "--actor", SUPER)
        leaf = run(
            "wbs", "define", "9.1", "--parent", "9", "--title", "Spare leaf",
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        node = read(views.wbs_detail, "9.1")
        check(
            root.exit_code == 0 and root.stdout == "defined WBS 9\n"
            and leaf.exit_code == 0 and leaf.stdout == "defined WBS 9.1\n"
            and node is not None and node.parent_code == "9" and node.title == "Spare leaf",
            "wbs define",
        )  # fmt: skip

        # map: one cost code at 100, then clear; each write is one version later
        mapped = run(
            "wbs", "map", "9.1", "--cost-code", f"{COST}:100",
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        check(
            mapped.exit_code == 0 and mapped.stdout.startswith("map 9.1  version ")
            and version_of(mapped) >= 1,
            "wbs map",
        )  # fmt: skip
        cleared = run("wbs", "map", "9.1", "--clear", "--project", PROJECT, "--actor", SUPER)
        check(
            cleared.exit_code == 0 and version_of(cleared) > version_of(mapped),
            "wbs clear",
        )  # fmt: skip

        # revise changes the title and leaves the parent alone
        rev = run(
            "wbs", "revise", "9.1", "--title", "Spare leaf renamed",
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        node = read(views.wbs_detail, "9.1")
        check(
            rev.exit_code == 0 and rev.stdout.startswith("revise 9.1  version ")
            and node is not None and node.title == "Spare leaf renamed"
            and node.parent_code == "9",
            "wbs revise",
        )  # fmt: skip

        # retire: the node reads back retired
        gone = run(
            "wbs", "retire", "9.1", "--reason", "T04d", "--project", PROJECT, "--actor", SUPER
        )
        node = read(views.wbs_detail, "9.1")
        check(
            gone.exit_code == 0 and gone.stdout.startswith("retire 9.1  version ")
            and node is not None and node.retired,
            "wbs retire",
        )  # fmt: skip

        # cwa: define, revise the location, retire; the list reads each step back
        made = run("cwa", "define", "SP", "--title", "Spare area", "--project", PROJECT,
                   "--actor", SUPER)  # fmt: skip
        located = run("cwa", "revise", "SP", "--location", "Bay 4", "--project", PROJECT,
                      "--actor", SUPER)  # fmt: skip
        retired = run("cwa", "retire", "SP", "--reason", "T04d", "--project", PROJECT,
                      "--actor", SUPER)  # fmt: skip
        areas = [a for a in read(views.cwa_list) if a.code == "SP"]
        check(
            made.exit_code == 0 and made.stdout == "defined CWA SP\n"
            and located.exit_code == 0 and located.stdout.startswith("revise SP  version ")
            and retired.exit_code == 0 and retired.stdout.startswith("retire SP  version ")
            and len(areas) == 1 and areas[0].retired and areas[0].location_text == "Bay 4",
            "cwa",
        )  # fmt: skip

        # path: move a seed area to the front; the path reads back as version 2
        moved = run(
            "path", "move", SEED_CWA, "--to", "1", "--reason", REASON,
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        path_now = read(views.path)
        check(
            moved.exit_code == 0 and moved.stdout.startswith(f"move {SEED_CWA}  version ")
            and path_now is not None and path_now.current_version == 2,
            "path move",
        )  # fmt: skip

        # the seed already has a path: a second definition is refused
        again = run(
            "path", "define", "--step", "A", "--step", "B:Access",
            "--project", PROJECT, "--actor", SUPER,
        )  # fmt: skip
        check(again.exit_code == 1 and "error:" in again.stderr, "path redefine")

        # refusals: each exits 1 with `error:` on stderr
        forbidden = run(
            "wbs", "define", "9.9", "--title", "x", "--project", PROJECT, "--actor", PLAIN
        )  # fmt: skip
        check(forbidden.exit_code == 1 and "error: forbidden" in forbidden.stderr, "forbidden")
        unknown = run("wbs", "revise", "9.9", "--title", "x", "--project", PROJECT,
                      "--actor", SUPER)  # fmt: skip
        check(
            unknown.exit_code == 1 and "error: no WBS node '9.9' in project P123" in unknown.stderr,
            "unknown",
        )
        parse = run("wbs", "map", "9.1", "--cost-code", "100", "--project", PROJECT,
                    "--actor", SUPER)  # fmt: skip
        check(
            parse.exit_code == 1
            and "error: --cost-code 100: expected CODE:PERCENT" in parse.stderr,
            "parse",
        )
        neither = run("wbs", "map", "9.1", "--project", PROJECT, "--actor", SUPER)
        check(
            neither.exit_code == 1 and "error: give --cost-code or --clear" in neither.stderr,
            "map args",
        )
    print("T04d ok")


if __name__ == "__main__":
    main()
