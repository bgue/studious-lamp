"""The readiness check ``labour_requested`` (P2-I4B T05b). The ledger is made by real commands."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from scaffold_world import SCOPE, World
from sqlalchemy import Engine, event
from tl_adapters.db import as_target, make_engine
from tl_core.readiness import (
    CheckResult,
    ContractViolation,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_mod_requisitions.names import LABOR
from tl_mod_scaffold.labour import (
    COVERED,
    NO_ESTIMATE,
    NO_REQUISITION,
    NOT_APPROVED,
    NOT_COVERED,
    UNKNOWN,
    LabourRequested,
    labour_requested,
)

TODAY = date(2026, 11, 1)
START, FINISH = date(2026, 11, 2), date(2026, 11, 13)
RECORD_TYPES = frozenset({"awp.IWP", LABOR})
BODY = {
    "kind": "labor",
    "subject": "Six pipefitters",
    "craft": "Pipefitter",
    "headcount": 6,
    "start_date": "2026-11-02",
    "end_date": "2026-11-13",
}


class Rig:
    def __init__(self, world: World) -> None:
        self.world = world
        self.engine: Engine = make_engine(world.db)
        self.check = labour_requested()

    def facts(self, iwp: str, **more: Any) -> IwpFacts:
        fields: dict[str, Any] = {
            "record_id": iwp,
            "scope": SCOPE,
            "key": "IWP-1",
            "status": "Issued",
            "estimated_hours": 120.0,
            "planned_start": START,
            "planned_finish": FINISH,
        }
        return IwpFacts(**{**fields, **more})

    def answer(self, iwp: str, **more: Any) -> CheckResult:
        with self.engine.connect() as conn:
            return self.check.evaluate(conn, self.facts(iwp, **more), TODAY)

    def raise_one(self, iwp: str, approve: bool = False, **body: Any) -> str:
        made = self.world.call(
            "uma", "RaiseRequisition", requisition={**BODY, **body}, for_record_id=iwp
        )
        rid = str(made.stream_id)
        if approve:
            self.world.call(
                "sue",
                "ApproveRequisition",
                requisition=rid,
                expected_version=self.world.version(rid),
            )
        return rid


@pytest.fixture
def rig(world: World) -> Iterator[Rig]:
    r = Rig(world)
    yield r
    r.engine.dispose()


def iwp_of(rig: Rig, key: str = "IWP-1") -> str:
    return rig.world.iwp(key, "Issued")


def refs(result: CheckResult) -> list[str]:
    return [r.record_id for r in result.resolve_via]


def contract(rig: Rig, iwp: str, expect_n_a: bool, **more: Any) -> None:
    world = ContractWorld(
        rig.engine.connect, rig.facts(iwp, **more), TODAY, RECORD_TYPES, expect_n_a
    )
    try:
        check_readiness_contract(rig.check, world)
    except ContractViolation as exc:  # pragma: no cover - the failure text is the message
        pytest.fail(str(exc))


def test_the_check_is_found_by_name_and_the_placeholder_is_gone() -> None:
    found = load_checks()["labour_requested"]  # a second entry point of the name would raise
    assert isinstance(found, LabourRequested)
    assert (found.name, found.version) == ("labour_requested", "1")
    assert found.watches == frozenset({LABOR})


@pytest.mark.parametrize("hours", [None, 0.0])
def test_no_estimate_is_n_a_and_the_contract_holds(rig: Rig, hours: float | None) -> None:
    iwp = iwp_of(rig)
    contract(rig, iwp, True, estimated_hours=hours)
    got = rig.answer(iwp, estimated_hours=hours)
    assert got.state == "n_a" and got.detail == NO_ESTIMATE and not got.resolve_via
    rig.raise_one(iwp, approve=True)  # a requisition does not change what an estimate says
    assert rig.answer(iwp, estimated_hours=hours).state == "n_a"


def test_an_estimate_and_no_requisition_blocks(rig: Rig) -> None:
    iwp = iwp_of(rig)
    contract(rig, iwp, False)
    got = rig.answer(iwp)
    assert got.state == "blocked" and got.detail == NO_REQUISITION and not got.resolve_via
    rig.raise_one(iwp_of(rig, "IWP-2"), approve=True)  # another package's labour does not count
    assert rig.answer(iwp).state == "blocked"


def test_a_requested_requisition_is_pending(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rid = rig.raise_one(iwp)
    contract(rig, iwp, False)
    got = rig.answer(iwp)
    assert got.state == "pending" and got.detail == NOT_APPROVED
    assert refs(got) == [rid] and got.resolve_via[0].record_type == LABOR
    assert got.resolve_via[0].key == "P123-REQ-LAB-0001"


def test_an_approved_requisition_covering_the_window_is_ok(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rig.raise_one(iwp, approve=True)
    contract(rig, iwp, False)
    got = rig.answer(iwp)
    assert got.state == "ok" and got.detail == COVERED and not got.resolve_via
    wider = rig.answer(iwp, planned_start=date(2026, 11, 5), planned_finish=date(2026, 11, 9))
    assert wider.state == "ok"  # inside the requisition


def test_a_window_the_requisition_does_not_cover_blocks(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rid = rig.raise_one(iwp, approve=True)
    early = rig.answer(iwp, planned_start=date(2026, 11, 1))
    assert early.state == "blocked" and early.detail == NOT_COVERED and refs(early) == [rid]
    late = rig.answer(iwp, planned_finish=date(2026, 11, 14))
    assert late.state == "blocked" and late.detail == NOT_COVERED


def test_without_planned_dates_any_approved_requisition_is_enough(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rig.raise_one(iwp, approve=True)
    assert rig.answer(iwp, planned_start=None, planned_finish=None).state == "ok"
    assert rig.answer(iwp, planned_finish=None).state == "ok"


def test_an_approved_one_beats_a_requested_one_and_a_requested_one_beats_a_gap(rig: Rig) -> None:
    iwp = iwp_of(rig)
    short = rig.raise_one(iwp, approve=True, end_date="2026-11-06")
    asked = rig.raise_one(iwp)
    got = rig.answer(iwp)  # the approved one is too short; the other is still asked for
    assert got.state == "pending" and got.detail == NOT_APPROVED and refs(got) == [asked]
    assert short not in refs(got)
    rig.raise_one(iwp, approve=True)  # now one approved requisition covers the window
    assert rig.answer(iwp).state == "ok"


def test_a_cancelled_or_rejected_requisition_counts_for_nothing(rig: Rig) -> None:
    iwp = iwp_of(rig)
    one, two = rig.raise_one(iwp), rig.raise_one(iwp)
    rig.world.call(
        "uma",
        "CancelRequisition",
        requisition=one,
        expected_version=rig.world.version(one),
        reason="Not needed",
    )
    rig.world.call(
        "sue",
        "RejectRequisition",
        requisition=two,
        expected_version=rig.world.version(two),
        reason="No budget",
    )
    got = rig.answer(iwp)
    assert got.state == "blocked" and got.detail == NO_REQUISITION and not got.resolve_via


def test_a_read_that_fails_is_unknown_with_fixed_text(tmp_path: Path) -> None:
    empty = make_engine(as_target(str(tmp_path / "empty.db")))
    try:
        facts = IwpFacts(
            record_id="01JX", scope=SCOPE, key="IWP-1", status="Issued", estimated_hours=10.0
        )
        with empty.connect() as conn:
            got = labour_requested().evaluate(conn, facts, TODAY)
    finally:
        empty.dispose()
    assert got.state == "unknown" and got.detail == UNKNOWN and not got.resolve_via


def test_the_check_runs_one_statement(rig: Rig) -> None:
    iwp = iwp_of(rig)
    rig.raise_one(iwp, approve=True)
    rig.raise_one(iwp)
    seen: list[str] = []

    def listen(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
        if not statement.lstrip().upper().startswith(("BEGIN", "COMMIT", "ROLLBACK")):
            seen.append(statement)  # the adapter's transaction statements are not reads

    with rig.engine.connect() as conn:
        event.listen(conn, "before_cursor_execute", listen)
        try:
            rig.check.evaluate(conn, rig.facts(iwp), TODAY)
        finally:
            event.remove(conn, "before_cursor_execute", listen)
    assert len(seen) == 1
