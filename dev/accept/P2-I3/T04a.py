"""Acceptance for P2-I3-T04a: the materials read routes over HTTP, on the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
serves that copy through ``create_app`` with two dev tokens, a person and an agent. Prints
``PASS <check>`` for each check and exits 0; on the first failure prints ``FAIL <check>: <detail>``
and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T04a.py
"""

import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
ROUTES = ROOT / "packages/tl-api/src/tl_api/routes/materials.py"
READER = "user:reader"
AGENT = "agent:reader"
PROJECT = "/projects/P123/materials"
COMPANY = "/companies/materials/items"
WORK_PACKAGE = "P123-CWP-PIP-0001"
RECEIPT = "P123-RCPT-0001"
HEAT = "H-7781"

#: The nine GET routes, by path as OpenAPI names it, and their operation ids.
ROUTE_IDS = {
    "/projects/{project}/materials/stock": "list_materials_stock",
    "/projects/{project}/materials/lots/{key}": "get_materials_lot",
    "/projects/{project}/materials/movements": "list_materials_movements",
    "/projects/{project}/materials/receipts": "list_materials_receipts",
    "/projects/{project}/materials/receipts/{number}": "get_materials_receipt",
    "/projects/{project}/materials/locations": "list_materials_locations",
    "/projects/{project}/materials/po-lines": "list_materials_po_lines",
    "/projects/{project}/materials/mto-lines": "list_materials_mto_lines",
    COMPANY: "list_materials_items",
}
#: The list routes, which all take ``limit``.
LISTS = (
    f"{PROJECT}/stock",
    f"{PROJECT}/movements",
    f"{PROJECT}/receipts",
    f"{PROJECT}/locations",
    f"{PROJECT}/po-lines",
    f"{PROJECT}/mto-lines",
    COMPANY,
)


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class World:
    app: FastAPI
    client: TestClient
    tokens: dict[str, str]
    state: dict[str, Any]

    def get(self, path: str, token: str | None = READER, **params: Any) -> Any:
        headers = {"Authorization": f"Bearer {self.tokens[token]}"} if token else {}
        return self.client.get(path, params=params or None, headers=headers)

    def rows(self, path: str, **params: Any) -> list[Any]:
        response = self.get(path, **params)
        expect(
            response.status_code == 200,
            f"{path} {params}: {response.status_code} {response.text[:200]}",
        )
        return response.json()


def check_openapi(w: World) -> None:
    paths = w.app.openapi()["paths"]
    for path, operation_id in ROUTE_IDS.items():
        expect(path in paths, f"{path} is not in the OpenAPI document")
        found = paths[path].get("get", {}).get("operationId")
        expect(found == operation_id, f"{path} has operation id {found}, want {operation_id}")


def check_stock_lists_seed(w: World) -> None:
    rows = w.rows(f"{PROJECT}/stock", limit=1000)
    expect(len(rows) > 0, "stock lists no lots")
    w.state["stock_all"] = len(rows)
    w.state["lot"] = rows[0]["lot"]


def check_heat_narrows_stock(w: World) -> None:
    # The S3 seed holds two lots, both of heat H-7781, so the filter keeps both and an
    # unknown heat keeps none. A literal "fewer than unfiltered" cannot hold on this seed.
    rows = w.rows(f"{PROJECT}/stock", heat=HEAT, limit=1000)
    expect(len(rows) == w.state["stock_all"] > 0, f"heat {HEAT} gives {len(rows)} rows")
    expect(all(r["heat_no"] == HEAT for r in rows), f"a row is not heat {HEAT}")
    none = w.rows(f"{PROJECT}/stock", heat="H-0000", limit=1000)
    expect(none == [], f"heat H-0000 gives {len(none)} rows")


def check_lot_detail(w: World) -> None:
    key = w.state["lot"]
    response = w.get(f"{PROJECT}/lots/{key}")
    expect(response.status_code == 200, f"lot {key}: {response.status_code} {response.text[:200]}")
    expect(response.json()["key"] == key, f"lot detail names {response.json()['key']}")


def check_unknown_lot_404(w: World) -> None:
    response = w.get(f"{PROJECT}/lots/NO-SUCH-LOT")
    expect(response.status_code == 404, f"unknown lot answers {response.status_code}")
    expect(response.json()["error"] == "materials_lot_not_found", response.text[:200])


def check_receipt_detail(w: World) -> None:
    response = w.get(f"{PROJECT}/receipts/{RECEIPT}")
    expect(response.status_code == 200, f"receipt {RECEIPT}: {response.status_code}")
    lines = response.json()["line_rows"]
    expect(len(lines) == 2, f"receipt {RECEIPT} has {len(lines)} lines, want 2")


