"""Acceptance for P2-I5-S4b: the waive word, the hold rule, the worker word.

SQLite, dialect-neutral. One ``PASS <check>`` line each, then ``S4b ok``.
Run: ``uv run python dev/accept/P2-I5/S4b.py``.
"""

# ruff: noqa: E501

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(ROOT / "dev/accept/P2-I2"))
import c2_checks as c2  # noqa: E402
import progress_world as pw  # noqa: E402
from awp_world import SCOPE, World, hidden_record, refuses  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import as_target, create_schema, make_uow_factory, open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.constraints import clear_constraint, queries, raise_constraint  # noqa: E402
from tl_core.constraints.commands import ClearConstraint, RaiseConstraint  # noqa: E402
from tl_core.constraints.errors import MSG_WAIVE_WORD  # noqa: E402
from tl_core.constraints.handlers import (  # noqa: E402
    handle_clear_constraint,
    handle_raise_constraint,
)
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.readiness.hold_rule import HoldFollower  # noqa: E402
from typer.testing import CliRunner  # noqa: E402


def check(name: str, ok: bool) -> None:
    if not ok:
        sys.exit(f"FAIL {name}")
    print(f"PASS {name}")


def waive_checks(tmp: Path) -> None:
    w, _ = c2.build(tmp / "waive.db")
    iwp = c2.iwp_in_check(w)

    def chk(facts: str = c2.H1) -> Any:
        return w.mod(
            lambda u: raise_constraint(
                u, subject_id=iwp, phase="start", severity="blocking", category="materials",
                source="check", check_name="c2", facts_hash=facts, by_module="awp",
            )
        )  # fmt: skip

    def state(cid: str) -> str:
        return str(
            w.scalar("SELECT COALESCE(status,'Open') FROM cur_core_record WHERE id=:i", i=cid)
        )

    def waived(cid: str) -> bool:
        return bool(w.read(queries.get_constraint, "admin", cid).waived)

    a = chk()
    err = refuses(
        ForbiddenError,
        lambda: w.run("user", "ClearConstraint", constraint=a.constraint_id, reason="r"),
    )
    check("a plain user clearing a check-raised constraint is refused with MSG_WAIVE_WORD",
          str(err) == MSG_WAIVE_WORD and state(a.constraint_id) == "Open")  # fmt: skip
    w.run("waiver", "ClearConstraint", constraint=a.constraint_id, reason="accepted")
    check("the holder with a reason clears it and the row reads waived",
          state(a.constraint_id) == "Cleared" and waived(a.constraint_id))  # fmt: skip
    b = chk(c2.H3)
    for reason in ("", "x" * 301):
        refuses(
            ValidationError,
            lambda r=reason: w.run(
                "waiver", "ClearConstraint", constraint=b.constraint_id, reason=r
            ),
        )
    check(
        "an empty reason and a 301-character reason are refused", state(b.constraint_id) == "Open"
    )
    m = w.raise_(iwp)
    w.run("user", "ClearConstraint", constraint=m.stream_id, reason="done")
    check(
        "a manual constraint clears with the edit word alone and reads waived false",
        not waived(m.stream_id),
    )
    c = chk("d" * 64)
    w.mod(lambda u: clear_constraint(u, constraint_id=c.constraint_id, reason="gone", by_module="awp",
                                     cleared_at=None, resolved_by=None))  # fmt: skip
    check("a module clear of a check constraint needs no word and reads waived false",
          state(c.constraint_id) == "Cleared" and not waived(c.constraint_id))  # fmt: skip
    with open_uow(w.db) as uow:
        accounts.create_account(uow, username="bot", display_name="Bot", kind="agent", roles=["user"],
                                password=None, by="svc:test")  # fmt: skip
    spec = c2.CMDS["ClearConstraint"]
    cmd = spec.model(
        actor="agent:bot", source="t", scope=SCOPE, constraint=b.constraint_id, reason="r"
    )

    def agent_clear() -> Any:
        with open_uow(w.db) as uow:
            return spec.handler(uow, cmd)

    check(
        "an agent actor is refused the word",
        str(refuses(ForbiddenError, agent_clear)) == MSG_WAIVE_WORD,
    )
    check("the waived clear keeps the suppress hash: the check does not re-raise",
          w.row(a.constraint_id)["suppress_hash"] == c2.H1
          and w.modraise(iwp, "check", phase="start", check_name="c2", facts_hash=c2.H1).action == "suppressed")  # fmt: skip
    secret = hidden_record(w)
    with cf.system_view():
        h = w.modraise(secret, "check", check_name="c9", facts_hash=c2.H1)
    refuses(
        RecordNotFoundError,
        lambda: w.run("waiver", "ClearConstraint", constraint=h.constraint_id, reason="r"),
    )
    w.run("ada", "ClearConstraint", constraint=h.constraint_id, reason="r")
    check("a hidden waived constraint reads as missing to a viewer who cannot see it",
          w.read(queries.get_constraint, "user", h.constraint_id) is None)  # fmt: skip


