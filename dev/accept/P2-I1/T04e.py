"""Acceptance for P2-I1-T04e: `tl awp rollup` and `tl awp worker`, on a S4 seed copy.

The seed is copied to a temporary file; the verbs run through ``CliRunner`` on a local Typer app
with the root ``--db`` (as ``tl_cli.main`` passes it) and ``awp_run.register`` on the awp app. The
seed has no rollup rows (D25), so the first worker run must write them: ``views.wbs_tree`` then
shows a node with a total. Run: ``uv run python dev/accept/P2-I1/T04e.py --db .accept/p2-i1.db``
(the seed: ``S4.py --keep``). One ``PASS`` per check, then ``T04e ok``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import typer
from tl_adapters.db import as_target, open_uow
from tl_cli import awp_run
from tl_mod_awp import views
from typer.testing import CliRunner, Result

PROJECT = "P123"
SUPER = "user:sue"
SCOPE = f"project:{PROJECT}"


def check(ok: bool, what: str) -> None:
    if not ok:
        sys.exit(f"FAIL {what}")
    print(f"PASS {what}")


def build_app() -> typer.Typer:
    """The `tl awp` verbs on a local app; the root callback takes ``--db``."""
    app = typer.Typer()

    @app.callback()
    def root(ctx: typer.Context, db: str = typer.Option(..., "--db")) -> None:
        ctx.obj = as_target(db)

    awp_run.register(app)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="the S4 seed (SQLite file)")
    args = parser.parse_args()
    runner = CliRunner()
    app = build_app()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t04e.db"
        shutil.copyfile(args.db, copy)

        # a dev ledger file: --actor names any actor, and the session file stays in the temp dir
        env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(Path(tmp) / "session.json")}

        def run(*argv: str) -> Result:
            return runner.invoke(app, ["--db", str(copy), *argv], env=env)

        # rollup: queues once; a second call exits 0 and queues nothing new
        first = run("rollup", "--project", PROJECT, "--actor", SUPER)
        second = run("rollup", "--project", PROJECT, "--actor", SUPER)
        check(
            first.exit_code == 0 and second.exit_code == 0
            and first.stdout.startswith("rollup requested  job ")
            and second.stdout == first.stdout,
            "rollup",
        )  # fmt: skip

        # worker --once: runs the one queued rollup, then the WBS has a total
        once = run("worker", "--once")
        ran = [r for r in once.stdout.splitlines() if r.startswith("ran ")]
        with open_uow(as_target(str(copy))) as uow:
            tree = views.wbs_tree(uow.conn(), SCOPE)
        totals = [row.total_hours for row in tree if row.total_hours is not None]
        check(
            once.exit_code == 0 and len(ran) == 1 and " awp.rollup " in ran[0]
            and once.stdout.splitlines()[-1] == "worker done: ran=1" and totals != [],
            "worker",
        )  # fmt: skip

        # a second --once has nothing to run
        idle = run("worker", "--once")
        check(
            idle.exit_code == 0 and idle.stdout.splitlines() == ["worker done: ran=0"],
            "idle",
        )  # fmt: skip

        # rollup again, then --requeue: nothing was lost, so 0 is queued first
        run("rollup", "--project", PROJECT, "--actor", SUPER)
        requeue = run("worker", "--once", "--requeue")
        lines = requeue.stdout.splitlines()
        check(
            requeue.exit_code == 0 and lines[:1] == ["requeued 0"]
            and lines[-1].startswith("worker done: ran="),
            "requeue",
        )  # fmt: skip
    print("T04e ok")


if __name__ == "__main__":
    main()
