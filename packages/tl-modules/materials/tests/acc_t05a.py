"""Acceptance for P2-I3-T05a: the six materials reports and the report route, on the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory. The
reports are built through ``tl_mod_materials.reports`` on a read-only connection; the route is
driven through ``create_app`` with a reader token. Prints ``PASS <check>`` for each check and exits
0; on the first failure prints ``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T05a.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from tl_adapters.db import as_target, open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.app import create_app
from tl_api.routes.materials import ReportName
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_mod_cost import views as cost_views
from tl_mod_materials import views
from tl_mod_materials.limits import MAX_VIEW_ROWS
from tl_mod_materials.reports import REPORT_NAMES, Report, build_report, safe_cell, to_csv

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / ".accept" / "p2-i3.db"
REPORTS_PY = ROOT / "packages/tl-modules/materials/src/tl_mod_materials/reports.py"
ROUTES_PY = ROOT / "packages/tl-api/src/tl_api/routes/materials.py"
SCOPE = "project:P123"
READER = "user:reader"
REPORTS = "/projects/P123/materials/reports"
WORK_PACKAGE = "P123-CWP-PIP-0001"
HEAT = "H-7781"
STOCK_HEADER = "Lot,Heat,Item,Description,Location,On hand,Reserved,Available,UOM"
HEAT_HEADER = "Heat,Lot,Receipt,MTR file,Event,Date,Location,Qty"


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    conn: Connection
    client: TestClient
    auth: dict[str, str]


def check_six_reports_build(h: Harness) -> None:
    expect(tuple(REPORT_NAMES) == get_args(ReportName), "the route's Literal is not REPORT_NAMES")
    expect(len(REPORT_NAMES) == 6, f"{len(REPORT_NAMES)} report names, want 6")
    cost = {c.id: c.code for c in cost_views.cost_codes(h.conn, SCOPE)}
    for name in REPORT_NAMES:
        report = build_report(h.conn, SCOPE, name, heat=HEAT, cost_codes=cost)
        expect(isinstance(report, Report) and report.name == name, f"{name} did not build")
        expect(report.columns, f"{name} has no columns")
        expect(
            all(len(row) == len(report.columns) for row in report.rows),
            f"{name}: a row is not as wide as its columns",
        )


def check_stock_equals_view(h: Harness) -> None:
    report = build_report(h.conn, SCOPE, "stock_on_hand")
    stock = views.stock(h.conn, SCOPE, limit=MAX_VIEW_ROWS)
    expect(len(stock) > 0 and len(report.rows) == len(stock), "stock rows differ in number")
    for row, s in zip(report.rows, stock, strict=True):
        want = [
            s.lot,
            s.heat_no or "",
            s.item_code,
            s.item_title,
            s.location,
            format(s.on_hand, "f"),
            format(s.reserved, "f"),
            format(s.available, "f"),
            s.uom,
        ]
        expect(row == want, f"stock row {row} is not {want}")


def check_heat_trace_h7781(h: Harness) -> None:
    report = build_report(h.conn, SCOPE, "heat_trace", heat=HEAT)
    lots = {s.lot for s in views.stock(h.conn, SCOPE, heat=HEAT, limit=MAX_VIEW_ROWS)}
    on_hand = {row[1] for row in report.rows if row[4] == "On hand"}
    expect(len(lots) == 2 and on_hand == lots, f"On hand rows name {sorted(on_hand)}")
    expect(any(row[3] for row in report.rows), "no MTR file name in heat_trace for H-7781")


def check_heat_trace_unknown_heat_zero_rows(h: Harness) -> None:
    rows = build_report(h.conn, SCOPE, "heat_trace", heat="H-0000").rows
    expect(rows == [], f"heat H-0000 gives {len(rows)} rows, want 0")


def check_heat_trace_without_heat_is_value_error(h: Harness) -> None:
    try:
        build_report(h.conn, SCOPE, "heat_trace")
    except ValueError:
        return
    raise Failure("heat_trace without a heat did not raise ValueError")


def check_shortages_all_short(h: Harness) -> None:
    rows = build_report(h.conn, SCOPE, "shortages").rows
    short = views.mto_lines(h.conn, SCOPE, short_only=True, limit=MAX_VIEW_ROWS)
    expect(len(rows) == len(short), f"shortages has {len(rows)} rows, the view {len(short)}")
    expect(all(Decimal(row[7]) > 0 for row in rows), "a shortage row has Short <= 0")


def check_mto_status_sums_work_package(h: Harness) -> None:
    rows = [r for r in build_report(h.conn, SCOPE, "mto_status").rows if r[0] == WORK_PACKAGE]
    lines = views.mto_lines(h.conn, SCOPE, work_package=WORK_PACKAGE, limit=MAX_VIEW_ROWS)
    expect(len(lines) == 3, f"{WORK_PACKAGE} has {len(lines)} lines, want 3")
    expect(sum(Decimal(r[3]) for r in rows) == sum(x.required for x in lines), "Required differs")
    expect(sum(Decimal(r[5]) for r in rows) == sum(x.reserved for x in lines), "Reserved differs")
    expect(sum(Decimal(r[6]) for r in rows) == sum(x.issued for x in lines), "Issued differs")


def check_safe_cell_rule(h: Harness) -> None:
    expect(safe_cell("=1+1") == "'=1+1", "=1+1 is not quoted")
    expect(safe_cell("-3") == "-3", "-3 is not left alone")
    expect(safe_cell("1.5") == "1.5", "1.5 is not left alone")
    expect(safe_cell("+cmd|x").startswith("'"), "+cmd|x is not quoted")
    expect(safe_cell("@SUM(A1)") == "'@SUM(A1)", "@ is not quoted")
    expect(safe_cell("\tx").startswith("'"), "a leading tab is not quoted")
    expect(safe_cell(None) == "", "None is not empty")


def check_csv_quotes_formula_reason(h: Harness) -> None:
    report = build_report(h.conn, SCOPE, "movement_log")
    expect(len(report.rows) > 0, "the movement log of the seed is empty")
    row = list(report.rows[0])
    row[report.columns.index("Reason")] = '=HYPERLINK("http://x","y")'
    text = to_csv(Report(name=report.name, columns=report.columns, rows=[row], truncated=False))
    expect(
        '"\'=HYPERLINK(""http://x"",""y"")"' in text,
        f"the formula reason is not a quoted cell: {text[:300]!r}",
    )
    lines = text.split("\r\n")
    expect(lines[0] == ",".join(report.columns), f"header is {lines[0]!r}")
    expect(text.endswith("\r\n") and len(lines) == 3, "to_csv does not end each row with CRLF")


def check_route_json_200(h: Harness) -> None:
    response = h.client.get(f"{REPORTS}/stock_on_hand", headers=h.auth)
    expect(response.status_code == 200, f"JSON report answers {response.status_code}")
    body = response.json()
    expect(body["name"] == "stock_on_hand" and body["rows"], "JSON body is not the report")
    expect(body["columns"][0] == "Lot", f"first column is {body['columns'][0]!r}")


def check_route_csv_200(h: Harness) -> None:
    response = h.client.get(f"{REPORTS}/stock_on_hand", params={"format": "csv"}, headers=h.auth)
    expect(response.status_code == 200, f"CSV report answers {response.status_code}")
    content_type = response.headers["content-type"]
    expect(content_type.startswith("text/csv"), f"content type is {content_type!r}")
    expect(
        response.headers["content-disposition"] == 'attachment; filename="stock_on_hand.csv"',
        f"content disposition is {response.headers['content-disposition']!r}",
    )
    expect(response.text.split("\r\n")[0] == STOCK_HEADER, "the first CSV line is not the header")


def check_route_heat_trace_csv_200(h: Harness) -> None:
    response = h.client.get(
        f"{REPORTS}/heat_trace", params={"heat": HEAT, "format": "csv"}, headers=h.auth
    )
    expect(response.status_code == 200, f"heat_trace CSV answers {response.status_code}")
    expect(response.text.split("\r\n")[0] == HEAT_HEADER, "heat_trace CSV header is wrong")


def check_route_consumables_200(h: Harness) -> None:
    url = f"{REPORTS}/consumables_by_cost_code"
    response = h.client.get(
        url, params={"since": "2026-01-01", "until": "2026-12-31"}, headers=h.auth
    )
    expect(response.status_code == 200, f"consumables answers {response.status_code}")
    expect(response.json()["columns"][-1] == "Qty issued", "consumables columns are wrong")


def check_route_unknown_name_422(h: Harness) -> None:
    response = h.client.get(f"{REPORTS}/no_such_report", headers=h.auth)
    expect(response.status_code == 422, f"unknown name answers {response.status_code}")


def check_route_no_token_401(h: Harness) -> None:
    response = h.client.get(f"{REPORTS}/stock_on_hand")
    expect(response.status_code == 401, f"no token answers {response.status_code}")


def check_route_heat_trace_without_heat_422(h: Harness) -> None:
    response = h.client.get(f"{REPORTS}/heat_trace", headers=h.auth)
    expect(response.status_code == 422, f"heat_trace without heat answers {response.status_code}")
    expect(response.json()["error"] == "materials_invalid_value", response.text[:200])


def check_route_bad_date_422(h: Harness) -> None:
    response = h.client.get(
        f"{REPORTS}/movement_log", params={"until": "2026-13-45"}, headers=h.auth
    )
    expect(response.status_code == 422, f"a bad date answers {response.status_code}")


def check_no_viewer_argument(h: Harness) -> None:
    reports = REPORTS_PY.read_text(encoding="utf-8")
    routes = ROUTES_PY.read_text(encoding="utf-8")
    expect(re.search(r"\bviewer\b", reports) is None, "reports.py names a viewer (ADR-0016)")
    expect(re.search(r"viewer\s*=", routes) is None, "a materials route passes a viewer")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("the six reports build with their columns", check_six_reports_build),
    ("stock_on_hand rows equal views.stock", check_stock_equals_view),
    (
        f"heat_trace {HEAT} has On hand rows for both lots and an MTR file name",
        check_heat_trace_h7781,
    ),
    ("heat_trace H-0000 gives zero rows", check_heat_trace_unknown_heat_zero_rows),
    ("heat_trace without a heat is a ValueError", check_heat_trace_without_heat_is_value_error),
    ("shortages rows all have Short > 0", check_shortages_all_short),
    (
        f"mto_status for {WORK_PACKAGE} sums to the three seeded lines",
        check_mto_status_sums_work_package,
    ),
    ('safe_cell: "=1+1" quoted, "-3" kept, "+cmd|x" quoted', check_safe_cell_rule),
    ("to_csv quotes a movement reason =HYPERLINK(...)", check_csv_quotes_formula_reason),
    ("the report route answers 200 JSON", check_route_json_200),
    ("the report route answers 200 CSV with type and filename", check_route_csv_200),
    ("heat_trace CSV answers 200 with its header", check_route_heat_trace_csv_200),
    ("consumables_by_cost_code answers 200", check_route_consumables_200),
    ("unknown report name answers 422", check_route_unknown_name_422),
    ("no token answers 401 on the report route", check_route_no_token_401),
    (
        "heat_trace without heat answers 422 materials_invalid_value",
        check_route_heat_trace_without_heat_422,
    ),
    ("a bad date answers 422", check_route_bad_date_422),
    ("the report module and route pass no viewer (grep)", check_no_viewer_argument),
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
        token = add_token(tokens_path, READER)
        backend = SqliteUowFactory(db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens_path),
            tokens=TokenStore(tokens_path),
            dev_tokens=True,
        )
        client = TestClient(app, raise_server_exceptions=False)
        try:
            with open_uow(as_target(db), readonly=True) as uow:
                harness = Harness(uow.conn(), client, {"Authorization": f"Bearer {token}"})
                for name, check in CHECKS:
                    try:
                        check(harness)
                    except Failure as exc:
                        print(f"FAIL {name}: {exc}")
                        return 1
                    except Exception as exc:  # an unexpected error is a failed check too
                        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                        return 1
                    print(f"PASS {name}")
        finally:
            closer: Any = getattr(backend, "close", None) or backend.dispose
            closer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
