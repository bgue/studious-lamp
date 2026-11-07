"""Acceptance for P2-I3-S5: the view keys the screens need (movement and lot ``For``,
``received_by``, the MTO line detail, the per-project quantities of an item).

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory; when
``TL_PG_URL`` is set it also seeds a fresh Postgres schema with the same ledger (S3's ``seed``).
Each backend is checked in two stages: the seed as it is (a receipt filed, every receipt
accepted, no reservation), then after commands add a reservation and an issue against the
first take-off line, a cost code with a consumable issue, and two undecided receipts (one
Inspected, one Received).
The embedded client, the API client (in process) and the fake must agree. Prints ``PASS <check>``
per check, exits 0; on the first failure prints ``FAIL <check>: <detail>`` and exits 1.

    uv run python dev/accept/P2-I3/S5.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / ".accept" / "p2-i3.db"
sys.path[:0] = [str(ROOT / "packages/tl-api/tests"), str(ROOT / "packages/tl-tui/tests")]
os.environ.setdefault("TL_ENV", "dev")  # the harness's dev token file is honoured in dev (as S4.py)

from fakes import FakeClient  # noqa: E402
from harness import ALICE, Harness  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import DbTarget, as_target, create_schema, open_uow  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_core import confidentiality  # noqa: E402
from tl_core.ledger import NewEvent  # noqa: E402
from tl_core.modules import ConfidentialSource, ModuleSpec, load_modules, use_modules  # noqa: E402
from tl_core.util import new_ulid  # noqa: E402
from tl_mod_materials import views, views_detail  # noqa: E402
from tl_mod_materials.errors import MtoLineNotFoundError, ReceiptNotFoundError  # noqa: E402
from tl_mod_materials.handlers.movements import (  # noqa: E402
    IssueStock,
    Movement,
    ReserveStock,
    handle_issue_stock,
    handle_reserve_stock,
)
from tl_mod_materials.handlers.receipts import (  # noqa: E402
    AcceptReceipt,
    CreateReceipt,
    InspectReceipt,
    handle_accept_receipt,
    handle_create_receipt,
    handle_inspect_receipt,
)
from tl_tui.client import ClientInterface  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
WORK_PACKAGE = "P123-CWP-PIP-0001"
RECEIPT = "P123-RCPT-0001"
LOT = "P123-RCPT-0001@1"
FLANGE = "FLG-WN-6-150-A105"
GLOVE = "CON-GLOVE-NIT-L"
COST_CODE = "4210-PIP"
ACTOR = "user:accept"
SOURCE = "accept"
#: The ten new or changed names: two reads (on four classes), the fake's two seeders, three
#: fields on ``MovementView``, one on ``ReservationView``, one on ``ReceiptDetailView``.
CLASS_METHODS = ("get_materials_mto_line", "list_materials_item_projects")


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def plain(value: Any) -> Any:
    """Models and lists as plain JSON data, so two clients' answers compare equal."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


@dataclass
class World:
    label: str
    target: DbTarget
    embedded: EmbeddedClient
    api: ApiClient
    harness: Harness
    state: dict[str, Any] = field(default_factory=dict[str, Any])

    def run(
        self, handler: Callable[[Any, Any], Any], command_type: type[Any], **fields: Any
    ) -> Any:
        command = command_type(actor=ACTOR, source=SOURCE, scope=SCOPE, **fields)
        with open_uow(self.target) as uow:
            return handler(uow, command)

    def read(self, call: Callable[[Any], Any]) -> Any:
        with open_uow(self.target, readonly=True) as uow:
            return call(uow.conn())

    def create(self, record_type: str, key: str, title: str) -> str:
        stream = new_ulid()
        created = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": record_type,
                "key": key,
                "title": title,
                "description": None,
                "psets": {},
            },
        )
        with open_uow(self.target) as uow:
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=SCOPE,
                expected_version=0,
                events=[created],
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )
        return stream

    def lines(self) -> list[views.MtoLineView]:
        return self.embedded.list_materials_mto_lines(PROJECT, work_package=WORK_PACKAGE)

    def http(self, path: str, token: bool = True, **params: Any) -> Any:
        client = self.harness.client_for(ALICE if token else None)
        return client.get(path, params=params or None)


# --- stage A: the seed as it is ------------------------------------------------------------------


