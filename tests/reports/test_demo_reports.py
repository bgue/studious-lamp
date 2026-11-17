"""`tl report` on a generated project ledger (V3-P0): every module report that has data there.

One small ledger (core, engineering, awp, constraints, requisitions, scaffold, materials,
correspondence, documents) is built once per run. For each report: the header is pinned, the row
count equals the module's own list view for the same viewer, JSONL equals the CSV rows, the low
viewer never has more rows than the controller, and for the reports with a restricted record
(documents in the ledger; an RFI made restricted in a copy) the low output is the full output
without that record's row, byte for byte. A ledger built without the generator's forms section has
no form data; those reports are in ``tests/confidentiality/test_reports_v3.py``.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.modules import module_reports
from tl_core.report_out import render
from tl_mod_awp import iwp_reports
from tl_mod_awp import reports as awp_reports
from tl_mod_correspondence import reports_technical
from tl_mod_correspondence import views as corr_views
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.testing import frozen_today
from tl_mod_documents import reports as doc_reports
from tl_mod_scaffold import views as scaffold_views

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = (
    "core,engineering,awp,constraints,requisitions,scaffold,materials,correspondence,documents"
)
SCOPE = "project:P200"
LOW = cf.LOWEST
FULL = cf.Viewer(actor="user:ada", level=1, account="user:ada")

HEADERS = {
    "rfis": "number,subtype,state,discipline,raised_on,issued_on,required_by,answered_on,"
    "response_days,on_time,overdue,days_overdue,potential_cost_impact,potential_schedule_impact,"
    "cost_impact,schedule_impact,review_decision,class,subject",
    "correspondence": "number,kind,state,direction,domain,subtype,date,counterparty,response_due,"
    "class,subject",
    "documents": "number,state,doc_type,discipline,current_revision,current_status,current_class,"
    "current_issued_on,revisions,open_revision,stale_links,title",
    "scaffolds": "key,subject,state,tag,tagged_on,last_inspected_on,next_due_on,location,elevation,"
    "gridline,load_class,request_key",
    "awp-cwp-status": "state,discipline,count,budget_hours",
    "awp-wbs-vs-cost-code": "code,name,awp_budget_hours,cost_budget_hours,difference",
    "awp-cwa-sequence": "position,cwa,cwa_title,cwps,budget_hours",
    "awp-iwp-status": "state,discipline,count,estimated_hours",
    "awp-iwp-readiness": "number,ready,passing,total,blocked",
    "awp-constraint-log": "key,state,category,severity,owner,phase,due,age_days,aging",
    "materials-stock-on-hand": "Lot,Heat,Item,Description,Location,On hand,Reserved,Available,UOM",
    "materials-movement-log": "Date,Kind,Lot,Item,Qty,UOM,From,To,By,Reason",
    "materials-mto-status": None,
    "materials-shortages": None,
    "materials-consumables-by-cost-code": None,
    "form-submissions": "key,state,template,template_version,subject,answer_class,author,"
    "submitted_on,reviewed_by,reviewed_on",
    "form-templates": "key,title,version,state,intake,purpose,answer_class,bound_record_type,"
    "field_count,published_on,retired_on",
}


@pytest.fixture(scope="module")
def ledger(tmp_path_factory: pytest.TempPathFactory) -> Path:
    reuse = os.environ.get("TL_REPORT_DEMO_DB")  # a ledger already built with SECTIONS (dev only)
    if reuse and Path(reuse).exists():
        return Path(reuse)
    base = tmp_path_factory.mktemp("demo-reports")
    db = base / "demo.db"
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [sys.executable, "-m", "dev.seed.demo_project", "--db", str(db), "--objects",
         str(base / "obj"), "--sections", SECTIONS],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-500:]
    return db


def out(db: Path, name: str, viewer: cf.Viewer, fmt: str = "csv") -> str:
    with open_uow(str(db), readonly=True) as uow:
        return "".join(render(module_reports()[name], uow.conn(), SCOPE, viewer, fmt))


def rows(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))[1:]


def list_view_count(db: Path, name: str, viewer: cf.Viewer) -> int | None:
    """The row count the module's own view gives this viewer; None where a view has no count."""
    with open_uow(str(db), readonly=True) as uow, cf.use_viewer(viewer):
        conn = uow.conn()
        if name == "rfis":
            return reports_technical.rfi_log(conn, SCOPE, limit=1_000_000).total
        if name == "correspondence":
            return len(corr_views.register(conn, SCOPE, limit=1_000_000))
        if name == "documents":
            return len(doc_reports.document_register(conn, SCOPE, limit=1_000_000))
        if name == "scaffolds":
            return scaffold_views.scaffold_list(conn, SCOPE, limit=500, viewer=viewer).total
        if name == "awp-cwp-status":
            return len(awp_reports.cwp_status(conn, SCOPE))
        if name == "awp-cwa-sequence":
            return len(awp_reports.cwa_sequence(conn, SCOPE))
        if name == "awp-iwp-status":
            return len(iwp_reports.iwp_status(conn, SCOPE))
        if name == "awp-iwp-readiness":
            return len(iwp_reports.iwp_readiness(conn, SCOPE))
        if name == "awp-constraint-log":
            return len(iwp_reports.constraint_log(conn, SCOPE))
    return None


