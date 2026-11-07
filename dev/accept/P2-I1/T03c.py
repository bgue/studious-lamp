"""Acceptance for P2-I1-T03c: the awp report route, called as a person with a read role.

Copies the seed ledger ``.accept/p2-i1.db`` (written by ``S4.py --keep``) to a scratch file, queues
and rolls up the copy (``requeue_orphans``, then the worker's ``run_until_idle``, as T04b does),
builds the API on the copy and signs in ``vera`` (the awp viewer). Each of the three reports is
read as JSON and as CSV; the JSON cells must equal the CSV cells, row by row. An unknown name
answers 404 ``record_not_found`` and an anonymous call answers 401. Prints one ``PASS`` per check,
then ``T03c ok``; exits 1 on the first failure. No network.

Run: ``uv run python dev/accept/P2-I1/T03c.py``.
"""

from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, open_uow
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_mod_awp import reports
from tl_mod_awp.reports import CostFigure
from tl_mod_awp.worker import build_worker, requeue_orphans
from tl_mod_cost.views import cost_codes

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".accept" / "p2-i1.db"
PASSWORD = "correct horse battery"  # the S4 seed's password for every person
READER = "vera"  # the awp viewer grant in the S4 seed
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
BASE = f"/projects/{PROJECT}/awp/reports"
CSV_TYPE = "text/csv; charset=utf-8"
COLUMNS = {
    "cwp_status": list(reports.StatusRow.model_fields),
    "wbs_vs_cost_code": list(reports.CostRow.model_fields),
    "cwa_sequence": list(reports.SequenceRow.model_fields),
}


def passed(line: str) -> None:
    print(f"PASS {line}", flush=True)


def need(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL {message}", flush=True)
        sys.exit(1)


def cost_figures(conn: Connection) -> dict[str, CostFigure]:
    """The cost system's figures of the project, as the CLI and the route load them."""
    out: dict[str, CostFigure] = {}
    for view in cost_codes(conn, SCOPE, limit=20000):
        hours = view.figures.get("hours_budget")
        out[view.code] = CostFigure(
            title=view.title, hours_budget=None if hours is None else Decimal(str(hours))
        )
    return out


def expected_rows(conn: Connection) -> dict[str, list[Any]]:
    """The rows each report must carry, from ``tl_mod_awp.reports`` on the same copy."""
    return {
        "cwp_status": reports.cwp_status(conn, SCOPE),
        "wbs_vs_cost_code": reports.wbs_vs_cost_code(conn, SCOPE, cost_figures(conn)),
        "cwa_sequence": reports.cwa_sequence(conn, SCOPE),
    }


def cells_of(rows: list[Any]) -> list[list[str]]:
    """The cells of report rows as the route shows them: ``format_value`` of each field."""
    if not rows:
        return []
    names = list(type(rows[0]).model_fields)
    return [[reports.format_value(getattr(row, name)) for name in names] for row in rows]


def main() -> None:
    need(SOURCE.exists(), f"{SOURCE} is missing; run dev/accept/P2-I1/S4.py --keep {SOURCE}")
    work = Path(tempfile.mkdtemp(prefix="t03c-"))
    try:
        db = work / "p2-i1.db"
        shutil.copy(SOURCE, db)
        target = as_target(str(db))
        requeue_orphans(target)
        with build_worker(target) as worker:
            worker.runner.run_until_idle()

        tokens = work / "tokens.json"
        backend = open_backend(db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens),
            tokens=TokenStore(tokens),
        )
        _, token = sessions.sign_in(backend, username=READER, password=PASSWORD)
        client = TestClient(app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        anonymous = TestClient(app, raise_server_exceptions=False)

        with open_uow(target, readonly=True) as uow:
            expected = expected_rows(uow.conn())

        json_cells: dict[str, list[list[str]]] = {}
        for name, want in expected.items():
            response = client.get(f"{BASE}/{name}")
            need(response.status_code == 200, f"GET {name} answered {response.status_code}")
            body = response.json()
            need(body["name"] == name, f"name was {body['name']!r}")
            need(body["columns"] == COLUMNS[name], f"{name} columns were {body['columns']!r}")
            need(body["rows"] == cells_of(want), f"{name} JSON rows differ from the reports")
            json_cells[name] = body["rows"]
            passed(f"json {name} {len(want)} rows")

        for name, want in expected.items():
            response = client.get(f"{BASE}/{name}", params={"format": "csv"})
            need(response.status_code == 200, f"CSV {name} answered {response.status_code}")
            need(
                response.headers["content-type"] == CSV_TYPE,
                f"CSV {name} content type was {response.headers['content-type']!r}",
            )
            need(response.text == reports.to_csv(want), f"CSV {name} body differs")
            passed(f"csv {name}")

        # The JSON cells equal the CSV cells, row by row, for the cost report.
        wbs_csv = client.get(f"{BASE}/wbs_vs_cost_code", params={"format": "csv"}).text
        parsed = list(csv.reader(io.StringIO(wbs_csv)))
        need(parsed[1:] == json_cells["wbs_vs_cost_code"], "wbs_vs_cost_code cells differ")
        passed("cells")

        unknown = client.get(f"{BASE}/x")
        code = unknown.json().get("error")
        message = unknown.json().get("message")
        need(unknown.status_code == 404, f"unknown report answered {unknown.status_code}")
        need(code == "record_not_found", f"unknown report error was {code!r}")
        need(message == "no report 'x'", f"unknown report text was {message!r}")
        passed("unknown")

        plain = anonymous.get(f"{BASE}/cwp_status")
        need(plain.status_code == 401, f"anonymous answered {plain.status_code}")
        passed("401")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("T03c ok", flush=True)


if __name__ == "__main__":
    main()