def check_unknown_receipt_404(w: World) -> None:
    response = w.get(f"{PROJECT}/receipts/P123-RCPT-9999")
    expect(response.status_code == 404, f"unknown receipt answers {response.status_code}")
    expect(response.json()["error"] == "materials_receipt_not_found", response.text[:200])


def check_locations_nine(w: World) -> None:
    expect(len(w.rows(f"{PROJECT}/locations")) == 9, "locations are not 9")


def check_po_lines_fifteen(w: World) -> None:
    expect(len(w.rows(f"{PROJECT}/po-lines")) == 15, "po-lines are not 15")


def check_mto_work_package_three(w: World) -> None:
    rows = w.rows(f"{PROJECT}/mto-lines", work_package=WORK_PACKAGE)
    expect(len(rows) == 3, f"mto-lines for {WORK_PACKAGE} are {len(rows)}, want 3")


def check_company_items_fifty(w: World) -> None:
    expect(len(w.rows(COMPANY, limit=1000)) == 50, "company items are not 50")


def check_nine_routes_answer_200(w: World) -> None:
    urls = [
        f"{PROJECT}/stock",
        f"{PROJECT}/lots/{w.state['lot']}",
        f"{PROJECT}/movements",
        f"{PROJECT}/receipts",
        f"{PROJECT}/receipts/{RECEIPT}",
        f"{PROJECT}/locations",
        f"{PROJECT}/po-lines",
        f"{PROJECT}/mto-lines",
        COMPANY,
    ]
    for url in urls:
        response = w.get(url)
        expect(response.status_code == 200, f"{url} answers {response.status_code} to a reader")


def check_limit_bounds_422(w: World) -> None:
    for url in LISTS:
        for limit in (0, 1001):
            response = w.get(url, limit=limit)
            expect(
                response.status_code == 422, f"{url} limit={limit} answers {response.status_code}"
            )


def check_no_token_401(w: World) -> None:
    response = w.get(f"{PROJECT}/stock", token=None)
    expect(response.status_code == 401, f"no token answers {response.status_code}")


def check_agent_reads(w: World) -> None:
    response = w.get(f"{PROJECT}/stock", token=AGENT, limit=5)
    expect(response.status_code == 200, f"agent token answers {response.status_code}")


def check_no_route_passes_a_viewer(w: World) -> None:
    text = ROUTES.read_text(encoding="utf-8")
    expect(re.search(r"viewer\s*=", text) is None, "a materials route passes a viewer (ADR-0016)")


CHECKS: list[tuple[str, Callable[[World], None]]] = [
    ("openapi lists the nine GET routes with their operation ids", check_openapi),
    ("stock lists the seeded lots", check_stock_lists_seed),
    (f"stock heat={HEAT} filters the lots (H-0000 keeps none)", check_heat_narrows_stock),
    ("lot detail of a seeded lot answers 200", check_lot_detail),
    ("unknown lot key answers 404 materials_lot_not_found", check_unknown_lot_404),
    (f"receipt {RECEIPT} answers with two lines", check_receipt_detail),
    ("unknown receipt answers 404 materials_receipt_not_found", check_unknown_receipt_404),
    ("locations returns 9", check_locations_nine),
    ("po-lines returns 15", check_po_lines_fifteen),
    (f"mto-lines for {WORK_PACKAGE} returns 3", check_mto_work_package_three),
    ("company items returns 50", check_company_items_fifty),
    ("the nine routes answer 200 for a reader", check_nine_routes_answer_200),
    ("limit=0 and limit=1001 answer 422 on every list", check_limit_bounds_422),
    ("no token answers 401", check_no_token_401),
    ("an agent token reads (200)", check_agent_reads),
    ("no materials route passes a viewer", check_no_route_passes_a_viewer),
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
        tokens_path = root / "tokens.json"
        tokens = {READER: add_token(tokens_path, READER), AGENT: add_token(tokens_path, AGENT)}
        backend = SqliteUowFactory(db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens_path),
            tokens=TokenStore(tokens_path),
            dev_tokens=True,
        )
        world = World(app, TestClient(app, raise_server_exceptions=False), tokens, {})
        try:
            for name, check in CHECKS:
                try:
                    check(world)
                except Failure as exc:
                    print(f"FAIL {name}: {exc}")
                    return 1
                print(f"PASS {name}")
        finally:
            closer = getattr(backend, "close", None) or backend.dispose
            closer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
