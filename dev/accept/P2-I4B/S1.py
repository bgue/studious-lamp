"""Acceptance for P2-I4B S1: the scaffold lifecycle, tag, dismantle check and job (SQLite).

Run: ``uv run python dev/accept/P2-I4B/S1.py``. One ``PASS <check>`` line per check, then ``S1 ok``.
Command level, on a fresh ledger: an approved scaffold request is registered (``P123-SCF-0001``),
designed, erected, tagged green and released; a failed inspection gives a red tag and Modify; the
dismantle check; the inspections-due job; the ten words; the register refusals.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/scaffold/tests"))
from scaffold_world import World  # noqa: E402
from tl_adapters.db import as_target, create_schema, make_uow_factory  # noqa: E402
from tl_adapters.queue import job_queue_for  # noqa: E402
from tl_core.auth.access_words import load_access_words, table_word  # noqa: E402
from tl_core.jobs import JobRunner  # noqa: E402
from tl_mod_scaffold.errors import (  # noqa: E402
    DismantleRefused,
    ScaffoldRuleError,
    ScaffoldStateError,
)
from tl_mod_scaffold.inspections_due import InspectionsDueKind, request  # noqa: E402
from tl_mod_scaffold.module import SCAFFOLD_COMMANDS  # noqa: E402

TODAY = datetime.now(UTC).date()


def fresh() -> World:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s1.db"))
    create_schema(db)
    world = World(db)
    world.people()
    return world


def refused(error: type[BaseException], call: Callable[[], Any]) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}")


def passed(name: str) -> None:
    print(f"PASS {name}")


def check_lifecycle() -> None:
    world = fresh()
    sid = world.register()
    assert world.row(sid)["request_id"] and world.state(sid) == "Requested"
    key = world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=sid)
    assert key == "P123-SCF-0001", key
    passed("register gives P123-SCF-0001")
    world.call("uma", "DesignScaffold", scaffold=sid)
    world.call("uma", "ErectScaffold", scaffold=sid)
    assert world.state(sid) == "Erecting"
    passed("design then erect")
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    assert world.state(sid) == "Inspected" and world.row(sid)["tag"] == "green"
    passed("green tag from Erecting: Inspected, tag green")
    world.call("uma", "ReleaseScaffold", scaffold=sid)
    assert world.state(sid) == "In Use"
    passed("release gives In Use")
    world.call("uma", "InspectScaffold", scaffold=sid, result="fail")
    assert world.state(sid) == "Modify" and world.row(sid)["tag"] == "red"
    passed("a fail inspection gives tag red and state Modify")
    refused(ScaffoldStateError, lambda: world.call("uma", "ReleaseScaffold", scaffold=sid))
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    assert world.state(sid) == "Inspected" and world.row(sid)["tag"] == "green"
    world.call("uma", "InspectScaffold", scaffold=sid, result="conditional")
    refused(ScaffoldRuleError, lambda: world.call("uma", "ReleaseScaffold", scaffold=sid))
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    world.call("uma", "ReleaseScaffold", scaffold=sid)
    assert world.state(sid) == "In Use"
    passed("release is refused until the tag is green again")


def check_dismantle() -> None:
    world = fresh()
    sid = world.advance(world.register(), "In Use")
    issued = world.iwp("P123-IWP-0042", "Issued")
    world.require(issued, sid)
    message = refused(
        DismantleRefused,
        lambda: world.call("uma", "DismantleScaffold", scaffold=sid, reason="Done"),
    )
    assert "P123-IWP-0042" in message, message
    passed("an Issued IWP that requires the scaffold refuses dismantle, with its number")
    other = world.advance(world.register(), "In Use")
    world.require(world.iwp("P123-IWP-0043", "Closed"), other)
    world.call("uma", "DismantleScaffold", scaffold=other, reason="Done")
    assert world.state(other) == "Dismantle"
    passed("a Closed IWP does not refuse dismantle")


def check_job() -> None:
    world = fresh()
    sid = world.advance(world.register(), "In Use")
    open_uow = make_uow_factory(world.db)

    def run(days: int) -> int:
        before = world.count()
        with open_uow() as uow:
            request(uow, "P123", TODAY + timedelta(days=days))
        with open_uow() as uow:
            queue = job_queue_for(uow.conn())
        JobRunner(open_uow, queue, [InspectionsDueKind()], worker_id="accept").run_until_idle()
        return world.count() - before

    assert run(8) == 1
    row = world.row(sid)
    assert row["flagged_due_on"] == row["next_due_on"] and world.state(sid) == "In Use"
    assert run(8) == 0 and run(9) == 0
    open_uow.dispose()
    passed("the job flags an overdue scaffold once; running again writes nothing")


def check_words() -> None:
    words = load_access_words()
    expected = {
        "RegisterScaffold": ("scaffold.register", "user"),
        "DesignScaffold": ("scaffold.design", "user"),
        "ErectScaffold": ("scaffold.erect", "user"),
        "InspectScaffold": ("scaffold.inspect", "user"),
        "TagScaffoldGreen": ("scaffold.tag.green", "controller"),
        "ReleaseScaffold": ("scaffold.release", "user"),
        "ModifyScaffold": ("scaffold.modify", "user"),
        "DismantleScaffold": ("scaffold.dismantle", "user"),
        "RemoveScaffold": ("scaffold.remove", "user"),
    }
    for command in SCAFFOLD_COMMANDS:
        word, table = expected[command.model.__name__]
        assert command.access == word and words[word] == table_word(word) == table
    assert words["scaffold.view"] == "read"
    assert len([w for w in words if w.startswith("scaffold.")]) == 10
    passed("each of the ten words resolves to its table word")


def check_register_refusals() -> None:
    world = fresh()
    rejected = world.request(approve=False)
    world.call(
        "sue",
        "RejectRequisition",
        requisition=rejected,
        expected_version=world.version(rejected),
        reason="No",
    )
    refused(
        ScaffoldRuleError,
        lambda: world.call("uma", "RegisterScaffold", request_id=rejected, title="A"),
    )
    passed("register is refused for a Rejected request")
    approved = world.request()
    world.register(approved)
    refused(
        ScaffoldRuleError,
        lambda: world.call("uma", "RegisterScaffold", request_id=approved, title="B"),
    )
    passed("register is refused for a second scaffold on one request")


def main() -> None:
    check_lifecycle()
    check_dismantle()
    check_job()
    check_words()
    check_register_refusals()
    print("S1 ok")


if __name__ == "__main__":
    main()