def test_every_registered_report_has_a_pinned_header() -> None:
    assert set(module_reports()) == set(HEADERS)


@pytest.mark.parametrize("name", [n for n, h in HEADERS.items() if h])
def test_the_header_is_pinned(ledger: Path, name: str) -> None:
    assert out(ledger, name, FULL).splitlines()[0] == HEADERS[name]
    assert out(ledger, name, LOW).splitlines()[0] == HEADERS[name]


@pytest.mark.parametrize("name", [n for n, h in HEADERS.items() if h and not n.startswith("form")])
def test_the_row_count_equals_the_list_view_and_jsonl_equals_csv(ledger: Path, name: str) -> None:
    for viewer in (LOW, FULL):
        body = out(ledger, name, viewer)
        counted = list_view_count(ledger, name, viewer)
        if counted is not None:
            assert len(rows(body)) == counted, (name, viewer.level)
    full = rows(out(ledger, name, FULL))
    lines = [json.loads(x) for x in out(ledger, name, FULL, "jsonl").splitlines()]
    assert len(lines) == len(full)
    assert len(rows(out(ledger, name, LOW))) <= len(full)
    for line, row in zip(lines, full, strict=True):
        assert [
            "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
            for v in line.values()
        ] == [c.removeprefix("'") if c.startswith("'") else c for c in row]


@pytest.mark.parametrize("name", ["rfis", "correspondence", "documents", "scaffolds"])
def test_each_module_report_has_rows(ledger: Path, name: str) -> None:
    assert len(rows(out(ledger, name, FULL))) > 0


def test_a_restricted_document_is_a_controller_row_and_not_a_low_row(ledger: Path) -> None:
    full, low = rows(out(ledger, "documents", FULL)), rows(out(ledger, "documents", LOW))
    assert len(full) == len(low) + 1
    gone = [r for r in full if r not in low]
    assert len(gone) == 1
    expected = [r for r in full if r != gone[0]]
    assert expected == low  # nothing else moved: no gap, no mark, no count
    assert gone[0][0] not in out(ledger, "documents", LOW)  # its number is nowhere in the output


def test_a_restricted_rfi_is_missing_for_the_low_viewer(ledger: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy.db"
    shutil.copy(ledger, copy)
    before_low = rows(out(copy, "rfis", LOW))
    before_full = rows(out(copy, "rfis", FULL))
    assert before_low == before_full  # the generated RFIs are all internal
    with open_uow(str(copy), readonly=True) as uow:
        row = (
            uow.conn()
            .exec_driver_sql(
                "SELECT t.id, r.key FROM cur_correspondence_technical_item t "
                "JOIN cur_core_record r ON r.id = t.id WHERE r.scope = ? ORDER BY r.key LIMIT 1",
                (SCOPE,),
            )
            .one()
        )
    cmd = SetCorrespondenceConfidentiality(
        actor="user:dora", source="test", scope=SCOPE, stream_id=row[0], to_class="restricted",
        grant=[], reason="test",
    )  # fmt: skip
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(str(copy)) as uow:
        handle_set_confidentiality(uow, cmd)
    after_low, after_full = rows(out(copy, "rfis", LOW)), rows(out(copy, "rfis", FULL))
    assert len(after_full) == len(before_full)  # the controller still has the row, now marked
    assert [r[:17] + r[18:] for r in after_full] == [r[:17] + r[18:] for r in before_full]
    assert [r[17] for r in after_full if r[0] == row[1]] == ["restricted"]
    assert after_low == [r for r in before_low if r[0] != row[1]]
    assert len(after_low) == len(before_low) - 1
    assert row[1] not in out(copy, "rfis", LOW)
