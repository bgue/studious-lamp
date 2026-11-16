"""``label_fields``: key and text of a record at the lowest class, nothing above it."""

from __future__ import annotations

from qr_world import World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.util import new_ulid
from tl_mod_qr.labels import LabelFields, label_fields

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")


def fields(world: World, record_id: str, viewer: cf.Viewer = cf.LOWEST) -> LabelFields:
    with open_uow(world.db, readonly=True) as uow:
        return label_fields(uow.conn(), record_id, viewer)


def test_an_internal_record_gives_its_key_and_text(world: World) -> None:
    record = world.record(key="P-101")
    assert fields(world, record) == LabelFields(key="P-101", text="P-101")
    assert fields(world, record, LOW) == LabelFields("P-101", "P-101")


def test_a_restricted_record_gives_nothing_even_to_the_cleared(world: World) -> None:
    hidden = world.hidden_record()
    assert fields(world, hidden) == LabelFields(None, None)
    assert fields(world, hidden, LOW) == LabelFields(None, None)
    assert fields(world, hidden, CLEARED) == LabelFields(None, None)


def test_a_missing_record_gives_nothing(world: World) -> None:
    assert fields(world, new_ulid()) == LabelFields(None, None)


def test_the_text_is_cut_to_the_label_limit(world: World) -> None:
    record = world.record(key="K" * 60)
    assert fields(world, record).text == "K" * 40
