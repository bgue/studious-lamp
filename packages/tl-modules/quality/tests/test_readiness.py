"""The readiness check ``inspections_planned`` (P2-INSP-S3). Every inspection is made by the real
commands of ``insp_world``; ``today`` is the only clock."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from importlib.metadata import entry_points

import pytest
from insp_world import IWP, SCOPE, InspWorld, answers
from sqlalchemy import Engine
from tl_adapters.db import make_engine, open_uow
from tl_core.readiness import (
    READINESS_ENTRY_POINT,
    CheckResult,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_mod_quality.checks import InspectionsPlanned

TODAY = date(2026, 11, 20)
LATE_START = date(2026, 12, 5)  # after the 2026-12-01 the world schedules for
EARLY_START = date(2026, 11, 30)  # before it
SETTING = "quality.inspections.required_for_iwp"
RECORD_TYPES = frozenset({"awp.IWP", "quality.Inspection"})
TITLE = "Flange make-up"


@pytest.fixture
def engine(insp: InspWorld) -> Iterator[Engine]:
    found = make_engine(insp.db)
    yield found
    found.dispose()


def facts(iwp: str, start: date | None = None) -> IwpFacts:
    return IwpFacts(
        record_id=iwp, scope=SCOPE, key="P123-IWP-0001", status="Issued", planned_start=start
    )


def answer(insp: InspWorld, engine: Engine, iwp: str, start: date | None = None) -> CheckResult:
    with engine.connect() as conn:
        return InspectionsPlanned().evaluate(conn, facts(iwp, start), TODAY)


def require(insp: InspWorld) -> None:
    with open_uow(insp.db) as uow:
        handle_change_setting(
            uow,
            ChangeSetting(
                actor="user:ada",
                source="test",
                scope=SCOPE,
                key=SETTING,
                layer=SCOPE,
                value=True,
                reason="test",
                accept_risk=True,
            ),
        )


def iwp_of(insp: InspWorld) -> str:
    return insp.record(IWP, "IWP-0001")


def test_none_with_the_setting_off_is_n_a_and_on_is_blocked(
    insp: InspWorld, engine: Engine
) -> None:
    iwp = iwp_of(insp)
    off = answer(insp, engine, iwp)
    assert (off.state, off.count_ok, off.count_total, off.resolve_via) == ("n_a", None, None, [])
    require(insp)
    on = answer(insp, engine, iwp)
    assert (on.state, on.resolve_via) == ("blocked", [])


def test_a_cancelled_inspection_counts_in_neither(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    gone = insp.plan(iwp)
    insp.call("sue", "CancelInspection", inspection=gone, reason="not needed")
    assert answer(insp, engine, iwp).state == "n_a"
    keep = insp.scheduled(iwp)
    found = answer(insp, engine, iwp)
    assert (found.state, found.count_ok, found.count_total) == ("ok", 1, 1)
    assert [r.record_id for r in found.resolve_via] == []
    assert keep != gone


def test_a_planned_inspection_blocks_and_is_named(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    insp.scheduled(iwp)
    planned = insp.plan(iwp, point="witness")
    found = answer(insp, engine, iwp)
    assert found.state == "blocked"
    assert [r.record_id for r in found.resolve_via] == [planned]
    assert found.resolve_via[0].record_type == "quality.Inspection"
    assert (found.count_ok, found.count_total) == (1, 2)


def test_a_rejected_hold_point_blocks_until_it_is_reinspected(
    insp: InspWorld, engine: Engine
) -> None:
    iwp = iwp_of(insp)
    item = insp.scheduled(iwp, point="hold")
    insp.recorded(item, answers=answers(q1="no"))
    assert insp.inspection_row(item)["result"] == "reject"
    found = answer(insp, engine, iwp)
    assert found.state == "blocked"
    assert [r.record_id for r in found.resolve_via] == [item]
    again = insp.call("uma", "ReinspectInspection", inspection=item).stream_id
    insp.call(
        "uma",
        "ScheduleInspection",
        inspection=again,
        checklist=insp.checklist(),
        scheduled_for="2026-12-01",
        inspector="M. Okafor",
    )
    assert answer(insp, engine, iwp, EARLY_START).state != "blocked"
    assert answer(insp, engine, iwp, EARLY_START).state == "ok"


def test_a_rejected_witness_point_does_not_block(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    item = insp.scheduled(iwp, point="witness")
    insp.recorded(item, answers=answers(q1="no"))
    assert answer(insp, engine, iwp).state == "ok"


def test_pending_ok_and_the_counts(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    first = insp.scheduled(iwp)
    done = insp.scheduled(iwp, point="witness")
    insp.recorded(done, answers=answers())
    pending = answer(insp, engine, iwp, LATE_START)
    assert pending.state == "pending"
    assert [r.record_id for r in pending.resolve_via] == [first]
    assert (pending.count_ok, pending.count_total) == (2, 2)
    ok = answer(insp, engine, iwp, EARLY_START)
    assert (ok.state, ok.count_ok, ok.count_total) == ("ok", 2, 2)
    assert answer(insp, engine, iwp).state == "ok"  # no planned start: nothing is late
    insp.recorded(first, answers=answers())
    assert answer(insp, engine, iwp, LATE_START).state == "ok"  # everything is Done


def test_an_unreleased_hold_point_on_an_issued_iwp_stays_ok(
    insp: InspWorld, engine: Engine
) -> None:
    iwp = iwp_of(insp)
    insp.scheduled(iwp, point="hold")
    found = answer(insp, engine, iwp, EARLY_START)
    assert (found.state, found.resolve_via) == ("ok", [])


def test_the_contract_and_the_registry(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    check = load_checks()["inspections_planned"]
    assert isinstance(check, InspectionsPlanned)
    assert check.watches == {"quality.Inspection"}
    empty = ContractWorld(engine.connect, facts(iwp), TODAY, RECORD_TYPES, True)
    check_readiness_contract(check, empty)
    insp.scheduled(iwp)
    insp.plan(iwp)
    busy = ContractWorld(engine.connect, facts(iwp, LATE_START), TODAY, RECORD_TYPES)
    check_readiness_contract(check, busy)
    named = [
        e for e in entry_points(group=READINESS_ENTRY_POINT) if e.name == "inspections_planned"
    ]
    assert len(named) == 1 and named[0].value.startswith("tl_mod_quality.checks")


def test_the_detail_holds_no_title(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    insp.scheduled(iwp, title=TITLE)
    insp.plan(iwp, title=TITLE)
    found = answer(insp, engine, iwp, LATE_START)
    assert found.state == "blocked"
    assert TITLE not in found.detail and "Flange" not in found.detail


def test_a_failed_read_is_unknown(new_engine: Callable[[], Engine]) -> None:
    empty = new_engine()  # no tables: the read fails
    with empty.connect() as conn:
        found = InspectionsPlanned().evaluate(conn, facts("r1"), TODAY)
    assert found.state == "unknown" and found.detail


def test_a_start_on_the_scheduled_day_is_not_late(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    insp.scheduled(iwp)
    assert answer(insp, engine, iwp, date(2026, 12, 1)).state == "ok"
    assert answer(insp, engine, iwp, date(2026, 12, 2)).state == "pending"


def test_a_conditional_hold_point_does_not_block(insp: InspWorld, engine: Engine) -> None:
    iwp = iwp_of(insp)
    item = insp.scheduled(iwp, point="hold")
    insp.recorded(item, answers=answers(q2="no"))
    assert insp.inspection_row(item)["result"] == "conditional"
    assert answer(insp, engine, iwp).state == "ok"
