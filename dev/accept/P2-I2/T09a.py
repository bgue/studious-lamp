"""Acceptance for P2-I2-T09a: the IWP and constraint reports (SQLite only). Final line ``T09a ok``.

Seeds a ledger with the S4 world helpers (three IWPs in two states, one evaluated with two blocked
checks, one evaluated ready, one never evaluated; four constraints, one hidden by its subject's
class), then runs the checks in ``t09a_checks.py``. Run: ``uv run python dev/accept/P2-I2/T09a.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import s4_world as sw  # noqa: E402
import t09a_checks as t  # noqa: E402
from awp_world import hidden_record  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_core.readiness.types import RecordRef  # noqa: E402
from tl_mod_awp import readiness as rd  # noqa: E402


def set_workflow(w: Any, record: str, state: str) -> None:
    """The IWP list reads the state from ``cur_workflow_state`` (a projection row, written by hand
    here as the test seed; ``set_status`` writes only the record row)."""
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_workflow_state (record_id, scope, workflow, workflow_version, "
                "state, entered_at, transition, transitioned_by, last_seq) VALUES (:i, :s, "
                "'awp-iwp', 1, :st, '2026-11-07T08:00:00Z', 'seed', 'user:uma', 1)"
            ),
            {"i": record, "s": sw.SCOPE, "st": state},
        )


def seed(db: Path) -> dict[str, object]:
    """The world: A (Constraint check, two blocked checks), B (Draft, ready), C (Draft, never)."""
    w = sw.build(db)
    hidden = hidden_record(w)
    if not sw.c2_ready():
        sw.fake_c2(w)
    a = w.iwp(title="Rack A", estimated_hours="12.5")
    b = w.iwp(title="Rack B", estimated_hours="7.0")
    c = w.iwp(title="Rack C", estimated_hours="3.0")
    set_workflow(w, a, "Constraint check")
    keys = {
        "CON-0001": sw.constraint_row(w, a, "ready", "advisory", None),
        "CON-0002": sw.constraint_row(w, b, "start", "blocking", None),
        "CON-0003": sw.constraint_row(w, b, "ready", "blocking", "Cleared"),
        "CON-HID": sw.constraint_row(w, hidden, "ready", "blocking", None),
    }
    with open_uow(w.db) as uow:
        for key, cid in keys.items():
            uow.conn().execute(
                text("UPDATE cur_core_record SET key = :k WHERE id = :i"), {"k": key, "i": cid}
            )
    blocked = sw.Stand("zz_a", "blocked")
    blocked.refs = [RecordRef(record_id=hidden, record_type="x.Rfi", key="CON-HID")]
    a_checks = sw.checks(blocked, sw.Stand("zz_b", "blocked"), sw.Stand("zz_n", "n_a"))
    sw.run(w, rd.evaluate_now, a, sw.TODAY, a_checks)
    sw.run(w, rd.evaluate_now, b, sw.TODAY, sw.checks(sw.Stand("zz_n", "n_a")))
    return {
        "w": w,
        "a": a,
        "b": b,
        "c": c,
        "hidden": hidden,
        "hidden_con": keys["CON-HID"],
        "db": db,
    }


if __name__ == "__main__":
    work = Path(tempfile.mkdtemp())
    db = work / "t09a.db"
    world = seed(db)
    t.checks(world)
    print("T09a ok")
