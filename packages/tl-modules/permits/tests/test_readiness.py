"""The readiness check ``permits_planned`` (P2-PTW-S4). Permits are made by the real commands of
``permit_world``; ``today`` is the only clock the check sees."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from importlib.metadata import entry_points

import pytest
from permit_world import IWP, SCOPE, World
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
from tl_mod_permits import views
from tl_mod_permits.checks import PermitsPlanned

# The world issues at 07:00 on 2026-12-01 and the general permit runs to the 18:00 shift end.
DAY = date(2026, 12, 1)
NEXT_DAY = date(2026, 12, 2)
SETTING = "permits.required_for_iwp"
RECORD_TYPES = frozenset({"awp.IWP", "permits.Permit"})
DESCRIPTION = "Weld repair, rack 12"
HOLDER = "Rob"


@pytest.fixture
def engine(world: World) -> Iterator[Engine]:
    found = make_engine(world.db)
    yield found
    found.dispose()


def facts(iwp: str) -> IwpFacts:
    return IwpFacts(record_id=iwp, scope=SCOPE, key="P123-IWP-0001", status="Issued")


def answer(engine: Engine, iwp: str, today: date = DAY) -> CheckResult:
    with engine.connect() as conn:
        return PermitsPlanned().evaluate(conn, facts(iwp), today)


def require(world: World) -> None:
    with open_uow(world.db) as uow:
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


def iwp_of(world: World) -> str:
    return world.record(IWP, "IWP-0001")


def for_iwp(world: World, iwp: str, kind: str = "general", state: str = "requested") -> str:
    """A permit of ``kind`` for the IWP, taken to ``state`` (requested, approved, active)."""
    if state == "requested":
        return world.request(permit_type=kind, for_record_id=iwp)
    if state == "approved":
        return world.approved(kind, for_record_id=iwp)
    return world.active(kind, for_record_id=iwp)


def test_none_with_the_setting_off_is_n_a_and_on_is_blocked(world: World, engine: Engine) -> None:
    iwp = iwp_of(world)
    off = answer(engine, iwp)
    assert (off.state, off.count_ok, off.count_total, off.resolve_via) == ("n_a", None, None, [])
    require(world)
    on = answer(engine, iwp)
    assert (on.state, on.resolve_via) == ("blocked", [])


def test_a_requested_permit_is_pending_and_approved_or_active_is_ok(
    world: World, engine: Engine
) -> None:
    iwp = iwp_of(world)
    asked = for_iwp(world, iwp)
    found = answer(engine, iwp)
    assert (found.state, found.count_ok, found.count_total) == ("pending", 0, 1)
    assert [r.record_id for r in found.resolve_via] == [asked]
    world.call("sue", "ApprovePermit", permit=asked)
    approved = answer(engine, iwp)
    assert (approved.state, approved.count_ok, approved.count_total) == ("ok", 1, 1)
    world.issue(asked)
    active = answer(engine, iwp)
    assert (active.state, active.count_ok, active.count_total) == ("ok", 1, 1)
    assert active.resolve_via == []


def test_cancelled_closed_and_rejected_count_in_neither(world: World, engine: Engine) -> None:
    iwp = iwp_of(world)
    live = for_iwp(world, iwp, "general", "approved")
    cancelled = for_iwp(world, iwp, "hot_work")
    world.call("pam", "CancelPermit", permit=cancelled, reason="Moved")
    ended = for_iwp(world, iwp, "general", "active")
    world.call("rob", "HandBackPermit", permit=ended, handback_note="Site clear")
    world.call("pam", "ClosePermit", permit=ended)
    refused = for_iwp(world, iwp, "excavation")
    world.call("sue", "RejectPermit", permit=refused, reason="No")
    # the refused excavation has no live permit of its type: that alone blocks
    blocked = answer(engine, iwp)
    assert blocked.state == "blocked"
    assert [r.record_id for r in blocked.resolve_via] == [refused]
    assert (blocked.count_ok, blocked.count_total) == (1, 1)
    again = for_iwp(world, iwp, "excavation", "approved")
    found = answer(engine, iwp)
    assert (found.state, found.count_ok, found.count_total) == ("ok", 2, 2)
    assert live != again


def test_a_rejected_suspended_or_lapsed_permit_blocks_without_another_live_one(
    world: World, engine: Engine
) -> None:
    iwp = iwp_of(world)
    rejected = for_iwp(world, iwp, "hot_work")
    world.call("sue", "RejectPermit", permit=rejected, reason="No")
    found = answer(engine, iwp)
    assert (found.state, [r.record_id for r in found.resolve_via]) == ("blocked", [rejected])
    suspended = for_iwp(world, iwp, "general", "active")
    world.call("uma", "SuspendPermit", permit=suspended, reason="Stop")
    found = answer(engine, iwp)
    assert found.state == "blocked"
    assert {r.record_id for r in found.resolve_via} == {rejected, suspended}
    assert found.resolve_via[0].record_type == "permits.Permit"


def test_a_lapsed_permit_blocks_and_another_live_one_of_its_type_unblocks(
    world: World, engine: Engine
) -> None:
    iwp = iwp_of(world)
    old = for_iwp(world, iwp, "general", "active")
    assert answer(engine, iwp, DAY).state == "ok"
    lapsed = answer(engine, iwp, NEXT_DAY)
    assert (lapsed.state, [r.record_id for r in lapsed.resolve_via]) == ("blocked", [old])
    for_iwp(world, iwp, "hot_work", "approved")
    assert answer(engine, iwp, NEXT_DAY).state == "blocked"
    fresh = for_iwp(world, iwp, "general", "approved")
    found = answer(engine, iwp, NEXT_DAY)
    assert found.state == "pending"  # the lapsed one is counted and not in force
    assert found.resolve_via and found.resolve_via[0].record_id == old
    assert fresh != old


def test_a_suspended_permit_with_another_live_one_is_not_blocked(
    world: World, engine: Engine
) -> None:
    iwp = iwp_of(world)
    suspended = for_iwp(world, iwp, "general", "active")
    world.call("uma", "SuspendPermit", permit=suspended, reason="Stop")
    for_iwp(world, iwp, "general", "approved")
    found = answer(engine, iwp)
    assert found.state != "blocked"
    assert (found.count_ok, found.count_total) == (1, 2)


def test_a_lapsed_permit_is_not_ok_and_agrees_with_permit_detail(
    world: World, engine: Engine
) -> None:
    iwp = iwp_of(world)
    permit = for_iwp(world, iwp, "general", "active")
    assert world.state(permit) == "Active"  # stored Active
    for today, shown in ((DAY, "Active"), (NEXT_DAY, "Lapsed")):
        now = datetime.combine(today, time.min, tzinfo=UTC)
        with engine.connect() as conn:
            number = str(
                conn.exec_driver_sql(
                    f"SELECT key FROM cur_core_record WHERE id = '{permit}'"
                ).scalar()
            )
            detail = views.permit_detail(conn, SCOPE, number, now=now)
        assert detail is not None and detail.row.state == shown
        found = answer(engine, iwp, today)
        assert (found.state == "ok") == (shown == "Active")
    assert answer(engine, iwp, NEXT_DAY).state != "ok"


def test_the_contract_the_registry_and_a_detail_without_text(world: World, engine: Engine) -> None:
    iwp = iwp_of(world)
    check = load_checks()["permits_planned"]
    assert isinstance(check, PermitsPlanned)
    assert check.watches == {"permits.Permit"}
    check_readiness_contract(
        check, ContractWorld(engine.connect, facts(iwp), DAY, RECORD_TYPES, True)
    )
    for_iwp(world, iwp, "general", "approved")
    for_iwp(world, iwp)
    check_readiness_contract(check, ContractWorld(engine.connect, facts(iwp), DAY, RECORD_TYPES))
    named = [e for e in entry_points(group=READINESS_ENTRY_POINT) if e.name == "permits_planned"]
    assert len(named) == 1 and named[0].value.startswith("tl_mod_permits.checks")
    found = answer(engine, iwp)
    assert DESCRIPTION not in found.detail and HOLDER not in found.detail
    assert "Weld" not in found.detail and "Pump" not in found.detail
