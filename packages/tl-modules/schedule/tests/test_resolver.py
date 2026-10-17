"""Resolving a link to an activity: current, as of an earlier snapshot, orphaned (P1-I4-T07)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from tl_adapters.db import open_uow
from tl_core.services.links import (
    FlagLink,
    RepinLink,
    RetractLink,
    handle_flag_link,
    handle_repin_link,
    handle_retract_link,
)
from tl_mod_schedule import resolver
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.names import ORPHAN_REASON
from tl_mod_schedule.resolver import (
    links_to_activities,
    orphaned_links,
    resolve_activity,
    resolve_snapshot,
)
from tl_mod_schedule.testing import BASE, ScheduleWorld
from tl_xer.synth import Spec, make_xer, slipped, week_pair
from xer_files import first_xer

SCOPE = BASE["scope"]


def published_pair(world: ScheduleWorld) -> tuple[str, str]:
    """Snapshots 1 (data date 2026-10-05 08:00) and 2 (2026-10-12 08:00), both published."""
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    return one, two


def third_file() -> bytes:
    """A week after the second: the activity that disappeared (A1990) is back."""
    later = slipped(week_pair()[1], days=0, codes=())
    fence = Spec("A1990", "Temporary fencing", "CON", 20, ("A1200",))
    return make_xer(replace(later, specs=(*later.specs, fence)))


def snapshot_number(world: ScheduleWorld, as_of: resolver.AsOf) -> int | None:
    schedule = world.schedule()
    with open_uow(world.db, readonly=True) as uow:
        found = resolve_snapshot(uow.conn(), schedule.id, as_of, scope=SCOPE)
    return None if found is None else found.number


def resolution(world: ScheduleWorld, activity_id: str, as_of: resolver.AsOf = None):  # noqa: ANN201
    schedule = world.schedule()
    with open_uow(world.db, readonly=True) as uow:
        return resolve_activity(uow.conn(), schedule.id, activity_id, as_of, scope=SCOPE)


# --- which snapshot an as-of names ------------------------------------------------------------


def test_no_as_of_names_the_current_snapshot(world: ScheduleWorld) -> None:
    published_pair(world)
    assert snapshot_number(world, None) == 2


def test_a_schedule_with_nothing_published_has_no_current_snapshot(world: ScheduleWorld) -> None:
    world.define()
    world.upload(first_xer())  # built, not published
    assert snapshot_number(world, None) is None
    assert snapshot_number(world, 1) is None


def test_a_number_names_a_published_snapshot(world: ScheduleWorld) -> None:
    published_pair(world)
    for as_of, number in [(1, 1), (2, 2), (3, None), (0, None), (-1, None)]:
        assert snapshot_number(world, as_of) == number, as_of


def test_a_snapshot_that_is_built_but_not_published_is_not_history(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    assert snapshot_number(world, 1) == 1
    assert snapshot_number(world, 2) is None  # Valid, not published
    world.publish(two)
    assert snapshot_number(world, 2) == 2


def test_a_date_names_the_latest_snapshot_on_or_before_it(world: ScheduleWorld) -> None:
    published_pair(world)
    cases: list[tuple[str, int | None]] = [
        ("2026-10-04", None),
        ("2026-10-05", 1),  # the end of the day: the data date is 08:00
        ("2026-10-11", 1),
        ("2026-10-12", 2),
        ("2027-01-01", 2),
        ("2026-10-12T07:59", 1),
        ("2026-10-12T08:00", 2),
        ("2026-10-05T07:59", None),
    ]
    for as_of, number in cases:
        assert snapshot_number(world, as_of) == number, as_of


def test_a_string_that_is_not_a_date_names_nothing(world: ScheduleWorld) -> None:
    published_pair(world)
    for as_of in ["yesterday", "", "2026-10-05 08:00", "2026-13-45x", "5", "1"]:
        assert snapshot_number(world, as_of) is None, as_of
    for as_of in ["2026-10-12T08:00x", "2026-10-12T08:00:30", "2026-10-12T08:00\n", "2026-10-12\n"]:
        assert snapshot_number(world, as_of) is None, as_of


def test_true_is_not_snapshot_one(world: ScheduleWorld) -> None:
    published_pair(world)
    assert snapshot_number(world, True) is None


def test_an_unknown_schedule_is_an_error(world: ScheduleWorld) -> None:
    world.define()
    with open_uow(world.db, readonly=True) as uow:
        with pytest.raises(ScheduleNotFoundError):
            resolve_snapshot(uow.conn(), "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", scope=SCOPE)
        with pytest.raises(ScheduleNotFoundError):
            resolve_activity(uow.conn(), "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "A1", scope=SCOPE)


# --- what an activity is -----------------------------------------------------------------------


def test_an_activity_resolves_to_the_current_snapshot_and_as_of_the_earlier_one(
    world: ScheduleWorld,
) -> None:
    one, two = published_pair(world)
    now = resolution(world, "A1230")
    assert (now.state, now.snapshot_id, now.snapshot_number) == ("current", two, 2)
    assert now.data_date == "2026-10-12T08:00" and now.schedule_code == "MAIN"
    assert now.activity is not None and now.activity.total_float_hr == 32.0
    before = resolution(world, "A1230", 1)
    assert (before.state, before.snapshot_id, before.snapshot_number) == ("as_of", one, 1)
    assert before.activity is not None and before.activity.total_float_hr == 72.0
    by_date = resolution(world, "A1230", "2026-10-07")
    assert (by_date.state, by_date.snapshot_number) == ("as_of", 1)


def test_an_activity_the_snapshot_lacks_is_orphaned_when_a_reference_exists(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.link(world.record(), "A1990")  # makes the reference
    world.publish(two)
    gone = resolution(world, "A1990")
    assert (gone.state, gone.snapshot_number, gone.activity) == ("orphaned", 2, None)
    earlier = resolution(world, "A1990", 1)
    assert (earlier.state, earlier.snapshot_number) == ("as_of", 1) and earlier.activity is not None


def test_an_activity_nobody_ever_referred_to_is_unknown_not_orphaned(world: ScheduleWorld) -> None:
    published_pair(world)
    assert resolution(world, "A1990").state == "unknown_activity"  # no reference was ever made
    assert resolution(world, "A9999").state == "unknown_activity"


def test_a_missing_snapshot_is_said_not_raised(world: ScheduleWorld) -> None:
    published_pair(world)
    nothing = resolution(world, "A1230", 9)
    assert (nothing.state, nothing.snapshot_id, nothing.snapshot_number, nothing.activity) == (
        "no_snapshot", None, None, None,
    )  # fmt: skip
    assert nothing.activity_id == "A1230" and nothing.schedule_code == "MAIN"


# --- the links of a record ----------------------------------------------------------------------


def test_the_links_of_a_record_are_resolved_each_by_its_own_pin(world: ScheduleWorld) -> None:
    published_pair(world)
    record = world.record()
    floating = world.link(record, "A1230")
    pinned = world.link(record, "A1990", pin=1)  # only snapshot 1 has A1990
    other = world.record()
    world.link(other, "A1240")
    found = links_of(world, record)
    assert [link.link_id for link in found] == [floating.stream_id, pinned.stream_id]
    now, then = found
    assert (now.pin, now.status, now.ref_key) == (None, "active", "MAIN/A1230")
    assert now.resolution.state == "current" and now.resolution.snapshot_number == 2
    assert then.pin == "1" and then.resolution.state == "as_of"
    assert then.ref_key == "MAIN/A1990" and then.resolution.snapshot_number == 1
    assert then.resolution.activity is not None
    assert then.resolution.activity.activity_id == "A1990"


def links_of(world: ScheduleWorld, record: str):  # noqa: ANN201
    with open_uow(world.db, readonly=True) as uow:
        return links_to_activities(uow.conn(), record, scope=SCOPE)


def orphans(world: ScheduleWorld):  # noqa: ANN201
    schedule = world.schedule()
    with open_uow(world.db, readonly=True) as uow:
        return orphaned_links(uow.conn(), schedule.id, scope=SCOPE)


def test_a_retracted_link_and_a_link_to_something_else_are_not_listed(world: ScheduleWorld) -> None:
    published_pair(world)
    record = world.record()
    kept = world.link(record, "A1230")
    dropped = world.link(record, "A1240")
    with open_uow(world.db) as uow:
        handle_retract_link(uow, RetractLink(**BASE, link_id=dropped.stream_id, reason="mistake"))
    from tl_core.services.links import AddLink, handle_add_link

    something_else = world.record()
    with open_uow(world.db) as uow:
        handle_add_link(
            uow, AddLink(**BASE, from_id=record, to_id=something_else, relation="references")
        )
    assert [link.link_id for link in links_of(world, record)] == [kept.stream_id]


def test_a_pin_that_is_not_a_snapshot_number_floats(world: ScheduleWorld) -> None:
    published_pair(world)
    labels = ["rev B", "\u00b2", "\u0662", "9" * 5000, "-1", " 1"]
    for label in labels:
        made = world.link(world.record(), "A1230")  # one record per link: no duplicate
        with open_uow(world.db) as uow:
            handle_repin_link(uow, RepinLink(**BASE, link_id=made.stream_id, pin=label))
        [link] = links_of(world, made_from(world, made.stream_id))
        assert link.pin == label
        assert (link.resolution.state, link.resolution.snapshot_number) == ("current", 2), label


def made_from(world: ScheduleWorld, link_id: str) -> str:
    return str(world.link_row(link_id)["from_id"])


def test_a_pin_written_with_leading_zeros_is_still_a_number(world: ScheduleWorld) -> None:
    published_pair(world)
    made = world.link(world.record(), "A1230")
    with open_uow(world.db) as uow:
        handle_repin_link(uow, RepinLink(**BASE, link_id=made.stream_id, pin="01"))
    [link] = links_of(world, made_from(world, made.stream_id))
    assert (link.resolution.state, link.resolution.snapshot_number) == ("as_of", 1)


def test_a_stale_link_is_listed_with_its_reason(world: ScheduleWorld) -> None:
    published_pair(world)
    record = world.record()
    made = world.link(record, "A1230")
    with open_uow(world.db) as uow:
        handle_flag_link(
            uow, FlagLink(**BASE, link_id=made.stream_id, status="stale", reason="by hand")
        )
    [link] = links_of(world, record)
    assert (link.status, link.reason) == ("stale", "by hand")


# --- link health ------------------------------------------------------------------------------


def test_the_links_of_an_activity_that_left_are_orphaned_until_it_comes_back(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    first, second = world.record(), world.record()
    gone = world.link(first, "A1990")
    world.link(second, "A1990")
    world.link(first, "A1230")  # stays
    world.publish(two)
    found = orphans(world)
    assert [(o.activity_id, o.last_seen_number) for o in found] == [("A1990", 1), ("A1990", 1)]
    assert found[0].link_id == gone.stream_id and found[0].from_id == first
    assert found[0].reason.startswith(ORPHAN_REASON)
    three = world.upload(third_file(), name="third.xer")
    world.publish(three)
    assert orphans(world) == []


def test_a_stale_link_the_module_did_not_flag_is_not_an_orphan(world: ScheduleWorld) -> None:
    one, two = published_pair(world)
    del one, two
    record = world.record()
    made = world.link(record, "A1230")
    with open_uow(world.db) as uow:
        handle_flag_link(
            uow, FlagLink(**BASE, link_id=made.stream_id, status="stale", reason="by hand")
        )
    assert orphans(world) == []


def test_nothing_is_orphaned_in_a_schedule_without_references(world: ScheduleWorld) -> None:
    published_pair(world)
    assert orphans(world) == []


def test_a_link_flagged_by_hand_or_retracted_after_the_flag_is_not_listed(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    modules, hand, retracted, broken = (world.record() for _ in range(4))
    flagged = world.link(modules, "A1990")
    by_hand = world.link(hand, "A1990")
    dropped = world.link(retracted, "A1990")
    smashed = world.link(broken, "A1990")
    world.publish(two)
    assert len(orphans(world)) == 4
    with open_uow(world.db) as uow:  # broken, with the very words the module uses
        handle_flag_link(
            uow, FlagLink(**BASE, link_id=smashed.stream_id, status="broken", reason=ORPHAN_REASON)
        )
    with open_uow(world.db) as uow:
        handle_repin_link(uow, RepinLink(**BASE, link_id=by_hand.stream_id))  # active again
        handle_flag_link(
            uow, FlagLink(**BASE, link_id=by_hand.stream_id, status="stale", reason="see Anna")
        )
        handle_retract_link(uow, RetractLink(**BASE, link_id=dropped.stream_id, reason="mistake"))
    assert [o.link_id for o in orphans(world)] == [flagged.stream_id]


def test_only_the_orphans_of_the_schedule_asked_for_are_listed(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    mine = world.link(world.record(), "A1990")
    world.define("OTHER")
    other_one, other_two = world.two_weeks("OTHER")
    world.publish(other_one)
    theirs = world.link(world.record(), "A1990", code="OTHER")
    world.publish(two)
    world.publish(other_two)
    assert [o.link_id for o in orphans(world)] == [mine.stream_id]
    other = world.schedule("OTHER")
    with open_uow(world.db, readonly=True) as uow:
        assert [o.link_id for o in orphaned_links(uow.conn(), other.id, scope=SCOPE)] == [
            theirs.stream_id
        ]
