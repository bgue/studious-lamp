"""S1: the pure rules of the scaffold module (tag colour, next due, due state, dismantle check).

Copied byte-identical to packages/tl-modules/scaffold/tests/test_rules.py. No database: the
rules take values and return values, so the handlers, the job and the readiness check share them.
"""

from __future__ import annotations

from datetime import date

import pytest
from tl_mod_scaffold import rules


def test_a_result_gives_one_tag_colour() -> None:
    assert rules.tag_for("pass") == "green"
    assert rules.tag_for("conditional") == "yellow"
    assert rules.tag_for("fail") == "red"
    with pytest.raises(ValueError):
        rules.tag_for("green")


def test_next_due_adds_the_interval_and_refuses_a_silly_one() -> None:
    assert rules.next_due(date(2026, 11, 2), 7) == date(2026, 11, 9)
    assert rules.next_due(date(2026, 12, 28), 7) == date(2027, 1, 4)
    for bad in (0, -1, 91):
        with pytest.raises(ValueError):
            rules.next_due(date(2026, 11, 2), bad)


def test_due_state_ok_due_overdue_and_not_applicable() -> None:
    last = date(2026, 11, 2)
    assert rules.due_state("In Use", last, date(2026, 11, 8), 7) == "ok"
    assert rules.due_state("In Use", last, date(2026, 11, 9), 7) == "due"
    assert rules.due_state("Inspected", last, date(2026, 11, 10), 7) == "overdue"
    assert rules.due_state("Modify", last, date(2026, 11, 10), 7) == "overdue"
    # never inspected but standing: overdue; not yet built or already coming down: n_a
    assert rules.due_state("In Use", None, date(2026, 11, 10), 7) == "overdue"
    for state in ("Requested", "Designed", "Erecting", "Dismantle", "Removed"):
        assert rules.due_state(state, last, date(2026, 12, 31), 7) == "n_a"


def test_dismantle_is_refused_while_an_iwp_in_use_or_another_request_is_open() -> None:
    assert rules.dismantle_blockers({}, []) == []
    # planning and finished packages do not hold a scaffold
    quiet = {
        "P1-IWP-0001": "Draft",
        "P1-IWP-0002": "Ready",
        "P1-IWP-0003": "Field complete",
        "P1-IWP-0004": "Closed",
        "P1-IWP-0005": "Cancelled",
    }
    assert rules.dismantle_blockers(quiet, []) == []
    for state in ("Issued", "In progress", "On hold"):
        reasons = rules.dismantle_blockers({"P1-IWP-0009": state}, [])
        assert len(reasons) == 1
        assert "P1-IWP-0009" in reasons[0] and state in reasons[0]
    reasons = rules.dismantle_blockers({}, ["P1-REQ-SCF-0002"])
    assert len(reasons) == 1 and "P1-REQ-SCF-0002" in reasons[0]
    both = rules.dismantle_blockers({"P1-IWP-0009": "Issued"}, ["P1-REQ-SCF-0002"])
    assert len(both) == 2