def check_received_by(w: World) -> None:
    for client in (w.embedded, w.api):
        found = client.get_materials_receipt(PROJECT, RECEIPT)
        expect(bool(found.received_by), f"{type(client).__name__}: received_by is empty")
    expect(
        w.embedded.get_materials_receipt(PROJECT, RECEIPT).received_by == "user:plain",
        "received_by is not the actor that filed the receipt",
    )


def check_seed_detail_has_no_open_receipts(w: World) -> None:
    first = w.lines()[0]
    detail = w.embedded.get_materials_mto_line(PROJECT, first.key)
    expect(detail.key == first.key, "the detail is of another line")
    expect(isinstance(detail.reservations, list), "reservations is not a list")
    expect(detail.open_receipts == [], f"{len(detail.open_receipts)} open receipts, want 0")
    expect(
        plain(MtoLineViewOf(detail)) == plain(first),
        "the detail's line fields differ from the list",
    )
    w.state["first"] = first


def MtoLineViewOf(detail: views_detail.MtoLineDetailView) -> views.MtoLineView:  # noqa: N802
    return views.MtoLineView(**detail.model_dump(exclude={"reservations", "open_receipts"}))


def check_unknown_key(w: World) -> None:
    for client in (w.embedded, w.api):
        try:
            client.get_materials_mto_line(PROJECT, "ISO-0000@A/MTO/999")
        except MtoLineNotFoundError:
            continue
        raise Failure(f"{type(client).__name__}: an unknown key did not raise")


def check_item_projects_seed(w: World) -> None:
    rows = w.embedded.list_materials_item_projects(FLANGE)
    expect(len(rows) == 1 and rows[0].project == PROJECT, f"rows: {plain(rows)}")
    stock = w.read(lambda c: views.stock(c, SCOPE, item=FLANGE, limit=1000))
    expect(
        rows[0].on_hand == sum((r.on_hand for r in stock), Decimal(0)) == Decimal(20),
        f"on_hand {rows[0].on_hand}, stock {[r.on_hand for r in stock]}",
    )
    expect(w.embedded.list_materials_item_projects("NO-SUCH-ITEM") == [], "unknown code not []")
    expect(w.api.list_materials_item_projects("NO-SUCH-ITEM") == [], "API unknown code not []")


# --- stage B: add a reservation, an issue, a cost code, a consumable issue, undecided receipts ---


def extend(w: World) -> None:
    first: views.MtoLineView = w.state["first"]
    w.run(
        handle_reserve_stock,
        ReserveStock,
        movements=[
            Movement(lot_key=LOT, qty="5", uom="EA", from_location="L2", mto_line_id=first.id)
        ],
    )
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[
            Movement(lot_key=LOT, qty="2", uom="EA", from_location="L2", mto_line_id=first.id)
        ],
    )
    code_id = w.create("cost.CostCode", COST_CODE, "Piping")
    made = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-02",
        location_code="L2",
        po_line=None,
        lines=[{"item_code": GLOVE, "qty": "10.000"}],
    )
    w.run(handle_inspect_receipt, InspectReceipt, stream_id=made.stream_id)
    version = w.read(
        lambda c: c.execute(
            text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": made.stream_id}
        ).scalar_one()
    )
    w.run(handle_accept_receipt, AcceptReceipt, stream_id=made.stream_id, expected_version=version)
    glove_lot = w.read(
        lambda c: c.execute(
            text(
                "SELECT lr.key, x.uom FROM cur_materials_receipt_line x "
                "JOIN cur_core_record lr ON lr.id = x.lot_id WHERE x.receipt_id = :r"
            ),
            {"r": made.stream_id},
        ).one()
    )
    w.run(
        handle_issue_stock,
        IssueStock,
        movements=[
            Movement(
                lot_key=str(glove_lot.key),
                qty="1",
                uom=str(glove_lot.uom),
                from_location="L2",
                cost_code_id=code_id,
                person="R. Singh",
            )
        ],
    )
    inspected = w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-03",
        location_code="L2",
        po_line=None,
        lines=[{"item_code": FLANGE, "qty": "4.000"}, {"item_code": FLANGE, "qty": "1.500"}],
    )
    w.run(handle_inspect_receipt, InspectReceipt, stream_id=inspected.stream_id)
    w.run(
        handle_create_receipt,
        CreateReceipt,
        received_on="2026-11-04",
        location_code="L2",
        po_line=None,
        lines=[{"item_code": FLANGE, "qty": "2.000"}],
    )
    w.state["inspected_key"] = inspected.key


