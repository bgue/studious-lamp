"""The whole life of an RFI and of the Commercial item it leads to (P1-I6 supervisor flow test).

One test per leg, on both adapters: raise, submit, issue, answer with a cost impact, escalate,
review, issue the notice, assess, close. The per-command rules are in the tests of each command.
"""

from __future__ import annotations

from typing import Any

from tl_core import confidentiality as cf
from tl_mod_correspondence import constraints
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, as_controller, frozen_today

MONDAY = "2026-10-19"


def test_an_rfi_is_raised_issued_answered_and_escalated(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by="2026-11-02")
        assert made.key == "P123-RFI-0001"
        world.submit_technical(made.stream_id)
        with cf.use_viewer(CONTROLLER):
            world.issue_technical(made.stream_id)
    row = world.technical("P123-RFI-0001")
    assert row.item.state == "Awaiting response"
    assert row.item.issued_on == MONDAY and row.item.delivery == "stub"
    [clock] = world.clocks("P123-RFI-0001")
    assert (clock.kind, clock.start_on, clock.due_on) == (
        "response_from_them",
        MONDAY,
        "2026-11-02",
    )
    with frozen_today("2026-10-22"):
        world.answer_technical(made.stream_id, cost_impact="yes", schedule_impact="no")
    answered = world.technical("P123-RFI-0001")
    assert answered.item.state == "Answered" and answered.data.answered_on == "2026-10-22"
    assert answered.item.responded_on == "2026-10-22"
    [met] = world.clocks("P123-RFI-0001")
    assert met.state == "met" and met.closed_on == "2026-10-22"
    with frozen_today("2026-10-22"), as_controller():
        escalated = world.escalate(made.stream_id)
        assert escalated.key is not None
        warning = world.commercial(escalated.key)
    assert escalated.key == "P123-EW-0001"
    assert warning.item.state == "Draft" and warning.item.confidentiality == "restricted"
    assert warning.data.derived_from_id == made.stream_id
    assert warning.data.aware_on == "2026-10-22"
    with as_controller():
        [bar] = world.clocks("P123-EW-0001")
    assert (bar.kind, bar.start_on, bar.due_on, bar.day_type) == (
        "time_bar",
        "2026-10-22",
        "2026-11-05",
        "calendar",
    )


def test_a_commercial_item_goes_from_draft_to_closed(world: CorrWorld) -> None:
    with frozen_today(MONDAY), as_controller():
        made = world.raise_commercial(estimated_value="12500", currency="USD")
        assert made.key == "P123-EW-0001"
        assert world.commercial(made.key).data.estimated_value == "12500.00"
        world.submit_commercial(made.stream_id)
        world.review_commercial(made.stream_id)
        world.issue_commercial(made.stream_id)
        issued = world.commercial(made.key)
        assert issued.item.state == "Awaiting assessment"
        bar, wait = world.clocks(made.key)
        assert (bar.kind, bar.state, bar.closed_on) == ("time_bar", "met", MONDAY)
        assert (wait.kind, wait.state) == ("response_from_them", "running")
    with frozen_today("2026-11-02"), as_controller():
        world.assess_commercial(made.stream_id, "partially_agreed", assessed_value="9000")
        assessed = world.commercial(made.key)
        assert assessed.item.state == "Partially agreed"
        assert assessed.data.assessed_value == "9000.00"
        assert world.clocks(made.key)[1].state == "met"
        world.close_commercial(made.stream_id)
        assert world.commercial(made.key).item.state == "Closed"


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str | None]] = []

    def rfi_issued(self, uow: object, item: Any, data: Any) -> None:
        self.calls.append(("issued", item.number, item.state, data.answered_on))

    def rfi_answered(self, uow: object, item: Any, data: Any) -> None:
        self.calls.append(("answered", item.number, item.state, data.answered_on))


def test_the_constraint_hook_hears_of_an_rfi_when_it_is_issued_and_when_it_is_answered(
    world: CorrWorld,
) -> None:
    recorder = _Recorder()
    with constraints.use_sink(recorder), frozen_today(MONDAY):
        made = world.raise_technical(required_by="2026-11-02")
        world.submit_technical(made.stream_id)
        assert recorder.calls == []
        with cf.use_viewer(CONTROLLER):
            world.issue_technical(made.stream_id)
        world.answer_technical(made.stream_id)
    assert recorder.calls == [
        ("issued", "P123-RFI-0001", "Awaiting response", None),
        ("answered", "P123-RFI-0001", "Answered", MONDAY),
    ]


def test_without_a_sink_the_hook_does_nothing(world: CorrWorld) -> None:
    assert isinstance(constraints.current(), constraints.NullSink)
    with frozen_today(MONDAY):
        made = world.raise_technical(required_by="2026-11-02")
        world.submit_technical(made.stream_id)
        with cf.use_viewer(CONTROLLER):
            world.issue_technical(made.stream_id)
    assert world.technical("P123-RFI-0001").item.state == "Awaiting response"
