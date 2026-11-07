"""The CWP commands (S4): numbering, allocation, workflow, release preconditions, frozen fields."""

from __future__ import annotations

from typing import Any

import pytest
from awp_world import World, hidden_record, line, refuses
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import (
    NoChangesError,
    RecordNotFoundError,
    UnsupportedRecordTypeError,
)
from tl_core.services.links import AddLink, handle_add_link
from tl_core.util import new_ulid
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.errors import (
    AllocationError,
    CwpRuleError,
    CwpStateError,
    ReleaseRefusedError,
    StaleVersionError,
    UnknownListCodeError,
    WbsRuleError,
)

SPEC = {c.model.__name__: c for c in AWP_COMMANDS}


@pytest.fixture
def plant(world: World) -> World:
    world.wbs_tree()
    world.areas_and_path(("A1", "A2"))
    return world


def _alloc(code: str, percent: str = "100.00") -> list[dict[str, str]]:
    return [{"wbs_code": code, "percent": percent}]


def test_numbers_run_gap_free_per_discipline(plant: World) -> None:
    keys = [
        plant.call("uma", "CreateCwp", discipline=d, title=f"T{n}", cwa_code="A1").key
        for n, d in enumerate(("PIP", "PIP", "CIV"))
    ]
    assert keys == ["P123-CWP-PIP-0001", "P123-CWP-PIP-0002", "P123-CWP-CIV-0001"]