# --- stage C: after the commands ------------------------------------------------------------------


def check_movements_carry_keys(w: World) -> None:
    first: views.MtoLineView = w.state["first"]
    for client in (w.embedded, w.api):
        rows = client.list_materials_movements(PROJECT, lot=LOT)
        by_kind = {r.kind: r for r in rows}
        expect({"receive", "reserve", "issue"} <= set(by_kind), f"kinds {sorted(by_kind)}")
        for kind in ("reserve", "issue"):
            r = by_kind[kind]
            expect(r.mto_line == first.key, f"{kind}: mto_line {r.mto_line!r}")
            expect(r.work_package == WORK_PACKAGE, f"{kind}: work_package {r.work_package!r}")
            expect(r.mto_line_id == first.id, f"{kind}: mto_line_id changed")
        recv = by_kind["receive"]
        expect(
            (recv.mto_line, recv.work_package, recv.cost_code) == (None, None, None),
            "a receive movement names an MTO line or cost code",
        )


def check_consumable_issue_cost_code(w: World) -> None:
    for client in (w.embedded, w.api):
        rows = [r for r in client.list_materials_movements(PROJECT) if r.cost_code_id]
        expect(len(rows) == 1, f"{len(rows)} movements with a cost code, want 1")
        expect(rows[0].cost_code == COST_CODE, f"cost_code {rows[0].cost_code!r}, want the code")
        expect(rows[0].cost_code != rows[0].cost_code_id, "cost_code is the id")
        expect(rows[0].mto_line is None and rows[0].work_package is None, "an MTO key on it")


def check_lot_reservations_work_package(w: World) -> None:
    for client in (w.embedded, w.api):
        lot = client.get_materials_lot(PROJECT, LOT)
        expect(len(lot.reservations) == 1, f"{len(lot.reservations)} reservations, want 1")
        expect(
            lot.reservations[0].work_package == WORK_PACKAGE,
            f"reservation work_package {lot.reservations[0].work_package!r}",
        )
        movement = next(m for m in lot.movements if m.kind == "issue")
        expect(movement.work_package == WORK_PACKAGE, "lot movements lack work_package")


def check_detail_reservations_and_open_receipts(w: World) -> None:
    first: views.MtoLineView = w.state["first"]
    for client in (w.embedded, w.api):
        detail = client.get_materials_mto_line(PROJECT, first.key)
        expect(len(detail.reservations) == 1, f"{len(detail.reservations)} reservations, want 1")
        r = detail.reservations[0]
        expect((r.lot, r.location, r.qty) == (LOT, "L2", Decimal(3)), f"reservation {plain(r)}")
        expect(r.mto_line == first.key and r.iwp_id == first.work_package_id, "reservation keys")
        expect(detail.reserved == Decimal(3) and detail.issued == Decimal(2), "line figures")
        opened = detail.open_receipts
        expect(len(opened) == 2, f"{len(opened)} open receipts, want 2: {plain(opened)}")
        inspected, received = opened
        expect(
            (inspected.state, inspected.qty, inspected.uom) == ("Inspected", Decimal("5.5"), "EA"),
            f"inspected row {plain(inspected)}",
        )
        expect((received.state, received.qty) == ("Received", Decimal(2)), f"row {plain(received)}")
        expect(inspected.number == w.state["inspected_key"], "the Inspected number differs")
        other = client.get_materials_mto_line(PROJECT, w.lines()[1].key)
        expect(other.open_receipts == [], "a line of another item shows these receipts")


def check_item_projects_after(w: World) -> None:
    rows = w.embedded.list_materials_item_projects(FLANGE)
    stock = w.read(lambda c: views.stock(c, SCOPE, item=FLANGE, limit=1000))
    expect(len(rows) == 1, f"{len(rows)} rows, want 1")
    expect(rows[0].on_hand == sum((r.on_hand for r in stock), Decimal(0)), "on_hand != stock sum")
    expect(rows[0].reserved == sum((r.reserved for r in stock), Decimal(0)), "reserved sum")
    expect(rows[0].available == rows[0].on_hand - rows[0].reserved, "available")
    expect(rows[0].on_hand == Decimal(18), f"on_hand {rows[0].on_hand}, want 18 (20 - 2 issued)")


