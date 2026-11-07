"""The materials world the six M4 twin tests share (P2-WEB1-T17): ``seed_materials``.

``seed_awp`` gives the awp twins one data set; this gives the materials twins one, on the
materials fake of ``fakes_materials.py``. It is one story, with ids and codes consistent across
every list and detail:

- four company items: PIPE-6S, BOLT-M20 and WELD-E7018 active, VLV-GATE-4 retired; PIPE-6S is in
  two projects, VLV-GATE-4 in none;
- a store ``WH`` with the bays ``WH-A`` and ``WH-B``, and the bin ``WH-A-1`` under ``WH-A``;
- stock: four rows over three lots. ``PL-4471`` is in two locations, ``BL/26-07`` (a ``/`` in its
  key, no heat) is in the bin, ``WE-2601`` (no receipt) is in ``WH-B``; one row has reserved > 0;
- six movements, one of each kind of ``receive``, ``reserve``, ``transfer``, ``issue``, ``return``,
  ``adjust``, with both directions and one ``None``;
- three receipts: RCV-0001 accepted (two lines, the second on the ``/`` lot), RCV-0002 inspected
  (MTR present), RCV-0003 received (MTR missing);
- three take-off lines on ``ISO-1234@A``: one short, one covered, one with no ``need_by``.

Test support only: no product code. The seed imports the materials view types and no sibling test
module; the web tests load ``fakes_materials.py`` and this file by path.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from tl_mod_materials import views, views_detail

PROJECT = "P123"
OTHER_PROJECT = "P456"  # the second project that adopted PIPE-6S

PIPE, BOLT, WELD, VALVE = "PIPE-6S", "BOLT-M20", "WELD-E7018", "VLV-GATE-4"
TITLES = {
    PIPE: "Carbon steel pipe 6 in Sch 40",
    BOLT: "Hex bolt M20 x 80, zinc",
    WELD: "Electrode E7018 3.2 mm",
    VALVE: "Gate valve 4 in 150#",
}
PIPE_LOT, BOLT_LOT, WELD_LOT = "PL-4471", "BL/26-07", "WE-2601"
ISO = "ISO-1234@A"
MTO_1, MTO_2, MTO_3 = f"{ISO}/MTO-1", f"{ISO}/MTO-2", f"{ISO}/MTO-3"


class MaterialsSeedTarget(Protocol):
    """The four seeding doors of ``FakeMaterialsSupport`` that the seed calls."""

    def put_materials(
        self,
        project: str,
        *,
        stock: Sequence[views.StockRowView] = (),
        movements: Sequence[views.MovementView] = (),
        receipts: Sequence[views.ReceiptView] = (),
        locations: Sequence[views.LocationView] = (),
        mto_lines: Sequence[views.MtoLineView] = (),
        lots: Sequence[views.LotDetailView] = (),
        receipt_details: Sequence[views.ReceiptDetailView] = (),
    ) -> None: ...

    def put_material_items(self, items: Sequence[views.MaterialItemView]) -> None: ...

    def put_mto_line_details(
        self, project: str, details: Sequence[views_detail.MtoLineDetailView]
    ) -> None: ...

    def put_item_projects(
        self, code: str, rows: Sequence[views_detail.ItemProjectView]
    ) -> None: ...


# --- items and locations -------------------------------------------------------------------------

_ITEMS = [
    views.MaterialItemView(
        id="ITM-1",
        code=PIPE,
        title=TITLES[PIPE],
        category="Piping",
        base_uom="M",
        size_text="6 in",
        rating_text="Sch 40",
        material_code="A106-B",
        consumable=False,
        retired=False,
        projects=2,
    ),  # fmt: skip
    views.MaterialItemView(
        id="ITM-2",
        code=BOLT,
        title=TITLES[BOLT],
        category="Fasteners",
        base_uom="PC",
        size_text="M20 x 80",
        rating_text=None,
        material_code="A193-B7",
        consumable=False,
        retired=False,
        projects=1,
    ),  # fmt: skip
    views.MaterialItemView(
        id="ITM-3",
        code=WELD,
        title=TITLES[WELD],
        category="Consumables",
        base_uom="KG",
        size_text="3.2 mm",
        rating_text=None,
        material_code=None,
        consumable=True,
        retired=False,
        projects=1,
    ),  # fmt: skip
    views.MaterialItemView(
        id="ITM-4",
        code=VALVE,
        title=TITLES[VALVE],
        category="Valves",
        base_uom="EA",
        size_text="4 in",
        rating_text="150#",
        material_code="A216-WCB",
        consumable=False,
        retired=True,
        projects=0,
    ),  # fmt: skip
]

_LOCATIONS = [
    views.LocationView(
        id="LOC-WH",
        code="WH",
        title="Site store",
        kind="store",
        parent_code=None,
        depth=0,
        retired=False,
        lots=0,
        lines=0,
    ),  # fmt: skip
    views.LocationView(
        id="LOC-WH-A",
        code="WH-A",
        title="Bay A",
        kind="bay",
        parent_code="WH",
        depth=1,
        retired=False,
        lots=1,
        lines=1,
    ),  # fmt: skip
    views.LocationView(
        id="LOC-WH-B",
        code="WH-B",
        title="Bay B",
        kind="bay",
        parent_code="WH",
        depth=1,
        retired=False,
        lots=2,
        lines=2,
    ),  # fmt: skip
    views.LocationView(
        id="LOC-WH-A-1",
        code="WH-A-1",
        title="Bin A-1",
        kind="bin",
        parent_code="WH-A",
        depth=2,
        retired=False,
        lots=1,
        lines=1,
    ),  # fmt: skip
]


# --- stock ---------------------------------------------------------------------------------------


def _stock(
    lot: str, heat: str | None, item: str, location: str, title: str, on_hand: str,
    reserved: str, available: str, uom: str,
) -> views.StockRowView:  # fmt: skip
    return views.StockRowView(
        lot=lot,
        heat_no=heat,
        item_code=item,
        item_title=TITLES[item],
        location=location,
        location_title=title,
        on_hand=Decimal(on_hand),
        reserved=Decimal(reserved),
        available=Decimal(available),
        uom=uom,
    )


_PIPE_A = _stock(PIPE_LOT, "H4471", PIPE, "WH-A", "Bay A", "12.500", "4.250", "8.250", "M")
_PIPE_B = _stock(PIPE_LOT, "H4471", PIPE, "WH-B", "Bay B", "3.000", "0.000", "3.000", "M")
_BOLT = _stock(BOLT_LOT, None, BOLT, "WH-A-1", "Bin A-1", "240.000", "0.000", "240.000", "PC")
_WELD = _stock(WELD_LOT, "E7018-26B", WELD, "WH-B", "Bay B", "18.750", "0.000", "18.750", "KG")
_STOCK = [_PIPE_A, _PIPE_B, _BOLT, _WELD]


# --- movements -----------------------------------------------------------------------------------


def _move(
    seq: int, when: str, kind: str, lot: str, heat: str | None, item: str, qty: str, uom: str,
    direction: str | None, *, actor: str, frm: str | None = None, to: str | None = None,
    mto_id: str | None = None, mto: str | None = None, wp: str | None = None,
    cost_id: str | None = None, cost: str | None = None, person: str | None = None,
    reason: str | None = None,
) -> views.MovementView:  # fmt: skip
    return views.MovementView(
        seq=seq,
        recorded_at=when,
        kind=kind,
        lot=lot,
        heat_no=heat,
        item_code=item,
        qty=Decimal(qty),
        uom=uom,
        direction=direction,
        from_location=frm,
        to_location=to,
        mto_line_id=mto_id,
        cost_code_id=cost_id,
        person=person,
        reason=reason,
        actor=actor,
        mto_line=mto,
        work_package=wp,
        cost_code=cost,
    )


_M1 = _move(
    1,
    "2026-10-03T09:15:00+00:00",
    "receive",
    PIPE_LOT,
    "H4471",
    PIPE,
    "20.000",
    "M",
    "in",
    actor="user:ana",
    to="WH-A",
)
_M2 = _move(
    2,
    "2026-10-05T14:02:00+00:00",
    "reserve",
    PIPE_LOT,
    "H4471",
    PIPE,
    "4.250",
    "M",
    None,
    actor="user:uma",
    frm="WH-A",
    mto_id="MTL-1",
    mto=MTO_1,
    wp="WP-101",
)
_M3 = _move(
    3,
    "2026-10-06T08:40:00+00:00",
    "transfer",
    PIPE_LOT,
    "H4471",
    PIPE,
    "3.000",
    "M",
    "out",
    actor="user:ana",
    frm="WH-A",
    to="WH-B",
    reason="bay rebalance",
)
_M4 = _move(
    4,
    "2026-10-14T11:30:00+00:00",
    "issue",
    PIPE_LOT,
    "H4471",
    PIPE,
    "4.500",
    "M",
    "out",
    actor="user:uma",
    frm="WH-A",
    mto_id="MTL-1",
    mto=MTO_1,
    wp="WP-101",
    person="R. Patel",
)
_M5 = _move(
    5,
    "2026-10-28T16:05:00+00:00",
    "return",
    BOLT_LOT,
    None,
    BOLT,
    "12.000",
    "PC",
    "in",
    actor="user:ana",
    to="WH-A-1",
    cost_id="CC-4210",
    cost="4210",
    reason="surplus back to store",
)
_M6 = _move(
    6,
    "2026-11-02T10:20:00+00:00",
    "adjust",
    WELD_LOT,
    "E7018-26B",
    WELD,
    "0.750",
    "KG",
    "in",
    actor="user:uma",
    to="WH-B",
    reason="count gain",
)
_MOVEMENTS = [_M1, _M2, _M3, _M4, _M5, _M6]


# --- lots ----------------------------------------------------------------------------------------

_LOTS = [
    views.LotDetailView(
        id="LOT-1",
        key=PIPE_LOT,
        heat_no="H4471",
        item_code=PIPE,
        item_title=TITLES[PIPE],
        uom="M",
        issued_net=Decimal("4.500"),
        receipt="RCV-0001",
        receipt_line=1,
        po_line=None,
        quantities=[_PIPE_A, _PIPE_B],
        reservations=[
            views.ReservationView(
                mto_line=MTO_1, location="WH-A", qty=Decimal("4.250"), work_package="WP-101"
            )
        ],
        movements=[_M4, _M3, _M2, _M1],  # newest first
    ),  # fmt: skip
    views.LotDetailView(
        id="LOT-2",
        key=BOLT_LOT,
        heat_no=None,
        item_code=BOLT,
        item_title=TITLES[BOLT],
        uom="PC",
        issued_net=Decimal("0.000"),
        receipt="RCV-0001",
        receipt_line=2,
        po_line=None,
        quantities=[_BOLT],
        reservations=[],
        movements=[_M5],
    ),  # fmt: skip
    views.LotDetailView(
        id="LOT-3",
        key=WELD_LOT,
        heat_no="E7018-26B",
        item_code=WELD,
        item_title=TITLES[WELD],
        uom="KG",
        issued_net=Decimal("0.000"),
        receipt=None,
        receipt_line=0,
        po_line=None,
        quantities=[_WELD],
        reservations=[],
        movements=[_M6],
    ),  # fmt: skip
]


# --- receipts ------------------------------------------------------------------------------------


def _line(
    line_no: int, item: str, qty: str, uom: str, heat: str | None, lot: str | None
) -> views.ReceiptLineView:
    return views.ReceiptLineView(
        line_no=line_no, item_code=item, item_title=TITLES[item], qty=Decimal(qty), uom=uom,
        heat_no=heat, condition="Good", serials_text=None, lot=lot,
    )  # fmt: skip


_RECEIPT_DETAILS = [
    views.ReceiptDetailView(
        id="RCV-1",
        number="RCV-0001",
        title="Pipe and bolts, Nordic delivery",
        state="Accepted",
        received_on="2026-10-03",
        location="WH-A",
        supplier_text="Nordic Pipe Co",
        delivery_ref="DN-7781",
        po_line=None,
        lines=2,
        mtr="present",
        mtr_required=True,
        created_at="2026-10-03T09:00:00+00:00",
        inspected_by="user:uma",
        inspected_on="2026-10-03",
        decided_by="user:ana",
        decided_on="2026-10-04",
        rejection_reason=None,
        received_by="user:ana",
        line_rows=[
            _line(1, PIPE, "20.000", "M", "H4471", PIPE_LOT),
            _line(2, BOLT, "228.000", "PC", None, BOLT_LOT),
        ],
        files=[
            views.ReceiptFileView(
                file_id="FIL-7781",
                slot=None,
                filename="DN-7781.pdf",
                status="available",
                uploaded_at="2026-10-03T09:30:00+00:00",
            ),
            views.ReceiptFileView(
                file_id="FIL-7782",
                slot="mtr",
                filename="MTR-H4471.pdf",
                status="available",
                uploaded_at="2026-10-03T09:32:00+00:00",
            ),
        ],
    ),  # fmt: skip
    views.ReceiptDetailView(
        id="RCV-2",
        number="RCV-0002",
        title="Electrodes, batch 26C",
        state="Inspected",
        received_on="2026-10-27",
        location="WH-B",
        supplier_text="Arc Supply Ltd",
        delivery_ref="DN-7790",
        po_line=None,
        lines=1,
        mtr="present",
        mtr_required=True,
        created_at="2026-10-27T13:00:00+00:00",
        inspected_by="user:uma",
        inspected_on="2026-10-29",
        decided_by=None,
        decided_on=None,
        rejection_reason=None,
        received_by="user:ana",
        line_rows=[_line(1, WELD, "50.000", "KG", "E7018-26C", None)],
        files=[
            views.ReceiptFileView(
                file_id="FIL-7790",
                slot="mtr",
                filename="MTR-E7018-26C.pdf",
                status="available",
                uploaded_at="2026-10-27T13:20:00+00:00",
            ),
        ],
    ),  # fmt: skip
    views.ReceiptDetailView(
        id="RCV-3",
        number="RCV-0003",
        title="Pipe, second drop",
        state="Received",
        received_on="2026-11-02",
        location="WH-A",
        supplier_text="Nordic Pipe Co",
        delivery_ref="DN-7802",
        po_line=None,
        lines=1,
        mtr="missing",
        mtr_required=True,
        created_at="2026-11-02T08:10:00+00:00",
        inspected_by=None,
        inspected_on=None,
        decided_by=None,
        decided_on=None,
        rejection_reason=None,
        received_by="user:ana",
        line_rows=[_line(1, PIPE, "6.000", "M", "H4502", None)],
        files=[],
    ),  # fmt: skip
]
_RECEIPTS = [
    views.ReceiptView(**r.model_dump(include=set(views.ReceiptView.model_fields)))
    for r in _RECEIPT_DETAILS
]


# --- take-off lines ------------------------------------------------------------------------------

_MTO_LINES = [
    views.MtoLineView(
        id="MTL-1",
        key=MTO_1,
        mto=ISO,
        line_no=1,
        item_code=PIPE,
        item_title=TITLES[PIPE],
        uom="M",
        required=Decimal("12.000"),
        reserved=Decimal("4.250"),
        issued=Decimal("4.500"),
        short=Decimal("3.250"),
        work_package="WP-101",
        work_package_id="WPK-101",
        need_by="2026-11-20",
    ),  # fmt: skip
    views.MtoLineView(
        id="MTL-2",
        key=MTO_2,
        mto=ISO,
        line_no=2,
        item_code=BOLT,
        item_title=TITLES[BOLT],
        uom="PC",
        required=Decimal("150.000"),
        reserved=Decimal("0.000"),
        issued=Decimal("0.000"),
        short=Decimal("150.000"),
        work_package="WP-102",
        work_package_id="WPK-102",
        need_by="2026-11-27",
    ),  # fmt: skip
    views.MtoLineView(
        id="MTL-3",
        key=MTO_3,
        mto=ISO,
        line_no=3,
        item_code=WELD,
        item_title=TITLES[WELD],
        uom="KG",
        required=Decimal("10.000"),
        reserved=Decimal("0.000"),
        issued=Decimal("10.000"),
        short=Decimal("0.000"),
        work_package="WP-103",
        work_package_id="WPK-103",
        need_by=None,
    ),  # fmt: skip
]

_MTO_DETAILS = [
    views_detail.MtoLineDetailView(
        **_MTO_LINES[0].model_dump(),
        reservations=[
            views.ReservationRowView(
                lot=PIPE_LOT,
                location="WH-A",
                mto_line=MTO_1,
                mto_line_id="MTL-1",
                qty=Decimal("4.250"),
                item_code=PIPE,
                iwp_id="WPK-101",
            )
        ],
        open_receipts=[
            views_detail.OpenReceiptView(
                number="RCV-0003",
                state="Received",
                received_on="2026-11-02",
                qty=Decimal("6.000"),
                uom="M",
                supplier_text="Nordic Pipe Co",
            )
        ],
    ),  # fmt: skip
    views_detail.MtoLineDetailView(
        **_MTO_LINES[1].model_dump(), reservations=[], open_receipts=[]
    ),  # fmt: skip
    views_detail.MtoLineDetailView(
        **_MTO_LINES[2].model_dump(),
        reservations=[],
        open_receipts=[
            views_detail.OpenReceiptView(
                number="RCV-0002",
                state="Inspected",
                received_on="2026-10-27",
                qty=Decimal("50.000"),
                uom="KG",
                supplier_text="Arc Supply Ltd",
            )
        ],
    ),  # fmt: skip
]


# --- the seed ------------------------------------------------------------------------------------


def _item_projects(project: str) -> dict[str, list[views_detail.ItemProjectView]]:
    """Per item code, the quantities in each project that adopted it; the ``project`` rows agree
    with the stock rows (PIPE-6S on hand 12.500 + 3.000 in the project)."""

    def row(
        name: str, on_hand: str, reserved: str, available: str, uom: str
    ) -> views_detail.ItemProjectView:
        return views_detail.ItemProjectView(
            project=name, title=name, on_hand=Decimal(on_hand), reserved=Decimal(reserved),
            available=Decimal(available), uom=uom,
        )  # fmt: skip

    return {
        PIPE: [
            row(project, "15.500", "4.250", "11.250", "M"),
            row(OTHER_PROJECT, "30.000", "0.000", "30.000", "M"),
        ],
        BOLT: [row(project, "240.000", "0.000", "240.000", "PC")],
        WELD: [row(project, "18.750", "0.000", "18.750", "KG")],
        VALVE: [],
    }


def seed_materials(fake: MaterialsSeedTarget, project: str = PROJECT) -> None:
    """Fill ``fake`` (after ``_init_materials()``) with the shared materials world of ``project``.

    The six list reads that return rows are stock, movements, receipts, locations, take-off lines
    and the item library; PO lines stay empty (not seeded), and the item projects are per code.
    """
    fake.put_material_items(_ITEMS)
    fake.put_materials(
        project,
        stock=_STOCK,
        movements=_MOVEMENTS,
        receipts=_RECEIPTS,
        locations=_LOCATIONS,
        mto_lines=_MTO_LINES,
        lots=_LOTS,
        receipt_details=_RECEIPT_DETAILS,
    )
    fake.put_mto_line_details(project, _MTO_DETAILS)
    for code, rows in _item_projects(project).items():
        fake.put_item_projects(code, rows)
