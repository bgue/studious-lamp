"""Reads the first view tests leave open: source lines under filters, pages, keys, replayed dates.

Found by the mutation run of P1-I5; each test names the rule it pins.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_mod_correspondence import views
from tl_mod_correspondence.names import CLOCK_TABLE
from tl_mod_correspondence.testing import BASE, PROJECT, CorrWorld, frozen_today
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.testing import DocumentsWorld

MONDAY = "2026-10-19"


def read(world: CorrWorld, fn, *args, **kw):  # type: ignore[no-untyped-def]
    with open_uow(world.db, readonly=True) as uow:
        return fn(uow.conn(), *args, **kw)


def with_transmittal(world: CorrWorld, tmp_path: Path) -> None:
    docs = DocumentsWorld(world.db, tmp_path / "docs")
    docs.issued_document("ISO-1234")
    rev = docs.revision("ISO-1234", "A")
    with open_uow(world.db) as uow:
        handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                subject="Isometrics",
                purpose="for_construction",
                recipients=[Recipient(name="Site", organisation=None, email=None)],
                revision_ids=[rev.id],
            ),
        )


def numbers(lines: list[views.RegisterLineView]) -> list[str]:
    return [ln.number for ln in lines]


def test_a_source_line_is_kept_only_when_every_filter_matches_it(
    world: CorrWorld, tmp_path: Path
) -> None:
    with frozen_today(MONDAY):
        world.receive("A letter")
    with_transmittal(world, tmp_path)
    [trn] = [ln for ln in read(world, views.register, PROJECT) if ln.kind == "transmittal"]
    kept = {"domain": "document_control", "direction": "out", "state": trn.state}
    assert numbers(read(world, views.register, PROJECT, **kept)) == [trn.number]
    for name, other in (("domain", "general"), ("direction", "in"), ("state", "Received")):
        got = read(world, views.register, PROJECT, **{**kept, name: other})
        assert trn.number not in numbers(got), name
    # a filter on the subtype
    assert (
        read(world, views.register, PROJECT, domain="document_control", subtype="submittal") == []
    )
    # a transmittal is not an answer owed
    waiting = read(world, views.register, PROJECT, awaiting_response=True)
    assert trn.number not in numbers(waiting)


def test_a_page_of_the_register_is_a_slice_of_the_whole_with_the_sources_in_place(
    world: CorrWorld, tmp_path: Path
) -> None:
    with frozen_today(MONDAY):
        for day in ("2026-10-12", "2026-10-13", "2026-10-14"):
            world.receive(f"Letter {day}", received_on=day)
    with_transmittal(world, tmp_path)
    full = numbers(read(world, views.register, PROJECT, limit=100))
    assert len(full) == 4
    assert numbers(read(world, views.register, PROJECT, limit=2)) == full[:2]
    assert numbers(read(world, views.register, PROJECT, limit=2, offset=2)) == full[2:4]
    assert numbers(read(world, views.register, PROJECT, limit=2, offset=3)) == full[3:]


def test_a_clock_is_known_by_its_own_key_not_its_items_number(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        item = world.forge_item()
        first = world.start_clock(item).stream_id
        second = world.start_clock(item, label="Another").stream_id
    one = read(world, views.clock_view_by_id, PROJECT, first)
    two = read(world, views.clock_view_by_id, PROJECT, second)
    assert (one.key, two.key) == ("P123-COR-0001-C01", "P123-COR-0001-C02")
    assert one.item_number == two.item_number == "P123-COR-0001"


def test_the_dates_of_a_clock_come_from_its_events_not_from_the_projected_row(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        item = world.forge_item()
        clock = world.start_clock(item).stream_id  # due 2 Nov, warns at 7, 3 and 1 days
    with frozen_today("2026-10-27"):
        world.sweep()
    before = read(world, views.clock_view_by_id, PROJECT, clock)
    assert before.due_on == "2026-11-02" and before.warned_level == 7
    with open_uow(world.db) as uow:  # damage the projection: the view must not believe it
        uow.conn().execute(
            text(
                f"UPDATE {CLOCK_TABLE} SET due_on = '2001-01-01', warned_level = NULL WHERE id = :i"
            ),
            {"i": clock},
        )
    with frozen_today("2026-10-27"):
        after = read(world, views.clock_view_by_id, PROJECT, clock)
    assert (after.due_on, after.warned_level) == ("2026-11-02", 7)


def test_a_thread_lists_its_items_oldest_first_on_both_adapters(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme", received_on="2026-10-12")
        second = world.receive("RE: Programme", received_on="2026-10-14")
        reply = world.draft("Re: Programme", responds_to_id=first.stream_id)  # no date of its own
    found = read(world, views.thread_view, PROJECT, "P123-THR-0001")
    assert [i.number for i in found.items] == [first.key, second.key, reply.key]