def check_clients_agree(w: World) -> None:
    first: views.MtoLineView = w.state["first"]
    detail = (PROJECT, first.key)
    expect(
        plain(w.embedded.get_materials_mto_line(*detail))
        == plain(w.api.get_materials_mto_line(*detail)),
        "mto line detail: embedded != API",
    )
    for code in (FLANGE, GLOVE, "NO-SUCH-ITEM"):
        expect(
            plain(w.embedded.list_materials_item_projects(code))
            == plain(w.api.list_materials_item_projects(code)),
            f"item projects of {code}: embedded != API",
        )
    fake = FakeClient()
    line = w.embedded.get_materials_mto_line(*detail)
    rows = w.embedded.list_materials_item_projects(FLANGE)
    fake.put_mto_line_details(PROJECT, [line])
    fake.put_item_projects(FLANGE, rows)
    expect(plain(fake.get_materials_mto_line(*detail)) == plain(line), "fake line differs")
    expect(plain(fake.list_materials_item_projects(FLANGE)) == plain(rows), "fake rows differ")
    expect(fake.list_materials_item_projects("NO-SUCH-ITEM") == [], "fake unknown code not []")
    try:
        fake.get_materials_mto_line(PROJECT, "ISO-0000@A/MTO/999")
    except MtoLineNotFoundError as exc:
        expect("ISO-0000@A/MTO/999" in str(exc), "the fake's error does not name the key")
    else:
        raise Failure("the fake did not raise for an unknown line")


def check_routes(w: World) -> None:
    first: views.MtoLineView = w.state["first"]
    base = f"/projects/{PROJECT}/materials/mto-line"
    ok = w.http(base, key=first.key)
    expect(ok.status_code == 200, f"mto-line answers {ok.status_code} {ok.text[:120]}")
    expect(ok.json()["key"] == first.key, "mto-line answered another line")
    missing = w.http(base, key="ISO-0000@A/MTO/999")
    expect(missing.status_code == 404, f"unknown key answers {missing.status_code}")
    expect(missing.json().get("error") == "materials_mto_line_not_found", f"{missing.json()}")
    expect(w.http(base, token=False, key=first.key).status_code == 401, "no token is not 401")
    path = "/companies/materials/item-projects"
    ok = w.http(path, code=FLANGE)
    expect(ok.status_code == 200 and len(ok.json()) == 1, f"item-projects {ok.status_code}")
    expect(w.http(path, code="NO-SUCH-ITEM").json() == [], "unknown code is not []")
    expect(w.http(path, token=False, code=FLANGE).status_code == 401, "no token is not 401")
    paths = w.harness.app.openapi()["paths"]
    ids = {
        "/projects/{project}/materials/mto-line": "get_materials_mto_line",
        path: "list_materials_item_projects",
    }
    for route, operation_id in ids.items():
        found = paths.get(route, {}).get("get", {}).get("operationId")
        expect(found == operation_id, f"{route} has operation id {found}")


def hiding(types: set[str]) -> list[ModuleSpec]:
    """The installed modules, each with a confidential source over the ``x_class`` table for the
    record types it owns among ``types``."""
    out: list[ModuleSpec] = []
    for m in load_modules():
        own = frozenset(types) & m.record_types
        if own:
            source = ConfidentialSource(
                record_types=own, table="x_class", id_column="id", class_column="cls"
            )
            m = dataclasses.replace(m, confidential=(*m.confidential, source))
        out.append(m)
    return out


