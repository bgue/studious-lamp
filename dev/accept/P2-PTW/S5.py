"""Acceptance for P2-PTW S5: the lapse job flags each lapse once and changes nothing else (SQLite).

Run: ``uv run python dev/accept/P2-PTW/S5.py``. One ``PASS <check>`` line per check, then
``S5 ok``. The clock is fixed (07:00 UTC on 2026-12-01; the job's ``now`` is a parameter).
"""

from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/permits/tests"))
from permit_world import START, World  # noqa: E402
from tl_adapters.db import as_target, create_schema, make_uow_factory  # noqa: E402
from tl_mod_permits.handlers import permit as handlers  # noqa: E402
from tl_mod_permits.lapse import LIMIT, job_id, run_once  # noqa: E402
from tl_mod_permits.names import JOB_SOURCE  # noqa: E402

LATE = START + timedelta(hours=12)


def passed(name: str) -> None:
    print(f"PASS {name}")


def main() -> None:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s5.db"))
    create_schema(db)
    w = World(db)
    w.people()
    clocked: Any = handlers
    clocked.now = lambda: w.at
    factory = make_uow_factory(db)

    def run(project: str = "P123") -> int:
        return run_once(factory, project, w.at)

    permit = w.active()
    before = w.row(permit)
    assert run() == 0
    passed("a permit that is still valid is not flagged")
    w.at = LATE
    assert run() == 1 and run() == 0
    (flag,) = w.rows("SELECT source FROM events WHERE event_type = 'Permit.Lapsed'")
    assert flag["source"] == JOB_SOURCE
    passed("a lapsed permit is flagged once, by the job source")
    after = w.row(permit)
    kept = {k: v for k, v in after.items() if k not in ("lapse_flagged_for", "last_seq")}
    assert kept == {k: v for k, v in before.items() if k not in ("lapse_flagged_for", "last_seq")}
    assert w.state(permit) == "Active"
    passed("the run changes the flag and nothing else")
    assert run("P999") == 0
    passed("another project is not touched")
    w.call("rob", "RevalidatePermit", permit=permit)
    assert run() == 0
    w.at = w.at + timedelta(hours=12)
    assert run() == 1
    passed("a revalidated permit is flagged again once")
    many = w.active_many(LIMIT + 1, w.at - timedelta(hours=1))
    w.at = w.at + timedelta(minutes=1)
    assert run() == LIMIT + 1 and run() == 0 and len(many) == LIMIT + 1
    assert job_id("P123", w.at).startswith("ptwlapse:P123:")
    passed("more than the limit is flagged by one re-queued run")
    factory.dispose()
    print("S5 ok")


if __name__ == "__main__":
    main()
