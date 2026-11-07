"""Acceptance for P2-I2-T04g: CLI glue and the readiness follower. SQLite temp ledger.

One ``PASS <check>`` per line; final line ``T04g ok`` (or exit with ``FAIL <check>``).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import s4_world as sw  # noqa: E402
from tl_adapters.db import make_uow_factory  # noqa: E402
from tl_adapters.queue import job_queue_for  # noqa: E402
from tl_cli.main import app  # noqa: E402
from tl_core.jobs import JobRunner  # noqa: E402
from tl_mod_awp.readiness.follow import Follower  # noqa: E402
from tl_mod_awp.readiness.job import ReadinessKind  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

os.environ["TL_ENV"] = "dev"  # --actor alone is accepted on a ledger file
PROJECT = ["--project", "P123", "--actor", "user:uma"]


def ok(name: str, cond: object = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def main() -> None:
    path = Path(tempfile.mkdtemp()) / "t04g.db"
    w = sw.build(path)
    runner = CliRunner()

    def tl(*args: str) -> tuple[int, str]:
        res = runner.invoke(app, ["--db", str(path), *args])
        return res.exit_code, res.output + (res.stderr if res.stderr_bytes else "")

    _, out = tl("awp", "iwp", "--help")
    ok(
        "iwp help lists ls show scope create",
        all(v in out for v in ("ls", "show", "scope", "create")),
    )
    _, out = tl("constraint", "--help")
    ok(
        "constraint help lists the verbs",
        all(v in out for v in ("ls", "show", "groups", "raise", "assign", "clear", "withdraw")),
    )
    code, out = tl("awp", "readiness", "--help")
    ok(
        "awp readiness --help exits 0 and lists ls show",
        code == 0 and "ls" in out and "show" in out,
    )

    iwp = w.iwp()
    key = w.column("cur_core_record", "key", iwp)
    sw.run(
        w,
        lambda uow: uow.conn().execute(
            sw.text("UPDATE cur_core_record SET status = 'Constraint check' WHERE id = :i"),
            {"i": iwp},
        ),
    )
    factory = make_uow_factory(w.db, registry=sw.registry())
    follower = Follower(factory, sw.checks())
    with factory() as uow:
        queue = job_queue_for(uow.conn())
    jobs = JobRunner(factory, queue, [ReadinessKind(lambda: sw.checks(), lambda: sw.TODAY)])
    ok(
        "follower start queues the IWP in Constraint check",
        follower.poll() == 0 and len(jobs.run_until_idle()) == 1,
    )
    code, out = tl(
        "constraint",
        "raise",
        *PROJECT,
        "--subject",
        key,
        "--phase",
        "ready",
        "--severity",
        "blocking",
        "--category",
        "materials",
        "--owner",
        "user:uma",
    )
    ok("constraint raise", code == 0 and out.startswith("raised "))
    ckey = out.split()[1]
    _, out = tl("constraint", "ls", *PROJECT)
    ok("constraint ls shows it", ckey in out)
    n = follower.poll()
    ok(f"follower: raised constraint requests an evaluation ({n})", n == 1)
    ok("the readiness job ran", len(jobs.run_until_idle()) == 1)
    ok("own events do not ask again", follower.poll() == 0)
    code, out = tl("constraint", "clear", ckey, *PROJECT, "--reason", "done")
    ok("constraint clear", code == 0 and out.startswith("clear "))
    ok("follower: clear requests an evaluation", follower.poll() == 1)
    ok("the readiness job ran after the clear", len(jobs.run_until_idle()) == 1)
    print("T04g ok")


if __name__ == "__main__":
    main()
