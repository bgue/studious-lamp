"""Checks of the readiness check materials_reserved (T03)."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from acc_s3 import ACTOR, SOURCE, Stocked, World  # noqa: E402
from sqlalchemy import Engine, event
from tl_adapters.db import as_target, create_schema, make_engine, open_uow
from tl_core.readiness import (
    CheckResult,
    ContractWorld,
    IwpFacts,
    ReadinessCheck,
    check_readiness_contract,
    load_checks,
)
from tl_core.services.commands import CommandResult
from tl_mod_materials.api import PostedMovement, post_movements
from tl_mod_materials.handlers.po_lines import RecordPoLine, handle_record_po_line
from tl_mod_materials.handlers.receipts import (
    CreateReceipt,
    VoidReceipt,
    handle_create_receipt,
    handle_void_receipt,
)
from tl_mod_materials.names import MTO_LINE, RECEIPT

NAME = "materials_reserved"
#: The brief's watches, spelled out here so a rename of the constants cannot pass unnoticed.
WATCHES = frozenset({"materials.StockLot", "materials.MTOLine", "materials.Receipt"})
NO_LINES = "no material take-off lines on this work package"
RECORD_TYPES = frozenset(
    {"materials.StockLot", "materials.MTOLine", "materials.Receipt", "awp.IWP"}
)
TODAY = date(2026, 11, 2)
START = date(2026, 11, 20)
STATEMENT_BUDGET = 6
failures: list[str] = []
ROOT = Path()


def fresh() -> World:
    target = as_target(ROOT / f"{uuid.uuid4().hex}.db")
    create_schema(target)
    return World(target, ROOT / "objects")


def facts(w: World, record_id: str, key: str, planned: date | None = START) -> IwpFacts:
    return IwpFacts(
        record_id=record_id, scope=w.project, key=key, status="Draft", planned_start=planned
    )


def check_object() -> ReadinessCheck:
    return load_checks()[NAME]


def evaluate(w: World, iwp: IwpFacts) -> CheckResult:
    engine = make_engine(w.target)
    try:
        with engine.connect() as conn:
            return check_object().evaluate(conn, iwp, TODAY)
    finally:
        engine.dispose()


def contract(w: World, iwp: IwpFacts, expect_n_a: bool) -> None:
    engine: Engine = make_engine(w.target)
    try:
        world = ContractWorld(engine.connect, iwp, TODAY, RECORD_TYPES, expect_n_a)
        check_readiness_contract(check_object(), world)
    finally:
        engine.dispose()


def statements_of(w: World, iwp: IwpFacts) -> int:
    seen: list[str] = []

    def on_execute(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
        seen.append(statement)

    engine = make_engine(w.target)
    try:
        with engine.connect() as conn:
            event.listen(conn, "before_cursor_execute", on_execute)
            try:
                check_object().evaluate(conn, iwp, TODAY)
            finally:
                event.remove(conn, "before_cursor_execute", on_execute)
    finally:
        engine.dispose()
    return len(seen)


def post(w: World, items: list[PostedMovement]) -> list[str]:
    with open_uow(w.target) as uow:
        return post_movements(uow, items, actor=ACTOR, source=SOURCE, by_module=True)


def flange_wp(w: World, qty: str = "6.000", n: int = 1) -> tuple[str, str, str]:
    """Tree, a flange item, an IWP and one take-off line of it: (item code, IWP id, line id)."""
    w.tree()
    code = w.code("FLG")
    flange = w.item(code, category="flange")
    iwp_id = w.create("awp.IWP", "P1-IWP-0003", "IWP 3")
    line = w.mto_line(flange, qty, work_package=iwp_id, n=n)
    return code, iwp_id, line


def check_registry_finds_the_check() -> None:
    check = check_object()
    assert check.name == NAME, check.name
    assert check.version == "1", check.version
    assert check.watches == WATCHES, check.watches


def check_no_lines_is_n_a() -> None:
    w = fresh()
    iwp_id = w.create("awp.IWP", "P1-IWP-0100", "IWP without take-off")
    iwp = facts(w, iwp_id, "P1-IWP-0100")
    contract(w, iwp, expect_n_a=True)
    result = evaluate(w, iwp)
    assert result.state == "n_a", result.state
    assert result.detail == NO_LINES, result.detail


def check_all_reserved_is_ok() -> None:
    w = fresh()
    s = Stocked(w)
    post(
        w,
        [
            PostedMovement(
                kind="reserve",
                scope=w.project,
                lot_key=s.key1,
                qty="6.000",
                uom="EA",
                from_location="LA",
                mto_line_id=s.line,
            )
        ],
    )
    iwp = facts(w, s.iwp, "P1-IWP-0001")
    contract(w, iwp, expect_n_a=False)
    result = evaluate(w, iwp)
    assert result.state == "ok", (result.state, result.detail)
    assert result.count_ok == result.count_total == 1, (result.count_ok, result.count_total)


def check_issued_counts_as_covered() -> None:
    w = fresh()
    s = Stocked(w)
    post(
        w,
        [
            PostedMovement(
                kind="issue",
                scope=w.project,
                lot_key=s.key1,
                qty="6.000",
                uom="EA",
                from_location="LA",
                mto_line_id=s.line,
            )
        ],
    )
    result = evaluate(w, facts(w, s.iwp, "P1-IWP-0001"))
    assert result.state == "ok", (result.state, result.detail)


def check_received_receipt_is_pending() -> None:
    w = fresh()
    code, iwp_id, line = flange_wp(w)
    made: CommandResult = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-02",
        location_code="LA",
        lines=[{"item_code": code, "qty": "3.000"}],
    )
    iwp = facts(w, iwp_id, "P1-IWP-0003")
    contract(w, iwp, expect_n_a=False)
    result = evaluate(w, iwp)
    assert result.state == "pending", (result.state, result.detail)
    ids = [ref.record_id for ref in result.resolve_via]
    kinds = [ref.record_type for ref in result.resolve_via]
    assert ids == [line, made.stream_id], ids
    assert kinds == [MTO_LINE, RECEIPT], kinds
    assert (result.count_ok, result.count_total) == (0, 1)


def check_promised_on_planned_start_is_pending() -> None:
    w = fresh()
    code, iwp_id, line = flange_wp(w)
    w.run(
        handle_record_po_line,
        RecordPoLine,
        po_number="4471",
        line_no=1,
        item_code=code,
        qty_ordered="10",
        uom="EA",
        promised_date=START.isoformat(),
        supplier_text="Acme Valves",
    )
    result = evaluate(w, facts(w, iwp_id, "P1-IWP-0003"))
    assert result.state == "pending", (result.state, result.detail)
    assert [ref.record_id for ref in result.resolve_via] == [line]


def check_promised_after_planned_start_is_blocked() -> None:
    w = fresh()
    code, iwp_id, line = flange_wp(w)
    w.run(
        handle_record_po_line,
        RecordPoLine,
        po_number="4471",
        line_no=1,
        item_code=code,
        qty_ordered="10",
        uom="EA",
        promised_date="2026-12-01",
        supplier_text="Acme Valves",
    )
    result = evaluate(w, facts(w, iwp_id, "P1-IWP-0003"))
    assert result.state == "blocked", (result.state, result.detail)
    assert [ref.record_id for ref in result.resolve_via] == [line], result.resolve_via


def check_voided_receipt_is_not_pending() -> None:
    w = fresh()
    code, iwp_id, line = flange_wp(w)
    made: CommandResult = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-02",
        location_code="LA",
        lines=[{"item_code": code, "qty": "3.000"}],
    )
    w.run(handle_void_receipt, VoidReceipt, stream_id=made.stream_id, reason="booked in error")
    result = evaluate(w, facts(w, iwp_id, "P1-IWP-0003"))
    assert result.state == "blocked", (result.state, result.detail)
    assert [ref.record_id for ref in result.resolve_via] == [line], result.resolve_via


def check_sixty_short_lines_resolve_fifty() -> None:
    w = fresh()
    w.tree()
    code = w.code("FLG")
    flange = w.item(code, category="flange")
    iwp_id = w.create("awp.IWP", "P1-IWP-0060", "IWP 60")
    for n in range(1, 61):
        w.mto_line(flange, "6.000", work_package=iwp_id, n=n)
    iwp = facts(w, iwp_id, "P1-IWP-0060", planned=None)
    result = evaluate(w, iwp)
    assert len(result.resolve_via) == 50, len(result.resolve_via)
    assert (result.count_ok, result.count_total) == (0, 60), (result.count_ok, result.count_total)
    used = statements_of(w, iwp)
    assert used <= STATEMENT_BUDGET, f"{used} statements, at most {STATEMENT_BUDGET}"
