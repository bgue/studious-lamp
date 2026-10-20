"""The Commercial register: values, variance, totals by currency, time bars, class (P1-I6-T09b)."""

from __future__ import annotations

from typing import Any

from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_correspondence import reports_commercial as rc
from tl_mod_correspondence.testing import (
    CONTROLLER,
    PROJECT,
    CorrWorld,
    as_controller,
    frozen_today,
)

TODAY = "2026-10-30"


def register(world: CorrWorld, **more: Any) -> rc.CommercialRegister:
    with cf.use_viewer(CONTROLLER), open_uow(world.db, readonly=True) as uow:
        return rc.commercial_register(uow.conn(), PROJECT, today=TODAY, **more)


def numbers(found: rc.CommercialRegister) -> list[str]:
    return [ln.number for ln in found.lines]


def bar(world: CorrWorld, item_id: str, *, start: str, days: int = 14, **more: Any) -> str:
    """A time-bar clock on the item, started on ``start``."""
    with as_controller(), frozen_today(start):
        return world.start_clock(
            item_id, label="Time bar", kind="time_bar", duration_days=days, start_on=start, **more
        ).stream_id


def test_an_empty_scope_has_an_empty_register(world: CorrWorld) -> None:
    found = register(world)
    assert (found.scope, found.as_of, found.lines, found.totals) == (PROJECT, TODAY, [], [])
    assert (found.time_bars_running, found.time_bars_late) == (0, 0)


def test_a_line_carries_the_values_the_clause_and_the_assessment(world: CorrWorld) -> None:
    clause = world.clause("CT-1", "20.1")
    world.forge_commercial(
        "P123-CN-0003",
        subject="Change: re-routing",
        subtype="change_notice",
        state="Agreed",
        issued_on="2026-10-21",
        contract_clause_id=clause.stream_id,
        aware_on="2026-10-19",
        estimated_value="12500.00",
        assessed_value="9000.00",
        schedule_impact_days=3,
        currency="USD",
    )
    [line] = register(world).lines
    assert (line.number, line.subject, line.subtype, line.state, line.direction) == (
        "P123-CN-0003",
        "Change: re-routing",
        "change_notice",
        "Agreed",
        "out",
    )
    assert (line.clause, line.aware_on, line.issued_on) == ("CT-1/20.1", "2026-10-19", "2026-10-21")
    assert (line.currency, line.estimated_value, line.assessed_value) == (
        "USD",
        "12500.00",
        "9000.00",
    )
    assert line.variance == "-3500.00" and line.assessment_status == "agreed"
    assert line.schedule_impact_days == 3 and line.confidentiality == "restricted"
    assert line.derived_from is None and line.time_bar_due is None and line.time_bar_state is None
    assert line.time_bar_late is False


def test_the_variance_is_the_assessed_value_minus_the_estimate_to_the_cent(
    world: CorrWorld,
) -> None:
    world.forge_commercial(
        "P123-CN-0001",
        state="Partially agreed",
        estimated_value="0.10",
        assessment={"assessed_value": "0.30"},
    )
    [line] = register(world).lines
    assert (line.estimated_value, line.assessed_value, line.variance) == ("0.10", "0.30", "0.20")
    assert line.assessment_status == "partially_agreed"


def test_a_missing_figure_leaves_the_variance_empty(world: CorrWorld) -> None:
    world.forge_commercial("P123-CN-0001", estimated_value=None, currency=None)
    [line] = register(world).lines
    assert (line.estimated_value, line.assessed_value, line.variance) == (None, None, None)


