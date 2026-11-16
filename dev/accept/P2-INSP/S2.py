"""Acceptance for P2-INSP S2: checklists, inspections, punch items in the same step, the subject row
and the hook (SQLite).

Run: ``uv run python dev/accept/P2-INSP/S2.py``. One ``PASS <check>`` line per check, then
``S2 ok``.
"""

from __future__ import annotations

import sys
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/quality/tests"))
from insp_world import IWP, InspWorld, answers  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.modules import load_modules, module_commands  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_quality.errors import ChecklistRuleError, InspectionStateError  # noqa: E402
from tl_mod_quality.handlers.inspection import MSG_SELF_VERIFY  # noqa: E402
from tl_mod_quality.module import INSP_COMMANDS, QUALITY_COMMANDS  # noqa: E402

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def fresh() -> InspWorld:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s2.db"))
    create_schema(db)
    world = InspWorld(db)
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


def check_hook() -> None:
    names = {row.name for row in module_commands() if row.module == "quality"}
    assert names == {c.model.__name__ for c in QUALITY_COMMANDS} and len(names) == 17
    assert len(INSP_COMMANDS) == 11
    spec = next(s for s in load_modules() if s.name == "quality")
    assert spec.commands == "tl_mod_quality.module:QUALITY_COMMANDS"
    assert {p.tool for p in spec.proposable} == {"propose_punch_item", "propose_inspection"}
    marks = tomllib.loads((ROOT / "tests/tools/delegation_marks.toml").read_text())
    assert "PlanInspection" in marks["eligible"]
    passed("hook: 17 commands, two proposal rows, one eligible mark")


def check_checklist_life() -> None:
    world = fresh()
    item = world.checklist(publish=False)
    refused(
        ChecklistRuleError,
        lambda: world.call(
            "sue", "PublishChecklist", checklist=world.checklist(publish=False, questions=[])
        ),
    )
    world.call("sue", "PublishChecklist", checklist=item)
    refused(
        InspectionStateError, lambda: world.call("uma", "EditChecklist", checklist=item, title="x")
    )
    second = str(world.call("sue", "ReviseChecklist", checklist=item).stream_id)
    assert world.checklist_row(second)["checklist_version"] == 2
    world.call("sue", "PublishChecklist", checklist=second)
    assert (
        world.state_of(item, "Draft") == "Retired"
        and world.state_of(second, "Draft") == "Published"
    )
    passed("checklist: publish, edit refused when published, revise v2 retires v1 on publish")


def check_inspection_life() -> None:
    world = fresh()
    iwp = world.record(IWP, "IWP-1")
    item = world.scheduled(iwp, point="hold", area="A1")
    world.recorded(item, answers=answers(q1="no", q2="no"))
    row = world.inspection_row(item)
    assert (row["result"], row["punch_count"]) == ("reject", 2)
    punch = world.raised_by(item)
    assert [p["category"] for p in punch] == ["A", "B"] and {p["source_id"] for p in punch} == {iwp}
    passed("record: reject raises one punch item per failed question, A on a hold, same step")
    assert (
        refused(ForbiddenError, lambda: world.call("rob", "VerifyInspection", inspection=item))
        == MSG_SELF_VERIFY
    )
    world.call("sue", "VerifyInspection", inspection=item)
    passed("verify: the recorder is refused, another controller passes")
    again = str(world.call("uma", "ReinspectInspection", inspection=item).stream_id)
    assert world.inspection_row(again)["reinspection_of_id"] == item
    passed("reinspect: a new Planned inspection names the old one")
    clean = world.scheduled(iwp)
    world.recorded(clean, answers=answers())
    assert world.inspection_row(clean)["result"] == "accept" and world.punch_total() == 2
    passed("record: accept raises no punch item")


def check_hidden_subject() -> None:
    world = fresh()
    secret = world.hidden_record()
    before = world.count()
    texts = set()
    for subject in (secret, "no-such-id"):
        texts.add(
            refused(
                RecordNotFoundError,
                lambda s=subject: world.call(
                    "uma", "PlanInspection", title="t", point="hold", subject_id=s
                ),
            )
        )
    assert texts == {"no record with that id"} and world.count() == before
    item = world.scheduled(secret, who="dora")
    world.recorded(item, who="dora", answers=answers(q1="no"))
    (punch,) = world.raised_by(item)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        assert cf.is_hidden(conn, item) and cf.is_hidden(conn, punch["id"])
        assert not cf.is_hidden(conn, item, CLEARED) and not cf.is_hidden(
            conn, punch["id"], CLEARED
        )
    passed("confidentiality: hidden subject refused as missing; inspection and punch item inherit")


def main() -> None:
    check_hook()
    check_checklist_life()
    check_inspection_life()
    check_hidden_subject()
    print("S2 ok")


if __name__ == "__main__":
    main()
