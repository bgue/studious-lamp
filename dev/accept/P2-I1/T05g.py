"""Acceptance for P2-I1-T05g: `PathVersion.reason_code`, on a S4 seed copy.

The seed (path version 1: A1, A2, A3, A4) is copied to a temporary file. The moves run through
``CliRunner`` as ``tl awp path move`` does (``--actor user:sue``, the superuser of the seed); the
reads are ``views.path_versions`` on the copy. Two checks write to the copy only: a hidden area is
simulated by patching ``views._hidden``, and a version-1 step carrying a reason is set with one
UPDATE on the copy's ``cur_awp_path_step`` (the seed never has one). The seed is not touched.

Run: ``uv run python dev/accept/P2-I1/T05g.py --db .accept/p2-i1.db`` (the seed: ``S4.py --keep``).
Prints ``PASS <check>`` per check, then ``T05g ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import typer
from sqlalchemy import text
from tl_adapters.db import as_target, open_uow
from tl_cli import awp_read, awp_write2
from tl_mod_awp import views
from typer.testing import CliRunner, Result

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
SUPER = "user:sue"


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def build_app() -> typer.Typer:
    """The `tl awp` reads and writes on a local app; the root callback takes ``--db``."""
    app = typer.Typer()

    @app.callback()
    def root(ctx: typer.Context, db: str = typer.Option(..., "--db")) -> None:
        ctx.obj = as_target(db)

    awp_read.register(app)
    awp_write2.register(app)
    return app


def by_version(versions: list[views.PathVersion]) -> dict[int, views.PathVersion]:
    return {v.version: v for v in versions}


def check(db: Path) -> None:
    runner = CliRunner()
    app = build_app()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t05g.db"
        shutil.copyfile(db, copy)
        target = as_target(str(copy))
        env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(Path(tmp) / "session.json")}

        def run(*argv: str) -> Result:
            return runner.invoke(app, ["--db", str(copy), *argv], env=env)

        def versions() -> list[views.PathVersion]:
            with open_uow(target, readonly=True) as uow:
                return views.path_versions(uow.conn(), SCOPE)

        def move(cwa: str, to: int, reason: str) -> Result:
            return run(
                "path", "move", cwa, "--to", str(to), "--reason", reason,
                "--project", PROJECT, "--actor", SUPER,
            )  # fmt: skip

        # the seed: version 1 only, and no version carries a reason
        seed = versions()
        need([v.version for v in seed] == [1], f"seed versions {[v.version for v in seed]}")
        need(all(v.reason_code is None for v in seed), "a seed version has a reason")
        passed("seed versions all have reason_code None (v1 only)")
        before = by_version(seed)

        # move A3 to place 1 for Access: version 2 carries Access, version 1 stays None
        first = move("A3", 1, "Access")
        ok = first.exit_code == 0 and first.stdout.startswith("move A3  version ")
        need(ok, f"move 1: {first.stdout}")
        after = by_version(versions())
        need([v.version for v in versions()] == [2, 1], "newest first after one move")
        need(after[2].reason_code == "Access", f"v2 reason {after[2].reason_code}")
        need(after[1].reason_code is None, f"v1 reason {after[1].reason_code}")
        need(after[1].step_count == before[1].step_count, "v1 step_count changed")
        need(after[1].is_current is False and after[2].is_current is True, "is_current")
        need(after[2].step_count == 4 and after[2].is_current, "v2 step_count")
        need(after[1].recorded_at == before[1].recorded_at, "v1 recorded_at changed")
        need(after[1].actor == before[1].actor, "v1 actor changed")
        passed("move A3 to 1 with Access: v2 Access, v1 None, other fields unchanged")

        # a second move for Weather: version 3 carries Weather, version 2 keeps Access
        second = move("A4", 2, "Weather")
        ok = second.exit_code == 0 and second.stdout.startswith("move A4  version ")
        need(ok, f"move 2: {second.stdout}")
        after = by_version(versions())
        need([v.version for v in versions()] == [3, 2, 1], "newest first after two moves")
        need(after[3].reason_code == "Weather", f"v3 reason {after[3].reason_code}")
        need(after[2].reason_code == "Access", f"v2 reason {after[2].reason_code}")
        need(after[1].reason_code is None, f"v1 reason {after[1].reason_code}")
        need(after[3].is_current and not after[2].is_current, "is_current after two moves")
        passed("move A4 to 2 with Weather: v3 Weather, v2 still Access")

        # a hidden area: the step that carries the reason is left out, so the reason is not shown
        with open_uow(target, readonly=True) as uow:
            a3_id = str(
                uow.conn()
                .execute(
                    text(
                        "SELECT s.cwa_id FROM cur_awp_path_step s "
                        "JOIN cur_awp_cwa a ON a.id = s.cwa_id WHERE a.code = 'A3' LIMIT 1"
                    )
                )
                .scalar_one()
            )
        real_hidden = views._hidden

        def hiding(conn_, ids):  # type: ignore[no-untyped-def]
            return set(real_hidden(conn_, ids)) | {a3_id}

        views._hidden = hiding
        try:
            hidden = by_version(versions())
        finally:
            views._hidden = real_hidden
        need(hidden[2].step_count == 3, f"the hidden step was not left out: {hidden[2].step_count}")
        need(hidden[2].reason_code is None, f"v2 reason with A3 hidden: {hidden[2].reason_code}")
        need(hidden[3].reason_code == "Weather", "v3 reason changed with A3 hidden")
        passed("hidden area: v2 reason None")

        # version 1 stays None even when one of its steps carries a reason (a copy-only write)
        with open_uow(target) as uow:
            uow.conn().execute(
                text(
                    "UPDATE cur_awp_path_step SET reason_code = 'Crew' "
                    "WHERE version = 1 AND position = 1"
                )
            )
        carried = by_version(versions())
        need(carried[1].reason_code is None, f"v1 reason {carried[1].reason_code}")
        need(carried[2].reason_code == "Access", "v2 reason changed by the v1 step")
        passed("version 1 stays None with a reason on one of its steps")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    try:
        check(args.db)
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
    print("T05g ok")


if __name__ == "__main__":
    main()