def test_totals_are_per_currency_and_exact(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", estimated_value="0.10", currency="USD")
    world.forge_commercial("P123-EW-0002", estimated_value="0.20", currency="USD")
    world.forge_commercial("P123-EW-0003", estimated_value="1000.00", currency="EUR")
    world.forge_commercial("P123-EW-0004", estimated_value=None, currency=None)
    totals = register(world).totals
    assert [(t.currency, t.count, t.estimated, t.assessed) for t in totals] == [
        ("EUR", 1, "1000.00", "0.00"),
        ("USD", 2, "0.30", "0.00"),
    ]


def test_the_assessed_total_counts_the_items_that_were_assessed(world: CorrWorld) -> None:
    world.forge_commercial(
        "P123-CN-0001",
        state="Agreed",
        estimated_value="500.00",
        assessment={"assessed_value": "450.50"},
    )
    world.forge_commercial("P123-CN-0002", state="Awaiting assessment", estimated_value="700.00")
    [total] = register(world).totals
    assert (total.count, total.estimated, total.assessed) == (2, "1200.00", "450.50")


def test_the_time_bar_shows_its_due_day_and_the_days_left(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001")
    bar(world, item, start="2026-10-24", days=14)  # due 2026-11-07
    [line] = register(world).lines
    assert (line.time_bar_due, line.time_bar_state, line.time_bar_days_left) == (
        "2026-11-07",
        "running",
        8,
    )
    assert line.time_bar_late is False
    found = register(world)
    assert (found.time_bars_running, found.time_bars_late) == (1, 0)


def test_a_time_bar_past_its_day_is_expired_and_late(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001")
    bar(world, item, start="2026-10-01", days=14)  # due 2026-10-15
    [line] = register(world).lines
    assert (line.time_bar_state, line.time_bar_late) == ("expired", True)
    assert line.time_bar_days_left == -15
    found = register(world)
    assert (found.time_bars_running, found.time_bars_late) == (0, 1)


def test_a_time_bar_met_in_time_is_not_late_and_one_met_after_its_day_is(world: CorrWorld) -> None:
    on_time = world.forge_commercial("P123-EW-0001")
    late = world.forge_commercial("P123-EW-0002")
    first = bar(world, on_time, start="2026-10-01", days=14)  # due 2026-10-15
    second = bar(world, late, start="2026-10-01", days=14)
    with as_controller(), frozen_today("2026-10-14"):
        world.meet(first, on="2026-10-14")
    with as_controller(), frozen_today("2026-10-20"):
        world.meet(second, on="2026-10-20")
    lines = {ln.number: ln for ln in register(world).lines}
    assert (lines["P123-EW-0001"].time_bar_state, lines["P123-EW-0001"].time_bar_late) == (
        "met",
        False,
    )
    assert (lines["P123-EW-0002"].time_bar_state, lines["P123-EW-0002"].time_bar_late) == (
        "met",
        True,
    )
    found = register(world)
    assert (found.time_bars_running, found.time_bars_late) == (0, 1)


def test_only_the_clocks_of_kind_time_bar_are_the_time_bar(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001")
    with as_controller(), frozen_today("2026-10-24"):
        world.start_clock(item, label="Assessment expected", kind="response_from_them")
    [line] = register(world).lines
    assert (line.time_bar_due, line.time_bar_state) == (None, None)


def test_a_derived_item_names_the_rfi_it_came_from(world: CorrWorld) -> None:
    rfi = world.forge_technical("P123-RFI-0001", state="Answered")
    world.forge_commercial("P123-EW-0001", derived_from_id=rfi)
    [line] = register(world).lines
    assert line.derived_from == "P123-RFI-0001"


def test_a_source_the_viewer_may_not_read_is_not_named(world: CorrWorld) -> None:
    secret = world.forge_technical("P123-RFI-0001", state="Answered", confidentiality="privileged")
    world.forge_commercial("P123-EW-0001", derived_from_id=secret)
    assert register(world).lines[0].derived_from is None


def test_the_filters(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", subtype="early_warning", state="Draft")
    world.forge_commercial("P123-CN-0001", subtype="change_notice", state="Agreed")
    live = world.forge_commercial(
        "P123-CL-0001", subtype="claim_notice", state="Awaiting assessment"
    )
    bar(world, live, start="2026-10-24")
    assert numbers(register(world, subtype="change_notice")) == ["P123-CN-0001"]
    assert numbers(register(world, state="Draft")) == ["P123-EW-0001"]
    assert numbers(register(world, time_bars_only=True)) == ["P123-CL-0001"]
    assert numbers(register(world)) == ["P123-EW-0001", "P123-CN-0001", "P123-CL-0001"]


def test_a_time_bar_met_on_its_due_day_is_in_time(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001")
    clock = bar(world, item, start="2026-10-01", days=14)  # due 2026-10-15
    with as_controller(), frozen_today("2026-10-15"):
        world.meet(clock, on="2026-10-15")
    [line] = register(world).lines
    assert (line.time_bar_state, line.time_bar_late) == ("met", False)


def test_a_paused_time_bar_still_counts_as_running(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001")
    clock = bar(world, item, start="2026-10-24", days=14)
    with as_controller(), frozen_today("2026-10-26"):
        world.pause(clock, on="2026-10-26")
    found = register(world)
    assert [ln.time_bar_state for ln in found.lines] == ["paused"]
    assert found.time_bars_running == 1
    assert numbers(register(world, time_bars_only=True)) == ["P123-EW-0001"]


def test_time_bars_only_keeps_a_late_bar_and_leaves_out_one_met_in_time(world: CorrWorld) -> None:
    expired = world.forge_commercial("P123-EW-0001")
    met_late = world.forge_commercial("P123-EW-0002")
    met_in_time = world.forge_commercial("P123-EW-0003")
    world.forge_commercial("P123-EW-0004")  # no clock at all
    bar(world, expired, start="2026-10-01", days=14)  # due 10-15, nobody answered
    late = bar(world, met_late, start="2026-10-01", days=14)
    ok = bar(world, met_in_time, start="2026-10-01", days=14)
    with as_controller(), frozen_today("2026-10-20"):
        world.meet(late, on="2026-10-20")
    with as_controller(), frozen_today("2026-10-10"):
        world.meet(ok, on="2026-10-10")
    assert sorted(numbers(register(world, time_bars_only=True))) == ["P123-EW-0001", "P123-EW-0002"]


def test_an_assessment_without_an_estimate_has_no_variance(world: CorrWorld) -> None:
    world.forge_commercial("P123-CN-0001", state="Agreed", estimated_value=None)
    [line] = register(world).lines
    assert (line.estimated_value, line.assessed_value, line.variance) == (None, "9000.00", None)


def test_an_instruction_we_received_reads_as_incoming(world: CorrWorld) -> None:
    world.forge_commercial(
        "P123-SI-0001",
        subtype="site_instruction",
        state="Awaiting assessment",
        item={"direction": "in"},
    )
    [line] = register(world).lines
    assert (line.subtype, line.direction) == ("site_instruction", "in")


def test_only_open_leaves_out_void_and_closed_items(world: CorrWorld) -> None:
    gone = world.forge_commercial("P123-EW-0001", state="Draft")
    world.forge_commercial("P123-EW-0002", state="Draft")
    with as_controller(), frozen_today("2026-10-20"):
        world.void_draft(gone)
    world.forge_commercial("P123-EW-0003", state="Closed")
    assert numbers(register(world)) == ["P123-EW-0003", "P123-EW-0002"]
    assert numbers(register(world, only_open=True)) == ["P123-EW-0002"]


def test_the_register_is_newest_number_first_and_the_limit_keeps_the_newest(
    world: CorrWorld,
) -> None:
    for n in (2, 10, 1):
        world.forge_commercial(f"P123-EW-{n:04d}")
    assert numbers(register(world)) == ["P123-EW-0010", "P123-EW-0002", "P123-EW-0001"]
    assert numbers(register(world, limit=1)) == ["P123-EW-0010"]


def test_commercial_items_are_restricted_so_a_plain_viewer_has_an_empty_register(
    world: CorrWorld,
) -> None:
    world.forge_commercial("P123-EW-0001", estimated_value="900.00")
    world.forge_commercial("P123-EW-0002", confidentiality="internal", estimated_value="100.00")
    world.forge_commercial("P123-EW-0003", confidentiality="privileged")
    world.forge_commercial("P123-EW-0004", confidentiality="Secret")
    with open_uow(world.db, readonly=True) as uow:
        plain = rc.commercial_register(uow.conn(), PROJECT, today=TODAY)
    assert numbers(plain) == ["P123-EW-0002"]
    assert [(t.count, t.estimated) for t in plain.totals] == [(1, "100.00")]
    assert numbers(register(world)) == ["P123-EW-0002", "P123-EW-0001"]
    agent = cf.Viewer(actor="agent:bot", level=0, account="")
    with cf.use_viewer(agent), open_uow(world.db, readonly=True) as uow:
        assert numbers(rc.commercial_register(uow.conn(), PROJECT, today=TODAY)) == ["P123-EW-0002"]


def test_another_project_is_not_in_the_register(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001")
    world.forge_commercial("P999-EW-0001", scope="project:P999")
    assert numbers(register(world)) == ["P123-EW-0001"]