def check_hidden(w: World) -> None:
    """A record the viewer may not read answers as one that never existed (ADR-0016)."""
    first: views.MtoLineView = w.state["first"]

    def ident(key: str) -> str:
        return str(
            w.read(
                lambda c: c.execute(
                    text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": key}
                ).scalar_one()
            )
        )

    hidden = {
        "cost.CostCode": [ident(COST_CODE)],
        "materials.Receipt": [ident(w.state["inspected_key"])],
    }
    copy = w.read(
        lambda c: c.execute(
            text(
                "SELECT p.id FROM cur_materials_project_item p JOIN cur_materials_item_master t "
                "ON t.id = p.item_master_id WHERE t.code = :c"
            ),
            {"c": FLANGE},
        ).scalar_one()
    )
    hidden["materials.ProjectItem"] = [str(copy)]
    types = {*hidden, "materials.MTOLine"}
    with open_uow(w.target) as uow:
        conn = uow.conn()
        conn.execute(text("CREATE TABLE x_class (id TEXT PRIMARY KEY, cls TEXT)"))
        # a record of a confidential type without a row is hidden: every one gets a class
        for record_type in sorted(types):
            for (record_id,) in conn.execute(
                text("SELECT id FROM cur_core_record WHERE type = :t"), {"t": record_type}
            ).all():
                conn.execute(
                    text("INSERT INTO x_class VALUES (:i, 'internal')"), {"i": str(record_id)}
                )
        for ids in hidden.values():
            for record_id in ids:
                conn.execute(
                    text("UPDATE x_class SET cls = 'restricted' WHERE id = :i"), {"i": record_id}
                )
    changed = hiding(types)
    low, high = confidentiality.LOWEST, confidentiality.Viewer(level=1)
    with use_modules(changed), open_uow(w.target, readonly=True) as uow:
        conn = uow.conn()

        def moved(viewer: confidentiality.Viewer) -> list[views.MovementView]:
            return views.movements(conn, SCOPE, viewer=viewer)

        expect(
            any(m.work_package == WORK_PACKAGE for m in moved(high)),
            "a reader does not see the work package",
        )
        expect(all(m.cost_code is None for m in moved(low)), "a hidden cost code is named")
        expect(any(m.cost_code == COST_CODE for m in moved(high)), "a reader misses the cost code")
        opened = views_detail.mto_line_detail(conn, SCOPE, first.key, viewer=high).open_receipts
        expect(len(opened) == 2, f"a reader sees {len(opened)} open receipts, want 2")
        found = views_detail.mto_line_detail(conn, SCOPE, first.key, viewer=low)
        expect(len(found.open_receipts) == 1, "a hidden receipt is among the open receipts")
        expect(
            views_detail.item_projects(conn, FLANGE, viewer=high) != [],
            "a reader does not see the project",
        )
        expect(
            views_detail.item_projects(conn, FLANGE, viewer=low) == [],
            "a hidden project copy gives a row",
        )
        expect(
            views_detail.item_projects(conn, GLOVE, viewer=low) != [],
            "the hiding is wider than the one copy",
        )
        expect(
            views.receipt_detail(conn, SCOPE, RECEIPT, viewer=low).received_by == "user:plain",
            "a reader of a visible receipt does not see who filed it",
        )
        try:
            views.receipt_detail(conn, SCOPE, w.state["inspected_key"], viewer=low)
        except ReceiptNotFoundError:
            pass
        else:
            raise Failure("a hidden receipt has a detail")
    with use_modules(changed), open_uow(w.target) as uow:
        uow.conn().execute(
            text("UPDATE x_class SET cls = 'restricted' WHERE id = :i"), {"i": first.id}
        )
    with use_modules(changed), open_uow(w.target, readonly=True) as uow:
        conn = uow.conn()
        try:
            views_detail.mto_line_detail(conn, SCOPE, first.key, viewer=low)
        except MtoLineNotFoundError:
            pass
        else:
            raise Failure("a hidden line has a detail")
        expect(
            all(m.mto_line is None for m in views.movements(conn, SCOPE, viewer=low)),
            "a hidden MTO line is named by a movement",
        )
        lot = views.lot_detail(conn, SCOPE, LOT, viewer=low)
        expect(lot.reservations == [], "a hidden line is named by the lot's reservations")
        expect(
            views_detail.mto_line_detail(conn, SCOPE, first.key, viewer=high).key == first.key,
            "a reader misses the line",
        )


def check_old_constructors(_: World) -> None:
    movement = views.MovementView(
        seq=1,
        recorded_at="2026-11-02T00:00:00Z",
        kind="receive",
        lot="L",
        heat_no=None,
        item_code="I",
        qty=Decimal(1),
        uom="EA",
        direction=None,
        from_location=None,
        to_location=None,
        mto_line_id=None,
        cost_code_id=None,
        person=None,
        reason=None,
        actor="a",
    )
    expect(
        (movement.mto_line, movement.work_package, movement.cost_code) == (None,) * 3, "defaults"
    )
    reservation = views.ReservationView(mto_line="K", location="L2", qty=Decimal(1))
    expect(reservation.work_package is None, "ReservationView.work_package has no default")
    fields = views.ReceiptDetailView.model_fields
    expect(fields["received_by"].default is None, "ReceiptDetailView.received_by has no default")
    for name in ("mto_line", "work_package", "cost_code"):
        expect(not views.MovementView.model_fields[name].is_required(), f"{name} is required")


