"""The RFI log: lines, response times, impact flags, counts, filters, class (P1-I6-T09a)."""

from __future__ import annotations

from typing import Any

from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_correspondence import reports_technical as rt
from tl_mod_correspondence.testing import CONTROLLER, PROJECT, CorrWorld, frozen_today

TODAY = "2026-10-30"


def log(world: CorrWorld, **more: Any) -> rt.RfiLog:
    with open_uow(world.db, readonly=True) as uow:
        return rt.rfi_log(uow.conn(), PROJECT, today=TODAY, **more)


def numbers(found: rt.RfiLog) -> list[str]:
    return [ln.number for ln in found.lines]


def test_an_empty_scope_has_an_empty_log(world: CorrWorld) -> None:
    found = log(world)
    assert (found.scope, found.as_of, found.lines) == (PROJECT, TODAY, [])
    assert (found.total, found.answered, found.open, found.overdue, found.impact_yes) == (0,) * 5
    assert found.average_response_days is None


def test_a_line_carries_the_dates_the_response_time_and_the_flags(world: CorrWorld) -> None:
    world.forge_technical(
        "P123-RFI-0007",
        subject="Beam B12 clashes",
        state="Answered",
        issued_on="2026-10-20",
        discipline="M",
        required_by="2026-10-27",
        potential_cost_impact="yes",
        potential_schedule_impact="no",
    )
    [line] = log(world).lines
    assert (line.number, line.subject, line.subtype, line.discipline) == (
        "P123-RFI-0007",
        "Beam B12 clashes",
        "rfi",
        "M",
    )
    assert (line.state, line.issued_on, line.required_by, line.answered_on) == (
        "Answered",
        "2026-10-20",
        "2026-10-27",
        "2026-10-20",
    )
    assert line.response_days == 0 and line.on_time is True
    assert (line.potential_cost_impact, line.potential_schedule_impact) == ("yes", "no")
    assert (line.cost_impact, line.schedule_impact) == ("yes", "no")
    assert line.confidentiality == "internal" and line.id and len(line.raised_on) == 10


