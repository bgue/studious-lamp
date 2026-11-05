"""Acceptance for P2-I3-T04b: the materials client methods on the four classes.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory. The
embedded client reads that copy; the API client reads it through the app of
``packages/tl-api/tests/harness.py`` (in process, no sockets). Each list method must return the same
rows from both clients and from the view call; the seeded counts, the errors and the write door are
checked on both clients. ``FakeClient`` answers the same filters on a small set. Prints
``PASS <check>`` for each check and exits 0; on the first failure prints ``FAIL <check>: <detail>``
and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T04b.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

import inspect
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
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
from tl_adapters.db import open_uow  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.services.commands import Command  # noqa: E402
from tl_mod_materials import views  # noqa: E402
from tl_mod_materials.errors import LotNotFoundError, ReceiptNotFoundError  # noqa: E402
from tl_tui.client import ClientInterface  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
WORK_PACKAGE = "P123-CWP-PIP-0001"
RECEIPT = "P123-RCPT-0001"
NO_LOT = "P123-LOT-NO-SUCH-LOT"
#: The ten methods T04b adds to ``ClientInterface``: nine reads and the write door.
METHODS = (
    "list_materials_stock",
    "get_materials_lot",
    "list_materials_movements",
    "list_materials_receipts",
    "get_materials_receipt",
    "list_materials_locations",
    "list_materials_po_lines",
    "list_materials_mto_lines",
    "list_materials_items",
    "materials_command",
)


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
class Clients:
    """The embedded client and the API client over the same copy of the ledger."""

    db: Path
    embedded: EmbeddedClient
    api: ApiClient
    lot: str = ""


# (method, positional args, keyword args, the view call on a connection or None)
CASES: list[tuple[str, tuple[str, ...], dict[str, Any], Callable[[Any], Any] | None]] = [
    ("list_materials_stock", (PROJECT,), {}, lambda c: views.stock(c, SCOPE, limit=1000)),
    ("list_materials_movements", (PROJECT,), {}, lambda c: views.movements(c, SCOPE, limit=1000)),
    ("list_materials_receipts", (PROJECT,), {}, lambda c: views.receipts(c, SCOPE, limit=1000)),
    (
        "list_materials_receipts",
        (PROJECT,),
        {"missing_mtr": True},
        lambda c: views.receipts(c, SCOPE, missing_mtr=True, limit=1000),
    ),
    (
        "list_materials_locations",
        (PROJECT,),
        {},
        lambda c: views.locations_tree(c, SCOPE, limit=1000),
    ),
    (
        "list_materials_po_lines",
        (PROJECT,),
        {},
        lambda c: views.po_lines(c, SCOPE, None, limit=1000),
    ),
    (
        "list_materials_mto_lines",
        (PROJECT,),
        {"work_package": WORK_PACKAGE},
        lambda c: views.mto_lines(c, SCOPE, work_package=WORK_PACKAGE, limit=1000),
    ),
    ("list_materials_items", (), {}, lambda c: views.items(c, project=None, limit=1000)),
    (
        "list_materials_items",
        (),
        {"project": PROJECT},
        lambda c: views.items(c, project=SCOPE, limit=1000),
    ),
]


def check_stock_has_two_lots(c: Clients) -> None:
    rows = c.embedded.list_materials_stock(PROJECT, limit=1000)
    lots = sorted({r.lot for r in rows})
    expect(len(lots) >= 2, f"stock lists {len(lots)} lots, want at least 2")
    c.lot = lots[0]


def check_seeded_counts(c: Clients) -> None:
    counts = {
        "locations": (len(c.embedded.list_materials_locations(PROJECT)), 9),
        "po_lines": (len(c.embedded.list_materials_po_lines(PROJECT)), 15),
        "mto_lines": (
            len(c.embedded.list_materials_mto_lines(PROJECT, work_package=WORK_PACKAGE)),
            3,
        ),
        "items": (len(c.embedded.list_materials_items()), 50),
    }  # fmt: skip
    for name, (got, want) in counts.items():
        expect(got == want, f"{name}: {got}, want {want}")


def check_lists_equal_api_and_view(c: Clients) -> None:
    with open_uow(c.db, readonly=True) as uow:
        conn = uow.conn()
        for name, args, kwargs, view in CASES:
            embedded = plain(getattr(c.embedded, name)(*args, limit=1000, **kwargs))
            api = plain(getattr(c.api, name)(*args, limit=1000, **kwargs))
            label = f"{name} {kwargs}".strip()
            expect(embedded == api, f"{label}: the API rows differ from the embedded rows")
            expect(view is not None, f"{label}: no view call")
            expect(embedded == plain(view(conn)), f"{label}: the rows differ from the view call")


def check_lot_detail_equal(c: Clients) -> None:
    embedded = plain(c.embedded.get_materials_lot(PROJECT, c.lot))
    expect(embedded == plain(c.api.get_materials_lot(PROJECT, c.lot)), "lot detail differs")


def check_unknown_lot_raises(c: Clients) -> None:
    for client in (c.embedded, c.api):
        try:
            client.get_materials_lot(PROJECT, NO_LOT)
        except LotNotFoundError:
            continue
        raise Failure(f"{type(client).__name__}: an unknown lot did not raise LotNotFoundError")


def check_receipt_lines(c: Clients) -> None:
    for client in (c.embedded, c.api):
        found = client.get_materials_receipt(PROJECT, RECEIPT)
        expect(len(found.line_rows) == 2, f"{type(client).__name__}: {len(found.line_rows)} lines")
    try:
        c.api.get_materials_receipt(PROJECT, "P123-RCPT-9999")
    except ReceiptNotFoundError:
        return
    raise Failure("an unknown receipt did not raise ReceiptNotFoundError")


def check_write_door_refuses_unknown_name(c: Clients) -> None:
    cmd = Command(actor=ALICE, source="tui", scope=SCOPE)
    for client in (c.embedded, c.api):
        try:
            client.materials_command("NoSuch", cmd)
        except ForbiddenError:
            continue
        raise Failure(f"{type(client).__name__}: NoSuch was not refused")


def check_fake_filters(_: Clients) -> None:
    fake = FakeClient()
    stock = [
        views.StockRowView(
            lot=f"P123-LOT-{n}",
            heat_no=heat,
            item_code="PIPE-6",
            item_title="Pipe 6in",
            location="A1",
            location_title="Yard",
            on_hand=Decimal(5),
            reserved=Decimal(0),
            available=Decimal(5),
            uom="m",
        )  # fmt: skip
        for n, heat in (("1", "H-1"), ("2", "H-2"))
    ]
    receipts = [
        views.ReceiptView(
            id=f"R-{n}",
            number=f"P123-RCPT-000{n}",
            title="Receipt",
            state=state,
            received_on="2026-10-01",
            location="A1",
            supplier_text="Acme",
            delivery_ref=None,
            po_line=None,
            lines=1,
            mtr=mtr,
            mtr_required=True,
        )  # fmt: skip
        for n, state, mtr in (("1", "Received", "missing"), ("2", "Accepted", "present"))
    ]
    fake.put_materials(PROJECT, stock=stock, receipts=receipts)
    heats = [r.heat_no for r in fake.list_materials_stock(PROJECT, heat="H-2")]
    expect(heats == ["H-2"], f"fake stock by heat gives {heats}")
    missing = [r.number for r in fake.list_materials_receipts(PROJECT, missing_mtr=True)]
    expect(missing == ["P123-RCPT-0001"], f"fake receipts by missing_mtr give {missing}")
    try:
        fake.get_materials_lot(PROJECT, NO_LOT)
    except LotNotFoundError:
        return
    raise Failure("fake: an unknown lot did not raise LotNotFoundError")


def check_signatures_on_four_classes(_: Clients) -> None:
    for cls in (ApiClient, ClientInterface, EmbeddedClient, FakeClient):
        for name in METHODS:
            expect(callable(getattr(cls, name, None)), f"{cls.__name__} has no {name}")
    for cls in (ApiClient, EmbeddedClient, FakeClient):
        for name in METHODS:
            have = [
                (p.name, p.kind, p.default)
                for p in inspect.signature(getattr(cls, name)).parameters.values()
                if p.name != "self"
            ]
            need = [
                (p.name, p.kind, p.default)
                for p in inspect.signature(getattr(ClientInterface, name)).parameters.values()
                if p.name != "self"
            ]
            expect(have == need, f"{cls.__name__}.{name}: {have} != {need}")


CHECKS: list[tuple[str, Callable[[Clients], None]]] = [
    ("stock lists at least two lots", check_stock_has_two_lots),
    ("seeded counts: locations, po-lines, take-off lines, items", check_seeded_counts),
    ("every list: API rows and view rows equal the embedded rows", check_lists_equal_api_and_view),
    ("lot detail: API equals embedded", check_lot_detail_equal),
    ("unknown lot raises LotNotFoundError on both", check_unknown_lot_raises),
    ("receipt P123-RCPT-0001 has 2 line rows; unknown receipt raises", check_receipt_lines),
    ("materials_command NoSuch raises ForbiddenError", check_write_door_refuses_unknown_name),
    ("FakeClient answers the heat and missing-MTR filters", check_fake_filters),
    ("ten methods: ClientInterface signatures on four classes", check_signatures_on_four_classes),
]


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        api_root = root / "api"
        api_root.mkdir()
        harness = Harness.build(api_root, target=db)
        try:
            clients = Clients(
                db,
                EmbeddedClient(SqliteUowFactory(db), actor=ALICE),
                harness.api(ALICE),
            )
            for name, check in CHECKS:
                try:
                    check(clients)
                except Failure as exc:
                    print(f"FAIL {name}: {exc}")
                    return 1
                print(f"PASS {name}")
        finally:
            harness.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
