"""Ratified defaults the later work must not move: D29, Q5, D35 (Q7: test_materials_reserved)."""

from __future__ import annotations

from decimal import Decimal

from acc_s3 import Stocked, World, mv
from tl_adapters.db import open_uow
from tl_mod_documents.derivation.publish_targets import publish_targets
from tl_mod_materials import views
from tl_mod_materials.errors import InsufficientStockError
from tl_mod_materials.handlers.movements import (
    IssueStock,
    ReserveStock,
    handle_issue_stock,
    handle_reserve_stock,
)


def test_d29_a_take_off_publishes_without_provenance() -> None:
    assert getattr(publish_targets()["mto"], "takes_provenance", None) is False


def test_q5_reserve_check_is_literal_reserved_plus_qty_within_line_qty(world3: World) -> None:
    s = Stocked(world3)  # the line asks 6; lots hold 12 and 8
    world3.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key1, "6.000", from_location="LA", mto_line_id=s.line)],
    )
    world3.refused(
        lambda: world3.run(
            handle_reserve_stock,
            ReserveStock,
            movements=[mv(s.key2, "0.001", from_location="LA", mto_line_id=s.line)],
        ),
        InsufficientStockError,
        "a reservation past the line quantity",
    )
    # what was issued against the line is not added: after the issue the line is open again
    world3.run(
        handle_issue_stock,
        IssueStock,
        movements=[mv(s.key1, "6.000", from_location="LA", mto_line_id=s.line)],
    )
    world3.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[mv(s.key2, "6.000", from_location="LA", mto_line_id=s.line)],
    )
    held = world3.one("SELECT SUM(qty) AS n FROM cur_materials_reservation")["n"]
    assert Decimal(str(held)) == Decimal("6")


def test_d35_an_unknown_movement_kind_returns_zero_rows(world3: World) -> None:
    Stocked(world3)
    with open_uow(world3.target, readonly=True) as uow:
        assert views.movements(uow.conn(), world3.project, kind="receive") != []
        assert views.movements(uow.conn(), world3.project, kind="teleport") == []
