"""Ratified defaults the later work must not move: D29, Q5, D35 (Q7: test_materials_reserved)."""

from __future__ import annotations

from decimal import Decimal

import acc_s4
from acc_s3 import PLAIN, Stocked, World, holder, mv
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.derivation.publish_targets import publish_targets
from tl_mod_documents.derivation.store import use_files
from tl_mod_materials import views
from tl_mod_materials.errors import InsufficientStockError
from tl_mod_materials.handlers.items import AdoptItem, DefineItem, handle_define_item
from tl_mod_materials.handlers.movements import (
    IssueStock,
    ReserveStock,
    handle_issue_stock,
    handle_reserve_stock,
)


def test_d29_a_take_off_publishes_without_provenance() -> None:
    assert getattr(publish_targets()["mto"], "takes_provenance", None) is False


def test_d29_a_republished_take_off_key_ends_in_dash_2(world4: acc_s4.World) -> None:
    """A compensated take-off is republished under the next free key: the first is
    ``ISO-1234@A/MTO`` and the republish is ``ISO-1234@A/MTO-2`` (the voided key stays taken)."""
    w = world4
    with (
        use_provider(DirectorySchemaProvider(acc_s4.FIXTURES)),
        use_extractors(make_extractors()),
        use_files(w.docs.files),
    ):
        acc_s4.Fixtures(w)
        first = w.derived("ISO-1234", "mto", acc_s4.GOOD)
        w.publish(first)
        assert (
            w.one(
                "SELECT r.key FROM cur_materials_mto m JOIN cur_core_record r ON r.id = m.id "
                "WHERE NOT r.voided"
            )["key"]
            == "ISO-1234@A/MTO"
        )
        w.compensate(first, "wrong revision")
        again = w.docs.derived_row(first.id)
        assert again.state == "Valid"
        w.publish(again)
        republished = w.one(
            "SELECT r.key FROM cur_materials_mto m JOIN cur_core_record r ON r.id = m.id "
            "WHERE NOT r.voided"
        )["key"]
        assert republished == "ISO-1234@A/MTO-2", republished
        lines = w.lines("ISO-1234@A/MTO-2")
        assert [r["key"] for r in lines] == [f"ISO-1234@A/MTO-2/00{i}" for i in (1, 2, 3)]
        assert all(not bool(r["voided"]) for r in lines)


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


def test_q5_adopt_item_at_company_scope_needs_the_user_word(world3: World) -> None:
    """AdoptItem is a project act whose word is ``user``: refused for an account without it and
    accepted for one with it, both asked at company scope through the command's word."""
    code = world3.code("ADP")
    world3.run(
        handle_define_item,
        DefineItem,
        scope="company",
        code=code,
        title=f"Item {code}",
        category="other",
        base_uom="EA",
        consumable=False,
    )
    adopt = AdoptItem(actor=PLAIN, source="test", scope="company", item_code=code)
    with open_uow(world3.target, readonly=True) as uow:
        try:
            require_command_access(uow.conn(), adopt, holder=holder(PLAIN))
        except ForbiddenError as refused:
            assert str(refused) == "AdoptItem needs the user access word for materials on company"
        else:
            raise AssertionError("an account without the word was not refused")
        require_command_access(uow.conn(), adopt, holder=holder(PLAIN, "user"))


def test_d35_an_unknown_movement_kind_returns_zero_rows(world3: World) -> None:
    Stocked(world3)
    with open_uow(world3.target, readonly=True) as uow:
        assert views.movements(uow.conn(), world3.project, kind="receive") != []
        assert views.movements(uow.conn(), world3.project, kind="teleport") == []
