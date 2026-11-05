"""The view keys the screens need (S5): received_by, the MTO line detail, item quantities per
project; every one is class-filtered (ADR-0016)."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
from acc_s3 import ACTOR, Stocked, World, mv
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality
from tl_core.modules import ConfidentialSource, load_modules, use_modules
from tl_mod_materials import views, views_detail
from tl_mod_materials.errors import MtoLineNotFoundError, ReceiptNotFoundError
from tl_mod_materials.handlers.items import AdoptItem, handle_adopt_item
from tl_mod_materials.handlers.movements import ReserveStock, handle_reserve_stock


@contextmanager
def classified(w: World, record_types: set[str], classes: dict[str, str]) -> Iterator[None]:
    """``classes`` (record id -> class) become the confidential source of the module."""
    with open_uow(w.target) as uow:
        uow.conn().execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        for record_id, cls in classes.items():
            uow.conn().execute(
                text("INSERT INTO x_class VALUES (:i, :c)"), {"i": record_id, "c": cls}
            )
    source = ConfidentialSource(
        record_types=frozenset(record_types), table="x_class", id_column="id", class_column="cls"
    )
    changed = [
        dataclasses.replace(m, confidential=(source,)) if m.name == "materials" else m
        for m in load_modules()
    ]
    with use_modules(changed):
        yield


def test_receipt_detail_names_the_person_who_filed_it(world3: World) -> None:
    s = Stocked(world3)
    number = world3.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.receipt)["key"]
    with open_uow(world3.target, readonly=True) as uow:
        detail = views.receipt_detail(uow.conn(), world3.project, number)
    assert detail.received_by == ACTOR


def test_a_hidden_receipt_has_no_detail(world3: World) -> None:
    s = Stocked(world3)
    number = world3.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.receipt)["key"]
    with classified(world3, {"materials.Receipt"}, {s.receipt: "restricted"}):
        with open_uow(world3.target, readonly=True) as uow:
            with pytest.raises(ReceiptNotFoundError):
                views.receipt_detail(
                    uow.conn(), world3.project, number, viewer=confidentiality.LOWEST
                )
            seen = views.receipt_detail(
                uow.conn(), world3.project, number, viewer=confidentiality.Viewer(level=1)
            )
    assert seen.received_by == ACTOR


def test_mto_line_detail_carries_reservations_and_open_receipts(world3: World) -> None:
    s = Stocked(world3)
    world3.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "4.000", from_location="LA", mto_line_id=s.line)],
    )
    key = world3.one("SELECT key FROM cur_core_record WHERE id = :i", i=s.line)["key"]
    with open_uow(world3.target, readonly=True) as uow:
        detail = views_detail.mto_line_detail(uow.conn(), world3.project, key)
        assert detail.id == s.line
        assert [r.qty for r in detail.reservations] == [Decimal("4.000")]
        with pytest.raises(MtoLineNotFoundError):
            views_detail.mto_line_detail(uow.conn(), world3.project, "no-such-line")
    with classified(world3, {"materials.MTOLine"}, {s.line: "restricted"}):
        with open_uow(world3.target, readonly=True) as uow:
            with pytest.raises(MtoLineNotFoundError):
                views_detail.mto_line_detail(
                    uow.conn(), world3.project, key, viewer=confidentiality.LOWEST
                )


def test_item_projects_sums_each_project_and_leaves_out_a_hidden_copy(world3: World) -> None:
    s = Stocked(world3)
    code = world3.code("FLG")
    other = "project:B" + uuid.uuid4().hex[:8].upper()
    copy = world3.run(handle_adopt_item, AdoptItem, scope=other, item_code=code).stream_id
    with open_uow(world3.target, readonly=True) as uow:
        rows = views_detail.item_projects(uow.conn(), code)
    by_project = {r.project: r for r in rows}
    assert by_project[world3.project.removeprefix("project:")].on_hand == Decimal("20")
    assert by_project[other.removeprefix("project:")].on_hand == Decimal("0")
    assert s.flange
    classes = {
        str(r["id"]): "internal" for r in world3.rows("SELECT id FROM cur_materials_project_item")
    }
    classes[copy] = "restricted"
    with classified(world3, {"materials.ProjectItem"}, classes):
        with open_uow(world3.target, readonly=True) as uow:
            low = views_detail.item_projects(uow.conn(), code, viewer=confidentiality.LOWEST)
    assert {r.project for r in low} == {world3.project.removeprefix("project:")}
    with open_uow(world3.target, readonly=True) as uow:
        assert views_detail.item_projects(uow.conn(), "NO-SUCH-ITEM") == []