def check_names_on_four_classes(_: World) -> None:
    classes = (ApiClient, ClientInterface, EmbeddedClient, FakeClient)
    for cls in classes:
        for name in CLASS_METHODS:
            expect(callable(getattr(cls, name, None)), f"{cls.__name__} has no {name}")
    for name in ("put_mto_line_details", "put_item_projects"):
        expect(callable(getattr(FakeClient, name, None)), f"FakeClient has no {name}")
    for cls in (ApiClient, EmbeddedClient, FakeClient):
        for name in CLASS_METHODS:
            have = [
                (p.name, p.kind, p.default)
                for p in inspect.signature(getattr(cls, name)).parameters.values()
            ]
            need = [
                (p.name, p.kind, p.default)
                for p in inspect.signature(getattr(ClientInterface, name)).parameters.values()
            ]
            expect(have == need, f"{cls.__name__}.{name}: {have} != {need}")


STAGE_A: list[tuple[str, Callable[[World], None]]] = [
    ("receipt P123-RCPT-0001 has a received_by (embedded and API)", check_received_by),
    (
        "first line detail: reservations list, no open receipts",
        check_seed_detail_has_no_open_receipts,
    ),
    ("unknown line key raises MtoLineNotFoundError (embedded and API)", check_unknown_key),
    ("item_projects: one row, on_hand = stock sum; unknown code is []", check_item_projects_seed),
]
STAGE_C: list[tuple[str, Callable[[World], None]]] = [
    ("reserve and issue movements carry mto_line and work_package", check_movements_carry_keys),
    ("consumable issue carries the cost code's code", check_consumable_issue_cost_code),
    ("lot reservations carry work_package", check_lot_reservations_work_package),
    (
        "line detail: its reservation and its two open receipts",
        check_detail_reservations_and_open_receipts,
    ),
    ("item_projects after the commands", check_item_projects_after),
    ("embedded, API and fake agree on both new methods", check_clients_agree),
    ("routes: 200, unknown key 404, no token 401, operation ids", check_routes),
    ("hidden records: cost code, line, receipt, project copy", check_hidden),
    ("old constructors validate without the new fields", check_old_constructors),
    ("the new names exist on all four client classes", check_names_on_four_classes),
]


def run_backend(label: str, target: DbTarget, root: Path) -> int:
    api_root = root / f"api-{label}"
    api_root.mkdir()
    harness = Harness.build(api_root, target=target)
    try:
        world = World(
            label,
            target,
            EmbeddedClient(harness.backend, actor=ALICE),
            harness.api(ALICE),
            harness,
        )

        def go(checks: list[tuple[str, Callable[[World], None]]]) -> int:
            for name, check in checks:
                try:
                    check(world)
                except Failure as exc:
                    print(f"FAIL {label}: {name}: {exc}")
                    return 1
                print(f"PASS {label}: {name}")
            return 0

        if go(STAGE_A):
            return 1
        extend(world)
        return go(STAGE_C)
    finally:
        harness.close()


def seed_postgres(url: str, root: Path) -> tuple[DbTarget, Callable[[], None]]:
    """A fresh schema with S3's seed (the same ledger as the SQLite file)."""
    from tl_adapters.postgres import admin

    spec = importlib.util.spec_from_file_location("accept_s3", Path(__file__).with_name("S3.py"))
    assert spec is not None and spec.loader is not None
    s3 = importlib.util.module_from_spec(spec)
    sys.modules["accept_s3"] = s3
    spec.loader.exec_module(s3)
    schema = "tl_acc_" + uuid.uuid4().hex[:12]
    admin.create_schema_namespace(url, schema)
    target = as_target(admin.schema_url(url, schema))
    create_schema(target)
    world = s3.World(target, root / "objects")
    world.project = SCOPE
    world.number = PROJECT
    s3.seed(world)
    return target, lambda: admin.drop_schema_namespace(url, schema)


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        status = run_backend("sqlite", as_target(db), root)
        url = os.environ.get("TL_PG_URL")
        if status == 0 and url:
            target, drop = seed_postgres(url, root)
            try:
                status = run_backend("postgres", target, root)
            finally:
                drop()
    return status


if __name__ == "__main__":
    sys.exit(main())