def test_hours_are_kept_with_one_decimal_and_the_area_gets_a_rule_link(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1", budget_hours="4200")
    assert plant.scalar("SELECT budget_hours FROM cur_awp_cwp WHERE id = :i", i=cwp) == "4200.0"
    area = plant.rows(
        "SELECT 1 FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
        "AND source = 'rule' AND status <> 'retracted'",
        i=cwp,
    )
    assert len(area) == 1


def test_discipline_and_commodity_must_come_from_the_lists(plant: World) -> None:
    refuses(
        UnknownListCodeError,
        lambda: plant.call("uma", "CreateCwp", discipline="ZZZ", title="x", cwa_code="A1"),
    )
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    plant.call(
        "uma",
        "ReviseCwp",
        cwp=cwp,
        quantities=[{"commodity": "concrete", "qty": "12.5", "uom": "m3"}],
    )
    refuses(
        UnknownListCodeError,
        lambda: plant.call(
            "uma",
            "ReviseCwp",
            cwp=cwp,
            quantities=[{"commodity": "gold", "qty": "1", "uom": "m3"}],
        ),
    )


def test_an_unknown_area_is_refused(plant: World) -> None:
    from tl_mod_awp.errors import CodeNotFoundError

    refuses(
        CodeNotFoundError,
        lambda: plant.call("uma", "CreateCwp", discipline="PIP", title="x", cwa_code="NOPE"),
    )


def test_the_period_must_not_end_before_it_starts(plant: World) -> None:
    with pytest.raises(ValidationError):
        plant.call(
            "uma",
            "CreateCwp",
            discipline="PIP",
            title="x",
            cwa_code="A1",
            planned_start="2026-12-01",
            planned_finish="2026-11-01",
        )


def test_allocation_replaces_the_rows_and_keeps_the_links(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    plant.call(
        "uma",
        "AllocateCwpToWbs",
        cwp=cwp,
        allocations=_alloc("1.1.1", "60.00") + _alloc("1.1.2", "40.00"),
    )
    got = plant.rows(
        "SELECT percent FROM cur_awp_cwp_allocation WHERE cwp_id = :i ORDER BY percent", i=cwp
    )
    assert [g["percent"] for g in got] == ["40.00", "60.00"]
    links = plant.rows(
        "SELECT 1 FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
        "AND status <> 'retracted'",
        i=cwp,
    )
    assert len(links) == 3  # the area and two nodes
    plant.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1.1.1"))
    links = plant.rows(
        "SELECT 1 FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
        "AND status <> 'retracted'",
        i=cwp,
    )
    assert len(links) == 2


@pytest.mark.parametrize("second", ["39.99", "40.01"])
def test_the_cwp_allocation_must_sum_to_100(plant: World, second: str) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    lines = _alloc("1.1.1", "60.00") + _alloc("1.1.2", second)
    refuses(
        AllocationError,
        lambda: plant.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=lines),
    )


def test_allocate_takes_leaf_nodes_only(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    refuses(
        WbsRuleError,
        lambda: plant.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1")),
    )


def test_allocate_has_no_clear_the_empty_list_does_not_validate(plant: World) -> None:
    # D16: the spec gives AllocateCwpToWbs 1 to 20 lines; only the WBS map clears (D10)
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    with pytest.raises(ValidationError):
        plant.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=[])
    plant.call("sue", "MapWbsToCostCodes", node=plant.id_of("1.1.1"), allocations=[])  # D10 clears


def test_the_zero_line_map_checks_nothing_but_lines_still_sum(world: World) -> None:
    world.cost_codes(("W", "w"), ("E", "e"))
    world.call("sue", "DefineWbsNode", code="1", title="One")
    node = world.id_of("1")
    world.call("sue", "MapWbsToCostCodes", node=node, allocations=[])  # nothing to clear: no-op
    refuses(
        AllocationError,
        lambda: world.call(
            "sue",
            "MapWbsToCostCodes",
            node=node,
            allocations=[line("W", "50.00"), line("E", "49.00")],
        ),
    )


STEPS: list[tuple[str, str, str, str]] = [
    ("uma", "StartCwpDevelopment", "In development", "awp.cwp.edit"),
    ("sue", "ReleaseCwp", "Released for IWP development", "awp.cwp.release"),
    ("sue", "ReturnCwp", "In development", "awp.cwp.release"),
    ("sue", "ReleaseCwp", "Released for IWP development", "awp.cwp.release"),
    ("uma", "StartCwpExecution", "Executing", "awp.cwp.edit"),
    ("uma", "CompleteCwp", "Complete", "awp.cwp.edit"),
    ("sue", "ReopenCwp", "Executing", "awp.cwp.close"),
    ("uma", "CompleteCwp", "Complete", "awp.cwp.edit"),
    ("sue", "CloseCwp", "Closed", "awp.cwp.close"),
]


def test_every_workflow_move_runs_with_its_word(plant: World) -> None:
    cwp = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    refuses(ForbiddenError, lambda: plant.call("vera", "StartCwpDevelopment", cwp=cwp))
    for who, name, state, word in STEPS:
        assert SPEC[name].access == word
        extra: dict[str, Any] = {"cwp": cwp}
        if name == "ReleaseCwp":
            extra["expected_version"] = plant.version(cwp)
            refuses(ForbiddenError, lambda e=dict(extra): plant.call("uma", "ReleaseCwp", **e))
        if name in ("ReturnCwp", "ReopenCwp"):
            extra["reason"] = "scope change"
        if name == "CloseCwp":
            refuses(ForbiddenError, lambda: plant.call("uma", "CloseCwp", cwp=cwp))
        plant.call(who, name, **extra)
        assert plant.state(cwp) == state, name
    refuses(CwpStateError, lambda: plant.call("sue", "VoidCwp", id=cwp, reason="late"))


def test_released_carries_the_person_and_the_record_hash(plant: World) -> None:
    cwp = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    plant.call("uma", "StartCwpDevelopment", cwp=cwp)
    plant.call("sue", "ReleaseCwp", cwp=cwp, expected_version=plant.version(cwp))
    [rel] = plant.rows(
        "SELECT payload FROM events WHERE event_type = 'CWP.Released' AND stream_id = :i", i=cwp
    )
    assert "record_hash" in rel["payload"]
    assert "user:sue" in rel["payload"]


def test_a_move_out_of_order_names_the_state(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    exc = refuses(CwpStateError, lambda: plant.call("uma", "CompleteCwp", cwp=cwp))
    assert "Planned" in str(exc)
    refuses(CwpStateError, lambda: plant.call("sue", "ReleaseCwp", cwp=cwp, expected_version=1))


@pytest.fixture
def developing(plant: World) -> tuple[World, str]:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    plant.call("uma", "StartCwpDevelopment", cwp=cwp)
    return plant, cwp


def _release(w: World, cwp: str) -> Any:
    return w.call("sue", "ReleaseCwp", cwp=cwp, expected_version=w.version(cwp))


def test_release_names_every_missing_precondition(developing: tuple[World, str]) -> None:
    w, cwp = developing
    exc = refuses(ReleaseRefusedError, lambda: _release(w, cwp))
    for words in ("budget hours", "planned start", "sum to 100.00"):
        assert words in str(exc)


def test_release_needs_hours_above_zero(developing: tuple[World, str]) -> None:
    w, cwp = developing
    w.call(
        "uma",
        "ReviseCwp",
        cwp=cwp,
        budget_hours="0",
        planned_start="2026-12-01",
        planned_finish="2026-12-31",
    )
    w.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1.2.1"))
    exc = refuses(ReleaseRefusedError, lambda: _release(w, cwp))
    assert "budget hours" in str(exc)
    assert "planned start" not in str(exc)
    assert "sum to 100.00" not in str(exc)
    w.call("uma", "ReviseCwp", cwp=cwp, budget_hours="0.1")
    _release(w, cwp)


@pytest.mark.parametrize("missing", ["planned_start", "planned_finish"])
def test_release_needs_both_dates(developing: tuple[World, str], missing: str) -> None:
    w, cwp = developing
    w.call("uma", "ReviseCwp", cwp=cwp, budget_hours="10", **{missing: None})
    w.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1.2.1"))
    only = (
        {"planned_start": "2026-12-01"}
        if missing == "planned_finish"
        else {"planned_finish": "2026-12-31"}
    )
    w.call("uma", "ReviseCwp", cwp=cwp, **only)
    exc = refuses(ReleaseRefusedError, lambda: _release(w, cwp))
    assert "planned start" in str(exc)


def test_release_needs_the_allocation_to_sum_to_100(developing: tuple[World, str]) -> None:
    w, cwp = developing
    w.call(
        "uma",
        "ReviseCwp",
        cwp=cwp,
        budget_hours="10",
        planned_start="2026-12-01",
        planned_finish="2026-12-31",
    )
    exc = refuses(ReleaseRefusedError, lambda: _release(w, cwp))
    assert "sum to 100.00" in str(exc)
    w.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1.2.1"))
    _release(w, cwp)


def test_a_stale_expected_version_is_refused_and_the_current_one_releases(plant: World) -> None:
    cwp = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    plant.call("uma", "StartCwpDevelopment", cwp=cwp)
    stale = plant.version(cwp)
    plant.call("uma", "ReviseCwp", cwp=cwp, contractor_text="Acme")
    refuses(
        StaleVersionError,
        lambda: plant.call("sue", "ReleaseCwp", cwp=cwp, expected_version=stale),
    )
    refuses(
        StaleVersionError,
        lambda: plant.call("sue", "ReleaseCwp", cwp=cwp, expected_version=plant.version(cwp) + 1),
    )
    _release(plant, cwp)


def test_fields_and_allocation_are_frozen_from_release_and_return_opens_them(plant: World) -> None:
    cwp = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    plant.call("uma", "StartCwpDevelopment", cwp=cwp)
    _release(plant, cwp)
    refuses(CwpStateError, lambda: plant.call("uma", "ReviseCwp", cwp=cwp, title="New"))
    refuses(
        CwpStateError,
        lambda: plant.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=_alloc("1.1.2")),
    )
    plant.call("sue", "ReturnCwp", cwp=cwp, reason="rework")
    plant.call("uma", "ReviseCwp", cwp=cwp, title="Rack, revised")
    assert plant.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=cwp) == "Rack, revised"