def hold_checks(tmp: Path) -> None:
    p = pw.build(tmp / "hold.db")
    w = p.w
    follower = HoldFollower(make_uow_factory(w.db))
    follower.poll()

    def issued(status: str = "Issued") -> str:
        i = w.iwp(planned_start="2026-12-01", foreman="user:uma")
        w.set_status(i, status)
        return i

    def events() -> int:
        return int(w.scalar("SELECT COUNT(*) FROM events"))

    a = issued()
    p.raise_blocking(a, "complete")
    check("the raise holds nothing by itself", w.state(a) == "Issued")
    check("one poll holds the Issued IWP", follower.poll() == 1 and w.state(a) == "On hold")
    n = events()
    again = follower.poll()
    with open_uow(w.db) as uow:
        uow.conn().execute(text("UPDATE rule_cursor SET last_seq = 0 WHERE name = 'awp.hold'"))
    replay = HoldFollower(make_uow_factory(w.db)).poll()
    check(
        "a second poll and a replay of the outbox rows change nothing",
        again == replay == 0 and events() == n,
    )
    others = []
    for status in ("Ready", "In progress", "On hold"):
        i = issued(status)
        p.raise_blocking(i, "complete")
        others.append((i, status))
    before = events()
    check("Ready, In progress and On hold are untouched",
          follower.poll() == 0 and events() == before and all(w.state(i) == s for i, s in others))  # fmt: skip
    d = issued()
    p.raise_blocking(d, "complete")
    cid = str(w.rows("SELECT id FROM cur_core_constraint WHERE subject_id=:i", i=d)[0]["id"])
    with open_uow(w.db) as uow:
        handle_clear_constraint(
            uow,
            ClearConstraint(actor="user:sue", source="t", scope=SCOPE, constraint=cid, reason="r"),
        )
    check(
        "a constraint cleared before the poll holds nothing",
        follower.poll() == 0 and w.state(d) == "Issued",
    )
    e = issued()
    with open_uow(w.db) as uow:
        handle_raise_constraint(uow, RaiseConstraint(actor="user:sue", source="t", scope=SCOPE, subject=e,
            phase="complete", severity="advisory", category="other", owner="user:uma"))  # fmt: skip
    check("a non-blocking severity holds nothing", follower.poll() == 0 and w.state(e) == "Issued")


def worker_checks(tmp: Path) -> None:
    from tl_cli.main import app

    db = tmp / "worker.db"
    w = World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp / "session.json")}

    def run(who: str) -> Any:
        return CliRunner().invoke(
            app, ["--db", str(db), "awp", "worker", "--once", "--actor", who], env=env
        )

    refused = run("user:uma")
    check("tl awp worker --once without awp.worker.run is refused with the fixed text",
          refused.exit_code == 1 and "tl awp worker needs the awp.worker.run access word" in refused.stderr)  # fmt: skip
    check("tl awp worker --once with the word runs", run("user:ada").exit_code == 0)


if __name__ == "__main__":
    os.environ.setdefault("TL_ENV", "dev")
    base = Path(tempfile.mkdtemp())
    waive_checks(base)
    hold_checks(base)
    worker_checks(base)
    print("S4b ok")