def test_the_judgement_of_the_answer_is_on_the_line(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Accepted")
    world.forge_technical("P123-RFI-0002", state="Rejected")
    world.forge_technical("P123-RFI-0003", state="Answered")
    found = {ln.number: ln.review_decision for ln in log(world).lines}
    assert found == {
        "P123-RFI-0001": "accepted",
        "P123-RFI-0002": "rejected",
        "P123-RFI-0003": None,
    }


def test_the_response_time_counts_calendar_days_from_the_issue_to_the_answer(
    world: CorrWorld,
) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", issued_on="2026-10-12")
    [line] = log(world).lines
    assert line.answered_on == "2026-10-20" and line.response_days == 8


def test_on_time_compares_the_answer_day_with_the_day_it_was_needed(world: CorrWorld) -> None:
    world.forge_technical(
        "P123-RFI-0001", state="Answered", required_by="2026-10-19"
    )  # answered 20
    world.forge_technical("P123-RFI-0002", state="Answered", required_by="2026-10-20")  # the day
    world.forge_technical("P123-RFI-0003", state="Answered", required_by=None)  # no date
    world.forge_technical("P123-RFI-0004", state="Awaiting response", required_by="2026-11-20")
    found = {ln.number: ln.on_time for ln in log(world).lines}
    assert found == {
        "P123-RFI-0001": False,
        "P123-RFI-0002": True,
        "P123-RFI-0003": None,
        "P123-RFI-0004": None,
    }


def test_overdue_means_awaiting_a_response_past_the_day_it_was_needed(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Awaiting response", required_by="2026-10-25")
    world.forge_technical("P123-RFI-0002", state="Awaiting response", required_by=TODAY)
    world.forge_technical("P123-RFI-0003", state="Awaiting response", required_by=None)
    world.forge_technical("P123-RFI-0004", state="Issued", required_by="2026-10-01")
    world.forge_technical("P123-RFI-0005", state="Answered", required_by="2026-10-01")
    by_number = {ln.number: ln for ln in log(world).lines}
    assert by_number["P123-RFI-0001"].overdue and by_number["P123-RFI-0001"].days_overdue == 5
    for number in ("P123-RFI-0002", "P123-RFI-0003", "P123-RFI-0004", "P123-RFI-0005"):
        assert not by_number[number].overdue and by_number[number].days_overdue is None


def test_the_log_is_newest_number_first_and_the_limit_keeps_the_newest(world: CorrWorld) -> None:
    for n in (2, 10, 1):
        world.forge_technical(f"P123-RFI-{n:04d}")
    assert numbers(log(world)) == ["P123-RFI-0010", "P123-RFI-0002", "P123-RFI-0001"]
    assert numbers(log(world, limit=1)) == ["P123-RFI-0010"]


def test_the_counts_follow_the_lines(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", issued_on="2026-10-10")
    world.forge_technical("P123-RFI-0002", state="Accepted", issued_on="2026-10-16")
    world.forge_technical("P123-RFI-0003", state="Awaiting response", required_by="2026-10-01")
    world.forge_technical("P123-RFI-0004", state="Draft")
    found = log(world)
    assert (found.total, found.answered, found.open, found.overdue) == (4, 2, 2, 1)
    assert found.impact_yes == 2  # both answers said yes to cost
    assert found.average_response_days == 7.0  # (10 + 4) / 2
    assert log(world, subtype="tq").total == 0


def test_a_same_day_answer_counts_as_a_zero_in_the_average(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", issued_on="2026-10-20")  # 0 days
    world.forge_technical("P123-RFI-0002", state="Answered", issued_on="2026-10-16")  # 4 days
    assert log(world).average_response_days == 2.0


def test_the_averages_are_rounded_to_one_place(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", issued_on="2026-10-17")  # 3 days
    world.forge_technical("P123-RFI-0002", state="Answered", issued_on="2026-10-16")  # 4
    world.forge_technical("P123-RFI-0003", state="Answered", issued_on="2026-10-12")  # 8
    assert log(world).average_response_days == 5.0
    world.forge_technical("P123-RFI-0004", state="Answered", issued_on="2026-10-13")  # 7
    assert log(world).average_response_days == 5.5
    world.forge_technical("P123-RFI-0005", state="Answered", issued_on="2026-10-15")  # 5
    assert log(world).average_response_days == 5.4  # 27 / 5 = 5.4


def test_the_filters(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", discipline="M")
    world.forge_technical(
        "P123-RFI-0002", state="Awaiting response", discipline="E", required_by="2026-10-01"
    )
    world.forge_technical("P123-TQ-0001", state="Draft", subtype="tq", discipline="M")
    world.forge_technical("P123-DEV-0001", state="Answered", subtype="deviation", discipline="C")
    assert numbers(log(world, subtype="tq")) == ["P123-TQ-0001"]
    assert sorted(numbers(log(world, state="Answered"))) == ["P123-DEV-0001", "P123-RFI-0001"]
    assert sorted(numbers(log(world, discipline="M"))) == ["P123-RFI-0001", "P123-TQ-0001"]
    assert sorted(numbers(log(world, only_open=True))) == ["P123-RFI-0002", "P123-TQ-0001"]
    assert numbers(log(world, only_overdue=True)) == ["P123-RFI-0002"]
    assert sorted(numbers(log(world, only_impact=True))) == ["P123-DEV-0001", "P123-RFI-0001"]


def test_only_open_leaves_out_an_item_that_was_closed_unanswered(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Closed")
    world.forge_technical("P123-RFI-0002", state="Awaiting response")
    assert numbers(log(world, only_open=True)) == ["P123-RFI-0002"]
    assert log(world).open == 1  # the count follows the same rule


def test_only_impact_keeps_an_answer_that_says_yes_to_either_question(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered", answer={"cost_impact": "no"})
    world.forge_technical(
        "P123-RFI-0002", state="Answered", answer={"cost_impact": "no", "schedule_impact": "yes"}
    )
    world.forge_technical(
        "P123-RFI-0003", state="Answered", answer={"cost_impact": "no", "schedule_impact": "no"}
    )
    world.forge_technical("P123-RFI-0004", state="Answered")  # cost yes
    assert sorted(numbers(log(world, only_impact=True))) == ["P123-RFI-0002", "P123-RFI-0004"]
    assert log(world).impact_yes == 2


def test_a_voided_item_is_not_in_the_log(world: CorrWorld) -> None:
    gone = world.forge_technical("P123-RFI-0001", state="Draft")
    world.forge_technical("P123-RFI-0002", state="Draft")
    with frozen_today("2026-10-20"):
        world.void_draft(gone)
    assert numbers(log(world)) == ["P123-RFI-0002"]


def test_another_project_is_not_in_the_log(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001")
    world.forge_technical("P999-RFI-0001", scope="project:P999")
    assert numbers(log(world)) == ["P123-RFI-0001"]


def test_an_item_the_viewer_may_not_read_is_neither_a_line_nor_counted(world: CorrWorld) -> None:
    world.forge_technical("P123-RFI-0001", state="Answered")
    world.forge_technical("P123-RFI-0002", state="Answered", confidentiality="restricted")
    world.forge_technical("P123-RFI-0003", state="Answered", confidentiality="privileged")
    world.forge_technical("P123-RFI-0004", state="Answered", confidentiality="Secret")  # no class
    plain = log(world)
    assert numbers(plain) == ["P123-RFI-0001"]
    assert (plain.total, plain.answered, plain.impact_yes) == (1, 1, 1)
    with cf.use_viewer(CONTROLLER):
        boss = log(world)
    assert numbers(boss) == ["P123-RFI-0002", "P123-RFI-0001"]
    assert boss.total == 2
    agent = cf.Viewer(actor="agent:bot", level=0, account="")
    with cf.use_viewer(agent):
        assert numbers(log(world)) == ["P123-RFI-0001"]