def test_revise_with_no_change_is_refused_and_a_null_clears(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Slab 4", "A1", contractor_text="Acme", budget_hours="5")
    refuses(NoChangesError, lambda: plant.call("uma", "ReviseCwp", cwp=cwp, title="Slab 4"))
    plant.call("uma", "ReviseCwp", cwp=cwp, contractor_text=None)
    assert plant.scalar("SELECT contractor_text FROM cur_awp_cwp WHERE id = :i", i=cwp) is None


def test_revise_can_move_the_package_to_another_area(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    plant.call("uma", "ReviseCwp", cwp=cwp, cwa_code="A2")
    assert (
        plant.scalar(
            "SELECT c.code FROM cur_awp_cwp p JOIN cur_awp_cwa c ON c.id = p.cwa_id "
            "WHERE p.id = :i",
            i=cwp,
        )
        == "A2"
    )
    live = plant.rows(
        "SELECT to_id FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
        "AND status <> 'retracted'",
        i=cwp,
    )
    assert [r["to_id"] for r in live] == [plant.id_of("A2", "awp.CWA")]


def test_void_is_the_superuser_s_and_ends_the_package(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    refuses(ForbiddenError, lambda: plant.call("uma", "VoidCwp", id=cwp, reason="x"))
    plant.call("sue", "VoidCwp", id=cwp, reason="not needed")
    assert plant.state(cwp) == "Void"
    refuses(RecordNotFoundError, lambda: plant.call("sue", "VoidCwp", id=cwp, reason="again"))


def test_a_closed_or_void_package_takes_no_generic_link(plant: World) -> None:
    closed = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    plant.call("uma", "StartCwpDevelopment", cwp=closed)
    _release(plant, closed)
    for who, name in (("uma", "StartCwpExecution"), ("uma", "CompleteCwp"), ("sue", "CloseCwp")):
        plant.call(who, name, cwp=closed)
    assert plant.state(closed) == "Closed"
    void = plant.new_cwp("PIP", "Gone", "A1")
    plant.call("sue", "VoidCwp", id=void, reason="x")
    for cwp in (closed, void):
        link = AddLink(
            actor="user:uma",
            source="test",
            scope="project:P123",
            from_id=cwp,
            to_id=plant.id_of("1.1.2"),
            relation="references",
        )
        with open_uow(plant.db) as uow:
            refuses(UnsupportedRecordTypeError, lambda lk=link, u=uow: handle_add_link(u, lk))


def test_a_cwp_takes_a_schedule_activity_link_from_its_end(plant: World) -> None:
    # LinkActivity from a CWP (S4 report): the allow-list holds AddLink, so the source end passes
    import tempfile
    from pathlib import Path

    from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
    from tl_mod_schedule.testing import ScheduleWorld
    from tl_xer.synth import make_xer, week_pair

    cwp = plant.new_cwp("PIP", "Rack", "A1")
    SCHEDULE_BASE["actor"] = "user:sue"
    with tempfile.TemporaryDirectory() as objects:
        sw = ScheduleWorld(plant.db, Path(objects))
        sw.define()
        first, _ = week_pair()
        snapshot = sw.upload(make_xer(first))
        sw.publish(snapshot)
        activity = sw.activities(snapshot)[0].activity_id
        made = sw.link(cwp, activity)
        link = sw.link_row(made.stream_id)
    assert link["from_id"] == cwp
    assert link["status"] == "active"


def test_a_hidden_id_answers_as_a_missing_one(plant: World) -> None:
    hidden, absent = hidden_record(plant), new_ulid()
    texts: list[list[str]] = []
    for target in (hidden, absent):
        tries = (
            ("StartCwpDevelopment", {"cwp": target}),
            ("VoidCwp", {"id": target, "reason": "x"}),
            ("ReviseCwp", {"cwp": target, "title": "x"}),
            ("AllocateCwpToWbs", {"cwp": target, "allocations": _alloc("1.1.1")}),
        )
        texts.append(
            [
                str(refuses(RecordNotFoundError, lambda n=n, f=f: plant.call("sue", n, **f)))
                for n, f in tries
            ]
        )
    assert [t.replace(hidden, "ID") for t in texts[0]] == [
        t.replace(absent, "ID") for t in texts[1]
    ]


def test_cwp_dates_are_checked_when_a_revise_changes_one(plant: World) -> None:
    cwp = plant.new_cwp(
        "PIP", "Rack", "A1", planned_start="2026-11-02", planned_finish="2026-12-01"
    )
    refuses(
        CwpRuleError, lambda: plant.call("uma", "ReviseCwp", cwp=cwp, planned_start="2027-01-01")
    )


def test_offline_drafts_are_empty_for_the_cwp() -> None:
    from tl_core import offline
    from tl_mod_awp.module import spec

    assert spec().offline_drafts == {}
    decision = offline.capture_allowed("awp.CWP", "ReviseCwp", node="site")
    assert not decision.allowed
    assert decision.reason == "not_drafting"
