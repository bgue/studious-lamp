"""The feed cards of correspondence events obey the class of the item they are about (P1-I6).

A card that names no record (``ctl defined a commercial``) tells a reader who may not read the
item that it exists. Every event of an item's stream is about that item, so the card is tagged with
it and the class filter hides the card with the item (ADR-0016, the P1-I6 security review).
"""

from __future__ import annotations

from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, frozen_today

PLAIN = cf.Viewer(actor="user:bob", level=0, account="user:bob")
AMY = cf.Viewer(actor="user:amy", level=0, account="user:amy")


def summaries(world: CorrWorld, viewer: cf.Viewer) -> list[str]:
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        clause, params = cf.not_hidden_item("i.item_id")
        rows = uow.conn().execute(
            text(f"SELECT i.summary FROM cur_feed_items i WHERE i.item_type = 'card' AND {clause}"),
            params,
        )
        return [str(r[0]) for r in rows]


def seed(world: CorrWorld) -> None:
    with frozen_today("2026-10-19"):
        world.forge_item("P123-COR-0001", subject="Open letter", state="Received")
        world.forge_technical("P123-RFI-0001", state="Issued")
        world.forge_commercial("P123-EW-0001")  # restricted
        secret = world.forge_commercial("P123-EW-0002", confidentiality="privileged")
        world.forge_item_event(
            secret,
            "Correspondence.ClearanceGranted",
            {"account": "user:amy", "granted_on": "2026-10-19", "reason": "counsel"},
        )


def test_a_plain_reader_is_told_nothing_of_a_restricted_or_privileged_item(
    world: CorrWorld,
) -> None:
    seed(world)
    assert summaries(world, CONTROLLER)  # the cards exist
    shown = " ".join(summaries(world, PLAIN)).lower()
    assert "commercial" not in shown and "clearance" not in shown
    assert "correspondence" in shown or "technical" in shown  # the open items still make cards


def test_a_controller_reads_the_restricted_cards_but_not_the_privileged_ones(
    world: CorrWorld,
) -> None:
    seed(world)
    plain = summaries(world, PLAIN)
    controller = summaries(world, CONTROLLER)
    amy = summaries(world, AMY)
    assert len(controller) > len(plain)
    assert any("commercial" in line.lower() for line in controller)
    assert not any("clearance" in line.lower() for line in controller)  # privileged: not named
    assert any("clearance" in line.lower() for line in amy)  # the named reader
    assert not any("commercial" in line.lower() for line in plain)


def test_the_cards_of_a_core_item_follow_its_class_too(world: CorrWorld) -> None:
    world.forge_item("P123-COR-0003", subject="Counsel advice", state="Received",
                     confidentiality="privileged")  # fmt: skip
    assert summaries(world, PLAIN) == []
    assert summaries(world, CONTROLLER) == []
