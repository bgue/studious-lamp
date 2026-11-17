"""The readiness check ``scaffold_tagged`` (P2-I4B T05a). The ledger is made by real commands."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from scaffold_world import SCAFFOLD, SCOPE, World
from sqlalchemy import Engine, event
from tl_adapters.db import as_target, make_engine, open_uow
from tl_core.readiness import (
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_core.services.links import RetractLink, handle_retract_link
from tl_mod_scaffold.readiness import NO_SCAFFOLD, UNKNOWN, ScaffoldTagged, scaffold_tagged

PAST = date(2000, 1, 1)
FAR = date(2099, 1, 1)
RECORD_TYPES = frozenset({"awp.IWP", SCAFFOLD, "scaffold.ScaffoldInspection"})


class Rig:
    def __init__(self, world: World) -> None:
        self.world = world
        self.engine: Engine = make_engine(world.db)
        self.check = scaffold_tagged()

    def facts(self, iwp: str, key: str = "IWP-1") -> IwpFacts:
        return IwpFacts(record_id=iwp, scope=SCOPE, key=key, status="Issued")

    def answer(self, iwp: str, today: date = PAST) -> CheckResult:
        with self.engine.connect() as conn:
            return self.check.evaluate(conn, self.facts(iwp), today)

    def scaffold(self, to: str | None, iwp: str | None = None) -> str:
        """A scaffold driven to ``to`` (None: Requested), required by ``iwp`` when given."""
        sid = self.world.register()
        if to is not None:
            self.world.advance(sid, to)
        if iwp is not None:
            self.world.require(iwp, sid)
        return sid


@pytest.fixture
def rig(world: World) -> Iterator[Rig]:
    r = Rig(world)
    yield r
    r.engine.dispose()


def iwp_of(rig: Rig, key: str = "IWP-1") -> str:
    return rig.world.iwp(key, "Issued")


def refs(result: CheckResult) -> list[str]:
    return [r.record_id for r in result.resolve_via]


def contract(rig: Rig, iwp: str, expect_n_a: bool) -> None:
    world = ContractWorld(rig.engine.connect, rig.facts(iwp), PAST, RECORD_TYPES, expect_n_a)
    try:
        check_readiness_contract(rig.check, world)
    except ContractViolation as exc:  # pragma: no cover - the failure text is the message
        pytest.fail(str(exc))


def test_the_check_is_found_by_name_with_its_watches() -> None:
    found = load_checks()["scaffold_tagged"]
    assert isinstance(found, ScaffoldTagged)
    assert (found.name, found.version) == ("scaffold_tagged", "1")
    assert found.watches == frozenset({SCAFFOLD})


def test_no_required_scaffold_is_n_a_and_the_contract_holds(rig: Rig) -> None:
    iwp = iwp_of(rig)
    contract(rig, iwp, True)
    got = rig.answer(iwp)
    assert got.state == "n_a" and got.detail == NO_SCAFFOLD and not got.resolve_via
    other = iwp_of(rig, "IWP-2")
    rig.scaffold("Erecting", other)  # another package's scaffold is none of this one's
    assert rig.answer(iwp).state == "n_a"


@pytest.mark.parametrize("stage", ["Inspected", "In Use"])
def test_a_green_standing_scaffold_in_date_is_ok(rig: Rig, stage: str) -> None:
    iwp = iwp_of(rig)
    rig.scaffold(stage, iwp)
    contract(rig, iwp, False)
    got = rig.answer(iwp)
    assert got.state == "ok" and (got.count_ok, got.count_total) == (1, 1)
    assert got.detail.startswith("1/1") and not got.resolve_via


def test_every_required_scaffold_must_be_good(rig: Rig) -> None:
    iwp = iwp_of(rig)
    good = rig.scaffold("In Use", iwp)
    building = rig.scaffold("Erecting", iwp)
    waiting = rig.scaffold(None, iwp)
    got = rig.answer(iwp)
    assert got.state == "blocked" and (got.count_ok, got.count_total) == (1, 3)
    assert got.detail.startswith("1/3") and good not in refs(got)
    assert sorted(refs(got)) == sorted([building, waiting])
    assert {(r.record_type, r.key) for r in got.resolve_via} == {
        (SCAFFOLD, "P123-SCF-0002"),
        (SCAFFOLD, "P123-SCF-0003"),
    }
    contract(rig, iwp, False)


def test_a_yellow_a_red_and_a_modified_scaffold_block(rig: Rig) -> None:
    iwp = iwp_of(rig)
    yellow = rig.scaffold("In Use", iwp)
    rig.world.call("uma", "InspectScaffold", scaffold=yellow, result="conditional")
    assert rig.answer(iwp).state == "blocked"
    rig.world.call("sue", "TagScaffoldGreen", scaffold=yellow)  # green again
    assert rig.answer(iwp).state == "ok"
    rig.world.call("uma", "InspectScaffold", scaffold=yellow, result="fail", note="Loose ledger")
    red = rig.answer(iwp)  # red tag, the scaffold went to Modify
    assert red.state == "blocked" and refs(red) == [yellow]
    rig.world.call("sue", "TagScaffoldGreen", scaffold=yellow)
    assert rig.answer(iwp).state == "ok"
    rig.world.call("uma", "ModifyScaffold", scaffold=yellow, reason="Add a lift")
    assert rig.answer(iwp).state == "blocked"  # green tag, but it is being changed


def test_a_scaffold_being_taken_down_blocks(rig: Rig) -> None:
    iwp = iwp_of(rig)
    sid = rig.scaffold("Inspected")
    rig.world.call("uma", "DismantleScaffold", scaffold=sid, reason="Work done")
    rig.world.require(iwp, sid)
    assert rig.answer(iwp).state == "blocked"


def test_overdue_blocks_and_the_due_day_itself_does_not(rig: Rig) -> None:
    iwp = iwp_of(rig)
    sid = rig.scaffold("In Use", iwp)
    day = date.fromisoformat(str(rig.world.row(sid)["next_due_on"]))
    assert rig.answer(iwp, PAST).state == "ok"
    assert rig.answer(iwp, day).state == "ok"
    assert rig.answer(iwp, day + timedelta(days=1)).state == "blocked"
    assert rig.answer(iwp, FAR).state == "blocked"


def test_a_retracted_link_is_ignored(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rig.scaffold("Erecting", iwp)
    assert rig.answer(iwp).state == "blocked"
    link = rig.world.scalar("SELECT link_id FROM cur_links WHERE from_id = :i", i=iwp)
    with open_uow(rig.world.db) as uow:
        handle_retract_link(
            uow,
            RetractLink(
                actor="user:uma", source="test", scope=SCOPE, link_id=link, reason="Not needed"
            ),
        )
    assert rig.answer(iwp).state == "n_a"


def test_a_read_that_fails_is_unknown_with_fixed_text(tmp_path: Path) -> None:
    empty = make_engine(as_target(str(tmp_path / "empty.db")))
    try:
        facts = IwpFacts(record_id="01JX", scope=SCOPE, key="IWP-1", status="Issued")
        with empty.connect() as conn:
            got = scaffold_tagged().evaluate(conn, facts, PAST)
    finally:
        empty.dispose()
    assert got.state == "unknown" and got.detail == UNKNOWN and not got.resolve_via


def test_the_check_runs_a_fixed_number_of_statements(rig: Rig) -> None:
    iwp = iwp_of(rig)
    for stage in ("In Use", "Erecting", "Inspected"):
        rig.scaffold(stage, iwp)
    seen: list[str] = []

    def listen(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
        if not statement.lstrip().upper().startswith(("BEGIN", "COMMIT", "ROLLBACK")):
            seen.append(statement)  # the adapter's transaction statements are not reads

    with rig.engine.connect() as conn:
        event.listen(conn, "before_cursor_execute", listen)
        try:
            rig.check.evaluate(conn, rig.facts(iwp), PAST)
        finally:
            event.remove(conn, "before_cursor_execute", listen)
    assert len(seen) <= 1
